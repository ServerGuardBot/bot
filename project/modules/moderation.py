from datetime import datetime
import re
from project.helpers.embeds import *
from project.helpers.images import *
from project.helpers.Cache import Cache
from project.helpers.translator import translate
from project.modules.base import Module
from project import bot_config, BotAPI, malicious_urls, guilded_paths
from guilded.ext import commands
from guilded import Embed, Colour, Forbidden, BulkMemberRolesUpdateEvent, MemberJoinEvent, MemberRemoveEvent, BanCreateEvent, \
    BanDeleteEvent, MessageUpdateEvent, MessageDeleteEvent, ForumTopicCreateEvent, ForumTopicDeleteEvent, ForumTopicUpdateEvent, \
    ChatMessage, ForumTopic, WebhookCreateEvent, WebhookUpdateEvent, ServerChannelCreateEvent, ServerChannelDeleteEvent, \
    ServerChannelUpdateEvent, ForumTopicReplyCreateEvent, ForumTopicReplyDeleteEvent, ForumTopicReplyUpdateEvent, \
    AnnouncementReplyCreateEvent, AnnouncementReplyUpdateEvent, AnnouncementReplyDeleteEvent, User, http
from humanfriendly import parse_timespan, format_timespan
from better_profanity import Profanity
from unidecode import unidecode
from bs4 import BeautifulSoup

import os
import requests
import joblib
import numpy as np

user_converter = commands.UserConverter()

SERVER_INVITE_REGEX = r'h?t?t?p?s?:?\/?\/?w?w?w?\.?(discord\.gg|discordapp\.com\/invite|guilded\.gg|guilded\.com|guilded\.gg\/i|guilded\.com\/i)\/([\w/-]+)'
IMAGE_EMBED_REGEX = r'\!\[(.*?)\]\((.*?)\)'
USER_AGENT = 'Guilded Server Guard/1.0 (Image Check)'
LOGIN_CHANNEL_ID = '1f6fae7f-6cdf-403d-80b9-623a76f8b621'

MODELS_ROOT = bot_config.PROJECT_ROOT + '/project/ml_models'

API_KEY_REGEXES = [
    r'gapi_([a-zA-Z0-9+\/]{86})==',
]

filters = {
    'toxicity': {
        'vectorizer': joblib.load(MODELS_ROOT + '/toxicity/vectorizer.joblib'),
        'model': joblib.load(MODELS_ROOT + '/toxicity/model.joblib')
    },
    'hatespeech': {
        'vectorizer': joblib.load(MODELS_ROOT + '/hatespeech/vectorizer.joblib'),
        'model': joblib.load(MODELS_ROOT + '/hatespeech/model.joblib')
    }
}

filter_cache = Cache()
spam_cache = Cache(3)

def _get_prob(prob):
    return prob[1]

def apply_filter(filter: str, texts: list):
    new_texts = []
    for text in texts:
        new_texts.append(unidecode(text))
    if not filters.get(filter):
        raise Exception('Filter not found')
    f = filters[filter]
    return np.apply_along_axis(
        _get_prob, 1, f['model'].predict_proba(f['vectorizer'].transform(texts))
    )

def reset_filter_cache(guild_id):
    filter_cache.remove(guild_id)

def repeats(s):
    s = s.lower()

    words = s.split()
    uniqueWords = set(words)

    if len(uniqueWords) < round(len(words) * .35):
        return True

    for word in words:
        charCount = dict()
        unique = set(tuple(word))
        for char in word:
            if char in charCount:
                charCount[char] += 1
            else:
                charCount[char] = 1
        for key in charCount:
            if charCount[key] > len(unique) and len(unique) > 4:
                return True

    return False

class Moderation(commands.Cog):
    pass

class ModerationModule(Module):
    name = 'Moderation'

    def get_filter(self, guild_id):
        cached = filter_cache.get(guild_id)
        if cached:
            return cached
        guild_data: dict = self.get_guild_data(guild_id)
        list = guild_data.get('config', {}).get('filters', [])

        cached = Profanity(list)
        filter_cache.set(guild_id, cached)
        return cached

    def initialize(self):
        bot = self.bot

        self.bot_api = http.HTTPClient()
        self.bot_api.token = os.getenv('BOT_KEY')

        cog = Moderation()

        @bot.command()
        async def ban(_, ctx: commands.Context, target: str, timespan: str=None, *_reason):
            """[Moderator+] Ban a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target, True)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            reason = ' '.join(_reason)

            if timespan is not None:
                try:
                    timespan = parse_timespan(timespan)
                except:
                    reason = timespan + ' ' + reason
                    timespan = None
            
            if isinstance(user, User):
                # User not in server, schedule an automated ban once they join
                if timespan is not None:
                    requests.post(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/ban', json={
                        'issuer': ctx.author.id,
                        'reason': f'(User Prebanned By <@{ctx.author.id}>)\n{reason}',
                        'ends_at': datetime.now().timestamp() + timespan
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                else:
                    requests.post(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/ban', json={
                        'issuer': ctx.author.id,
                        'reason': f'(User Prebanned By <@{ctx.author.id}>)\n{reason}'
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                em = Embed(
                    title = await translate(curLang, 'command.ban.title'),
                    colour = Colour.orange()
                )
                em.set_thumbnail(url=user.display_avatar.aws_url)
                em.add_field(name=await translate(curLang, 'log.user'), value=user.mention)
                em.add_field(name=await translate(curLang, 'log.issuer'), value=ctx.author.mention)
                if timespan is not None:
                    em.add_field(name=await translate(curLang, 'log.lasts'), value=format_timespan(timespan))
                em.add_field(name=await translate(curLang, 'log.reason'), value=reason, inline=False)
                await ctx.reply(embed=em, silent=True)
                if logs_channel:
                    channel = await ctx.server.fetch_channel(logs_channel)
                    await channel.send(embed=em, silent=True)
                return

            if await self.is_moderator(user):
                await ctx.reply('This user is a moderator, I can\'t do that!')
                return
            
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            config = guild_data.get('config', {})
            logs_channel = config.get('action_logs_channel', config.get('logs_channel'))
            
            if user is not None:
                await user.ban(reason=reason)
                if timespan is not None:
                    requests.post(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/ban', json={
                        'issuer': ctx.author.id,
                        'reason': reason,
                        'ends_at': datetime.now().timestamp() + timespan
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                em = Embed(
                    title = await translate(curLang, 'command.ban.title'),
                    colour = Colour.orange()
                )
                em.set_thumbnail(url=user.display_avatar.aws_url)
                em.add_field(name=await translate(curLang, 'log.user'), value=user.mention)
                em.add_field(name=await translate(curLang, 'log.issuer'), value=ctx.author.mention)
                if timespan is not None:
                    em.add_field(name=await translate(curLang, 'log.lasts'), value=format_timespan(timespan))
                em.add_field(name=await translate(curLang, 'log.reason'), value=reason, inline=False)
                await ctx.reply(embed=em, silent=True)
                if logs_channel:
                    channel = await ctx.server.fetch_channel(logs_channel)
                    await channel.send(embed=em, silent=True)
        
        ban.cog = cog
        
        @bot.command()
        async def unban(_, ctx: commands.Context, target: str):
            """[Moderator+] Unban a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target, True)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error.user')))
                return

            await ctx.server.unban(user)
            requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/ban', headers={
                'authorization': bot_config.SECRET_KEY
            })
            await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, 'command.unban.success', {'name': user.name})))

        unban.cog = cog
        
        @bot.command()
        async def mute(_, ctx: commands.Context, target: str, timespan: str=None, *_reason):
            """[Moderator+] Mute a user"""
            await self.validate_permission_level(1, ctx)
            with BotAPI() as bot_api:
                user = await self.convert_member(ctx, target)

                user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                user_info = user_data_req.json()
                curLang = user_info.get('language', 'en')

                if user is None:
                    await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error.user')))
                    return

                if await self.is_moderator(user):
                    await ctx.reply('This user is a moderator, I can\'t do that!')
                    return

                guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                guild_data: dict = guild_data_req.json()
                config = guild_data.get('config', {})
                logs_channel = config.get('action_logs_channel', config.get('logs_channel'))

                reason = ' '.join(_reason)

                if timespan is not None:
                    try:
                        timespan = parse_timespan(timespan)
                    except:
                        reason = timespan + ' ' + reason
                        timespan = None
                
                if user is not None:
                    if config.get('mute_role'):
                        await bot_api.assign_role_to_member(ctx.server.id, user.id, config['mute_role'])
                    requests.post(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/mute', json={
                        'issuer': ctx.author.id,
                        'reason': reason,
                        'ends_at': timespan is not None and datetime.now().timestamp() + timespan or None
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    em = Embed(
                        title = await translate(curLang, 'command.mute.title'),
                        colour = Colour.orange()
                    )
                    em.set_thumbnail(url=user.display_avatar.aws_url)
                    em.add_field(name=await translate(curLang, 'log.user'), value=user.mention)
                    em.add_field(name=await translate(curLang, 'log.issuer'), value=ctx.author.mention)
                    if timespan is not None:
                        em.add_field(name=await translate(curLang, 'log.lasts'), value=format_timespan(timespan))
                    em.add_field(name=await translate(curLang, 'log.reason'), value=reason, inline=False)
                    await ctx.reply(embed=em, silent=True)
                    if logs_channel:
                        channel = await ctx.server.fetch_channel(logs_channel)
                        await channel.send(embed=em, silent=True)
        
        mute.cog = cog
        
        @bot.command()
        async def unmute(_, ctx: commands.Context, target: str):
            """[Moderator+] Unmute a user"""
            await self.validate_permission_level(1, ctx)
            with BotAPI() as bot_api:
                user = await self.convert_member(ctx, target)

                user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                user_info = user_data_req.json()
                curLang = user_info.get('language', 'en')

                if user is None:
                    await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error.user')))
                    return

                guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                guild_data: dict = guild_data_req.json()

                if guild_data.get('config', {}).get('mute_role'):
                    await bot_api.remove_role_from_member(ctx.server.id, user.id, guild_data['config']['mute_role'])
                requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/mute', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, 'command.unmute.success', {'mention': user.mention})))
        
        unmute.cog = cog

        @bot.command()
        async def purge(_, ctx: commands.Context, amount: str):
            """[Moderator+] Purge up to 50 messages in the current channel"""
            await self.validate_permission_level(1, ctx)

            try:
                amount = int(amount)

                messages = await ctx.channel.history(limit=amount)
                purged = 0
                for message in messages:
                    try:
                        await message.delete()
                        purged += 1
                    except:
                        pass

                await ctx.reply(embed=EMBED_SUCCESS(await translate(ctx.message.language, 'command.purge.results', {
                    'amount': str(purged),
                    'total': str(amount)
                })), private=True)
            except ValueError:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'command.error.number')), private=True)
        
        purge.cog = cog
        
        @bot.command()
        async def warn(_, ctx: commands.Context, target: str, timespan: str=None, *_reason):
            """[Moderator+] Warn a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            config = guild_data.get('config', {})
            logs_channel = config.get('action_logs_channel', config.get('logs_channel'))

            reason = ' '.join(_reason)

            if timespan is not None:
                try:
                    timespan = parse_timespan(timespan)
                except:
                    reason = timespan + ' ' + reason
                    timespan = None
            
            if user is not None:
                result = requests.post(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', json={
                    'issuer': ctx.author.id,
                    'reason': reason,
                    'ends_at': timespan is not None and datetime.now().timestamp() + timespan or None
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })
                em = Embed(
                    title = await translate(curLang, 'command.warn.title'),
                    colour = Colour.orange()
                )
                em.set_thumbnail(url=user.display_avatar.aws_url)
                em.add_field(name=await translate(curLang, 'log.user'), value=user.mention)
                em.add_field(name=await translate(curLang, 'log.issuer'), value=ctx.author.mention)
                if timespan is not None:
                    em.add_field(name=await translate(curLang, 'log.lasts'), value=format_timespan(timespan))
                em.add_field(name=await translate(curLang, 'log.reason'), value=reason, inline=False)
                await ctx.reply(embed=em, silent=True)
                if logs_channel:
                    channel = await ctx.server.fetch_channel(logs_channel)
                    await channel.send(embed=em, silent=True)
        
        warn.cog = cog
        
        @bot.command()
        async def warnings(_, ctx: commands.Context, target: str):
            """[Moderator+] Get a user's warnings"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error.user')))
                return

            result = requests.get(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', headers={
                'authorization': bot_config.SECRET_KEY
            })
            if result.status_code == 200:
                warns = result.json()
                em = Embed(
                    title = await translate(curLang, 'command.warnings.title', {'username': user.name}),
                    description = len(warns) > 0 and ''.join([f'{item["id"]} | <@{item["issuer"]}> - {item["reason"]}{item.get("when") and " - " + datetime.fromtimestamp(item["when"]).strftime("%b %d %Y at %H:%M %p %Z") or ""}\n' for item in warns['result']]) or await translate(curLang, 'command.warnings.none'),
                    colour = Colour.orange()
                )
                await ctx.reply(embed=em)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        warnings.cog = cog
        
        @bot.command()
        async def delwarn(_, ctx: commands.Context, target: str, id: str=None):
            """[Moderator+] Delete a user's warning(s)"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error.user')))
                return

            if id:
                result = requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings/{id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                em = Embed(
                    title = f'Deleted warning {id} for {user.name}',
                    description = await translate(curLang, 'command.delwarn.success', {'id': id, 'username': user.name}),
                    colour = Colour.green()
                )
                await ctx.reply(embed=result.status_code == 404 and EMBED_COMMAND_ERROR(await translate(curLang, 'command.delwarn.error', {'id': id, 'username': user.name})) or em)
            else:
                result = requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, 'command.delwarn.success.all', {'username': user.name})))
        
        delwarn.cog = cog
        
        @bot.command()
        async def userinfo(_, ctx: commands.Context, target: str):
            """[Moderator+] Get information on a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error.user')))
                return

            if user is not None:
                user = await ctx.server.fetch_member(user.id)
                role_ids = await user.fetch_role_ids()
                created_time = user.created_at.timestamp()
                diff = abs(datetime.now().timestamp() - created_time)
                em = Embed(
                    title=f'{user.name} ({user.id})',
                    description=f'{await translate(curLang, "userinfo.content", {"user_mention": user.mention})}. {await translate(curLang, user.nick is None and "userinfo.nickname.none" or "userinfo.nickname.has")}',
                    colour=Colour.gilded(),
                    url=user.profile_url
                ) \
                .set_thumbnail(url=user.avatar != None and user.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                em.add_field(name=await translate(curLang, 'userinfo.roles'), value=', '.join([f'<@{role}>' for role in role_ids]), inline=False)
                em.add_field(name=await translate(curLang, 'userinfo.creation'), value=user.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n' + f':warning: {await translate(curLang, "userinfo.recent")}' or ''))
                em.add_field(name=await translate(curLang, 'userinfo.joined'), value=user.joined_at.strftime("%b %d %Y at %H:%M %p %Z"))
                await ctx.reply(embed=em)
        
        userinfo.cog = cog
        
        @bot.command()
        async def reset_xp(_, ctx: commands.Context, *_target):
            """[Manage XP] Reset the XP of all mentioned users"""

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if (not await self.user_can_manage_xp(ctx.author)) and not ctx.author.id == ctx.server.owner_id:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.reset_xp.error')))
                return
            
            reset_members = []

            for user in ctx.message.mentions:
                try:
                    member = await ctx.server.getch_member(user.id)
                    await member.edit(xp=0)
                    reset_members.append(member)
                except Exception as e:
                    pass
            NEWLINE = '\n'
            await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, 'command.reset_xp.success', {"mentions": NEWLINE.join([member.mention for member in reset_members])})))
        
        reset_xp.cog = cog
        
        async def on_member_join(event: MemberJoinEvent):
            member = await event.server.getch_member(event.member.id)

            await self._update_guild_data(event.server_id)

            with BotAPI() as bot_api:
                guild_data_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                guild_data: dict = guild_data_req.json()
                config = guild_data.get('config', {})

                mute_req = requests.get(f'http://localhost:5000/moderation/{event.server_id}/{member.id}/mute', headers={
                    'authorization': bot_config.SECRET_KEY
                })

                ban_req = requests.get(f'http://localhost:5000/moderation/{event.server.id}/{member.id}/ban', headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if mute_req.status_code == 200:
                    if config.get('mute_role'):
                        await bot_api.assign_role_to_member(event.server_id, member.id, config['mute_role'])
                
                if ban_req.status_code == 200:
                    data: dict = ban_req.json()
                    print(ban_req.text)
                    await member.ban(reason=data.get('reason', f'A ban for this user was sheduled by user with ID "{data["issuer"]}"'))
                
                traffic_log_channel = config.get('traffic_logs_channel')

                if traffic_log_channel is not None and traffic_log_channel != '':
                    created_time = member.created_at.timestamp()
                    diff = abs(datetime.now().timestamp() - created_time)
                    em = Embed(
                        title=f'{member.name} joined the server',
                        url=member.profile_url,
                        colour=Colour.gilded()
                    )
                    em.set_thumbnail(url=member.avatar is not None and member.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                    em.add_field(name='User ID', value=member.id)
                    em.add_field(name='Account created', value=member.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                    em.add_field(name='Account joined', value=member.joined_at.strftime("%b %d %Y at %H:%M %p %Z"))
                    if config.get('toxicity', 0) > 0:
                        toxicity_proba_name = round(apply_filter('toxicity', [member.name])[0] * 100)
                        em.add_field(name='Profile Toxicity', value=f'{toxicity_proba_name}%')
                    if config.get('hatespeech', 0) > 0:
                        hatespeech_proba_name = round(apply_filter('hatespeech', [member.name])[0] * 100)
                        em.add_field(name='Profile Hate-Speech', value=f'{hatespeech_proba_name}%')
                    channel = await bot.getch_channel(traffic_log_channel)
                    await channel.send(embed=em)
        
        bot.join_listeners.append(on_member_join)

        async def on_member_remove(event: MemberRemoveEvent):
            await self._update_guild_data(event.server_id)
            if event.banned:
                return
            member = await bot.getch_user(event.user_id)

            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            traffic_log_channel = config.get('traffic_logs_channel')

            if traffic_log_channel is not None and traffic_log_channel != '':
                if member.created_at is not None:
                    created_time = member.created_at.timestamp()
                    diff = abs(datetime.now().timestamp() - created_time)
                em = Embed(
                    title=event.kicked and f'{member.name} was kicked' or f'{member.name} left the server',
                    url=member.profile_url,
                    colour=event.kicked and Colour.red() or Colour.gilded()
                )
                em.set_thumbnail(url=member.avatar is not None and member.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                em.add_field(name='User ID', value=member.id)
                if member.created_at is not None:
                    em.add_field(name='Account created', value=member.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                channel = await bot.getch_channel(traffic_log_channel)
                await channel.send(embed=em)
        
        bot.leave_listeners.append(on_member_remove)

        async def on_ban_create(event: BanCreateEvent):
            ban_info = event.ban
            member = await bot.getch_user(ban_info.user.id)

            guild_data: dict = self.get_guild_data(event.server_id)
            traffic_log_channel = guild_data.get('config', {}).get('traffic_logs_channel')

            if traffic_log_channel is not None and traffic_log_channel != '':
                if member.created_at is not None:
                    created_time = member.created_at.timestamp()
                    diff = abs(datetime.now().timestamp() - created_time)
                em = Embed(
                    title=f'{member.name} has been banned',
                    url=member.profile_url,
                    colour=Colour.red()
                )
                em.set_thumbnail(url=member.avatar is not None and member.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                em.add_field(name='User ID', value=member.id)
                if member.created_at is not None:
                    em.add_field(name='Account created', value=member.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                em.add_field(name='Banned by', value=ban_info.author.mention, inline=True)
                em.add_field(name='Ban Reason', value=ban_info.reason, inline=False)
                channel = await bot.getch_channel(traffic_log_channel)
                await channel.send(embed=em)
        
        bot.ban_create_listeners.append(on_ban_create)

        async def on_ban_delete(event: BanDeleteEvent):
            ban_info = event.ban
            member = await bot.getch_user(ban_info.user.id)

            guild_data: dict = self.get_guild_data(event.server_id)
            traffic_log_channel = guild_data.get('config', {}).get('traffic_logs_channel')

            if traffic_log_channel is not None and traffic_log_channel != '':
                if member.created_at is not None:
                    created_time = member.created_at.timestamp()
                    diff = abs(datetime.now().timestamp() - created_time)
                em = Embed(
                    title=f'{member.name} has been unbanned',
                    url=member.profile_url,
                    colour=Colour.green()
                )
                em.set_thumbnail(url=member.avatar is not None and member.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                em.add_field(name='User ID', value=member.id)
                if member.created_at is not None:
                    em.add_field(name='Account created', value=member.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                em.add_field(name='Banned by', value=ban_info.author.mention, inline=True)
                em.add_field(name='Ban Reason', value=ban_info.reason, inline=False)
                channel = await bot.getch_channel(traffic_log_channel)
                await channel.send(embed=em)
        
        bot.ban_delete_listeners.append(on_ban_delete)

        async def handle_text_message(message):
            await self._update_guild_data(message.server_id)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{message.server_id}/{message.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            guild_data: dict = self.get_guild_data(message.server_id)
            config = guild_data.get('config', {})
            custom_filter = config.get('filters')
            logs_channel_id = config.get('automod_logs_channel')
            trusted = await self.is_trusted(message.author)
            if logs_channel_id:
                logs_channel = await bot.getch_channel(logs_channel_id)
            else:
                logs_channel = None
            if config.get('automod_duplicate', 0) == 1 and len(message.content) > 5:
                if repeats(message.content):
                    if isinstance(message, ChatMessage):
                        await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.duplicate_text')), private=True)
                    try:
                        await message.delete()
                    except Forbidden:
                        await message.reply(embed=EMBED_DENIED(
                            title='Permissions Error',
                            description='Server Guard encountered a permissions error while trying to delete the messages.'
                        ), private=True)
                    message.automoderated = True
                    return True

            if config.get('url_filter', 0) == 1:
                for url in malicious_urls.keys():
                    if url in message.content:
                        if isinstance(message, ChatMessage):
                            await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.malicious_url')), private=True)
                        try:
                            await message.delete()
                        except Forbidden:
                            await message.reply(embed=EMBED_DENIED(
                                title='Permissions Error',
                                description='Server Guard encountered a permissions error while trying to delete the messages.'
                            ), private=True)
                        if logs_channel is not None:
                            await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                                title='Malicious URL Detected',
                                description=message.content,
                                url=message.share_url,
                                colour = Colour.red(),
                            ).add_field(name='Threat Category', inline=False)\
                            .add_field(name='User', value=f'[{message.author.name}]({message.author.profile_url})'))
                        return True
            
            if config.get('filter_api_keys', 0) == 1:
                for pattern in API_KEY_REGEXES:
                    match = re.match(pattern, message.content)
                    if match is not None:
                        if isinstance(message, ChatMessage):
                            await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.api_key')), private=True)
                        try:
                            await message.delete()
                        except Forbidden:
                            await message.reply(embed=EMBED_DENIED(
                                title='Permissions Error',
                                description='Server Guard encountered a permissions error while trying to delete the messages.'
                            ), private=True)
                        if logs_channel is not None:
                            await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                                title='API Key Detected',
                                description=message.content.replace(match.group(0), '[REDACTED]'),
                                url=message.share_url,
                                colour = Colour.red(),
                            ).add_field(name='User', value=f'[{message.author.name}]({message.author.profile_url})'))
                        return True

            if config.get('invite_link_filter', 0) == 1:
                for domain, invite in re.findall(SERVER_INVITE_REGEX, message.content):
                    lowered = invite.lower()
                    if '/' in invite and not 'i/' in lowered and not 'r/' in lowered:
                        continue
                    stop = False
                    for path in guilded_paths:
                        if path in lowered:
                            stop = True
                            break
                    if stop:
                        continue
                    if isinstance(message, ChatMessage):
                        await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.invite_link')), private=True)
                    try:
                        await message.delete()
                    except Forbidden:
                        await message.reply(embed=EMBED_DENIED(
                            title='Permissions Error',
                            description='Server Guard encountered a permissions error while trying to delete the messages.'
                        ), private=True)
                    if logs_channel is not None:
                        await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                            title='Invite Linked Detected',
                            description=message.content,
                            url=message.share_url,
                            colour = Colour.red(),
                        ).add_field(name='Invite Link', value='https://www.' + domain + '/' + invite, inline=False)\
                        .add_field(name='User', value=f'[{message.author.name}]({message.author.profile_url})'))
                    message.automoderated = True
                    return True
            
            if config.get('toxicity', 0) > 0:
                toxicity_proba = apply_filter('toxicity', [message.content])[0] * 100
            else:
                toxicity_proba = 0
            if config.get('hatespeech', 0) > 0:
                hatespeech_proba = apply_filter('hatespeech', [message.content])[0] * 100
            else:
                hatespeech_proba = 0
            
            hit_filter = False
            if config.get('toxicity', 0) > 0 and toxicity_proba >= config.get('toxicity', 0):
                if isinstance(message, ChatMessage):
                    await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.toxicity')),private=True)
                try:
                    await message.delete()
                except Forbidden:
                    await message.reply(embed=EMBED_DENIED(
                        title='Permissions Error',
                        description='Server Guard encountered a permissions error while trying to delete the messages.'
                    ), private=True)
                hit_filter = True
            if config.get('hatespeech', 0) > 0 and hatespeech_proba >= config.get('hatespeech', 0):
                if isinstance(message, ChatMessage):
                    await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.hatespeech')),private=True)
                try:
                    await message.delete()
                except Forbidden:
                    await message.reply(embed=EMBED_DENIED(
                        title='Permissions Error',
                        description='Server Guard encountered a permissions error while trying to delete the messages.'
                    ), private=True)
                hit_filter = True
            if max(toxicity_proba, hatespeech_proba) >= 50:
                if logs_channel is not None:
                    which = toxicity_proba >= 50 and 'Toxicity' or 'Hate Speech'
                    await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                        title=f'{which} Filter Triggered',
                        description=message.content,
                        url=message.share_url,
                        colour = Colour.orange(),
                    ).set_footer(text=f'Certainty: {round(max(toxicity_proba, hatespeech_proba))}%').add_field(name='User', value=message.author.name))
            if hit_filter:
                message.automoderated = True
                return True
            if custom_filter is not None and len(custom_filter) > 0:
                filter = self.get_filter(message.server_id)
                if filter.contains_profanity(message.content):
                    if isinstance(message, ChatMessage):
                        await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.blacklist')),private=True)
                    try:
                        await message.delete()
                    except Forbidden:
                        await message.reply(embed=EMBED_DENIED(
                            title='Permissions Error',
                            description='Server Guard encountered a permissions error while trying to delete the messages.'
                        ), private=True)
                    if logs_channel is not None:
                        await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                            title='Blacklisted Word Filter Triggered',
                            description=message.content,
                            url=message.share_url,
                            colour = Colour.orange(),
                        ).add_field(name='User', value=message.author.name).add_field(name='Filtered Message', value=filter.censor(message.content), inline=False))
            if trusted is False:
                untrusted_block_images = config.get('untrusted_block_images', False)
                if untrusted_block_images:
                    for _, link in re.findall(r'\[(.*?)\]\((.*?)\)', message.content):
                        if link.startswith('https://media.tenor.com/') and not '@' in link:
                            continue
                        if re.search(r'.+(\.(jpe?g?|jif|jfif?|png|gif|bmp|dib|webp|tiff?|raw|arw|cr2|nrw|k25|heif|heic|indd?|indt|jp2|j2k|jpf|jpx|jpm|mj2|svgz?|ai|eps))', link):
                            if isinstance(message, ChatMessage):
                                await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.trusted.image')), private=True)
                            try:
                                await message.delete()
                            except Forbidden:
                                await message.reply(embed=EMBED_DENIED(
                                    title='Permissions Error',
                                    description='Server Guard encountered a permissions error while trying to delete the messages.'
                                ), private=True)
                            message.automoderated = True
                            return True
                        try:
                            head_req = requests.head(link, headers={
                                'user-agent': USER_AGENT
                            })
                            if head_req.status_code == 200:
                                content_type = head_req.headers.get('content-type')
                                content_disposition = head_req.headers.get('content-disposition')
                                blocked = False
                                if 'image' in content_type or re.search(r'.+(\.(jpe?g?|jif|jfif?|png|gif|bmp|dib|webp|tiff?|raw|arw|cr2|nrw|k25|heif|heic|indd?|indt|jp2|j2k|jpf|jpx|jpm|mj2|svgz?|ai|eps))', content_disposition):
                                    blocked = True
                                elif 'html' in content_type:
                                    page_req = requests.get(link, headers={
                                        'user-agent': USER_AGENT
                                    })
                                    if page_req.status_code == 200:
                                        parsed_html = BeautifulSoup(page_req.text)
                                        for tag in parsed_html('meta', attrs={'property': ['og:image', 'twitter:image', 'twitter:image:src']}):
                                            blocked = True
                                        for tag in parsed_html('meta', attrs={'property': ['og:type']}):
                                            og_type: str = tag['content'].lower().strip()
                                            if og_type.startswith(('article', 'website', 'book', 'profile', 'video', 'music')):
                                                blocked = False
                                        for tag in parsed_html('meta', attrs={'property': ['og:description']}):
                                            desc: str = tag['content'].lower().strip()
                                            if 'screenshot' in desc or '':
                                                blocked = False
                                        for tag in parsed_html('meta', attrs={'name': ['description']}):
                                            desc: str = tag['content'].lower().strip()
                                            if 'screenshot' in desc or '':
                                                blocked = False
                                        for tag in parsed_html('meta', attrs={'name': ['keywords']}):
                                            keywords: str = tag['content'].lower()
                                            if 'photo' in keywords or 'image upload' in keywords or 'image hosting' in keywords:
                                                blocked = True
                                            if 'video' in keywords or not 'image' in keywords:
                                                blocked = False
                                if blocked is True:
                                    if isinstance(message, ChatMessage):
                                        await message.reply(embed=EMBED_FILTERED(message.author, await translate(curLang, 'filter.trusted.image')), private=True)
                                    try:
                                        await message.delete()
                                    except Forbidden:
                                        await message.reply(embed=EMBED_DENIED(
                                            title='Permissions Error',
                                            description='Server Guard encountered a permissions error while trying to delete the messages.'
                                        ), private=True)
                                    message.automoderated = True
                                    return True
                        except:
                            pass
            return False

        async def on_message_update(event: MessageUpdateEvent):
            if event.after.author.bot:
                return
            member = await event.server.getch_member(event.after.author.id)
            event.after.automoderated = False
            if (await self.is_moderator(member)) == False and (await self.user_can_manage_server(member)) == False:
                if await handle_text_message(event.after):
                    return

            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                channel = await bot.getch_channel(message_log_channel)
                member = event.after.author
                em = Embed(
                    title=f'Message edited in {event.after.channel.name or (await bot.getch_channel(event.after.channel_id)).name}',
                    url=event.after.share_url,
                    colour=Colour.gilded(),
                    timestamp=datetime.now()
                )
                em.add_field(name='User', value=member.mention)
                em.add_field(name='ID', value=member.id)
                if event.before is not None:
                    em.add_field(name='Before', value=event.before.content, inline=False)
                em.add_field(name='After', value=event.after.content, inline=False)
                em.set_thumbnail(url=member.avatar.aws_url)
                await channel.send(embed=em, silent=True)
        
        bot.message_update_listeners.append(on_message_update)

        async def on_message_delete(event: MessageDeleteEvent):
            if not event.message:
                return
            if event.message.author.bot or event.channel_id == LOGIN_CHANNEL_ID:
                return
            try:
                if getattr(event.message, 'automoderated', False):
                    # This message was handled by automod and deleted, don't log it as it should already be logged in the automod logs
                    return
            except:
                # Just continue in this case
                pass
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                if event.message is None:
                    return # Don't process if the message doesn't exist in cache
                channel = await bot.getch_channel(message_log_channel)
                member = event.message.author
                em = Embed(
                    title=f'Message deleted in {event.message.channel.name or (await bot.getch_channel(event.message.channel_id)).name}',
                    url=event.message.share_url,
                    colour=event.private and Colour.purple() or Colour.red(),
                    timestamp=event.deleted_at
                )
                em.add_field(name='User', value=member.mention)
                em.add_field(name='ID', value=member.id)
                em.add_field(name='Deleted message contents', value=event.message.content, inline=False)
                em.set_thumbnail(url=member.avatar.aws_url)

                img = re.search(IMAGE_EMBED_REGEX, event.message.content)
                if img:
                    em.set_image(url=img.group(2))

                await channel.send(embed=em, silent=True)
        
        bot.message_delete_listeners.append(on_message_delete)

        async def on_message(message: ChatMessage):
            if message.author.bot:
                return
            member = await message.guild.getch_member(message.author.id)
            message.automoderated = False
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(message):
                return
            guild_data: dict = self.get_guild_data(message.server_id)
            config = guild_data.get('config', {})
            
            if config.get('automod_spam', 0) > 0:
                cached_spam = spam_cache.get(f'{message.guild.id}/{message.author_id}')
                if cached_spam is None:
                    cached_spam = []
                if len(cached_spam) >= config.get('automod_spam'):
                    await message.reply(embed=EMBED_FILTERED(message.author, 'Talking too fast!'), private=True)
                    try:
                        await message.delete()
                        for item in cached_spam:
                            await item.delete()
                    except Forbidden:
                        await message.reply(embed=EMBED_DENIED(
                            title='Permissions Error',
                            description='Server Guard encountered a permissions error while trying to delete the messages.'
                        ), private=True)
                    cached_spam = []
                    spam_cache.set(f'{message.guild.id}/{message.author_id}', cached_spam)
                    return
                else:
                    cached_spam.append(message)
                    spam_cache.set(f'{message.guild.id}/{message.author_id}', cached_spam)
        bot.message_listeners.append(on_message)

        async def on_forum_topic_create(event: ForumTopicCreateEvent):
            if event.topic.author.bot:
                return
            member = await event.server.getch_member(event.topic.author.id)
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(event.topic):
                return
        bot.topic_create_listeners.append(on_forum_topic_create)

        async def on_forum_topic_update(event: ForumTopicUpdateEvent):
            if event.topic.author.bot:
                return
            member = await event.server.getch_member(event.topic.author.id)
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(event.topic):
                return
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                channel = await bot.getch_channel(message_log_channel)
                member = event.after.author
                em = Embed(
                    title=f'Message edited in {event.after.channel.name}',
                    url=event.after.share_url,
                    colour=Colour.gilded(),
                    timestamp=datetime.now()
                )
                em.add_field(name='User', value=member.mention)
                em.add_field(name='ID', value=member.id)
                em.add_field(name='Edited topic title', value=event.topic.title, inline=False)
                em.add_field(name='Edited topic contents', value=event.topic.content, inline=False)
                em.set_thumbnail(url=member.display_avatar.aws_url)
                await channel.send(embed=em)
        bot.topic_update_listeners.append(on_forum_topic_update)

        async def on_forum_topic_delete(event: ForumTopicDeleteEvent):
            if event.topic.author.bot:
                return
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                if event.topic is not None:
                    channel = await bot.getch_channel(message_log_channel)
                    member = event.topic.author
                    em = Embed(
                        title=f'Forum topic deleted in {event.topic.channel.name}',
                        url=event.topic.share_url,
                        colour=Colour.red(),
                        timestamp=datetime.now()
                    )
                    em.add_field(name='User', value=member.mention)
                    em.add_field(name='ID', value=member.id)
                    em.add_field(name='Deleted topic title', value=event.topic.title, inline=False)
                    em.add_field(name='Deleted topic contents', value=event.topic.content, inline=False)
                    em.set_thumbnail(url=member.display_avatar.aws_url)
                    await channel.send(embed=em)
        bot.topic_delete_listeners.append(on_forum_topic_delete)

        async def on_forum_topic_reply_create(event: ForumTopicReplyCreateEvent):
            if event.reply.author.bot:
                return
            member = await event.server.getch_member(event.reply.author_id)
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(event.reply):
                return
        bot.topic_reply_create_listeners.append(on_forum_topic_reply_create)

        async def on_forum_topic_reply_update(event: ForumTopicReplyUpdateEvent):
            if event.reply.author.bot:
                return
            member = await event.server.getch_member(event.reply.author_id)
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(event.reply):
                return
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                channel = await bot.getch_channel(message_log_channel)
                member = event.reply.author
                em = Embed(
                    title=f'Topic reply  edited in {event.reply.channel.name}',
                    url=event.topic.share_url,
                    colour=Colour.gilded(),
                    timestamp=datetime.now()
                )
                em.add_field(name='User', value=member.mention)
                em.add_field(name='ID', value=member.id)
                em.add_field(name='Topic title', value=event.topic.title, inline=False)
                em.add_field(name='Edited reply contents', value=event.reply.content, inline=False)
                em.set_thumbnail(url=member.display_avatar.aws_url)
                await channel.send(embed=em)
        bot.topic_reply_update_listeners.append(on_forum_topic_reply_update)

        async def on_forum_topic_reply_delete(event: ForumTopicReplyDeleteEvent):
            if event.reply.author.bot:
                return
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                if event.reply is not None:
                    channel = await bot.getch_channel(message_log_channel)
                    member = event.reply.author
                    em = Embed(
                        title=f'Topic reply deleted in {event.reply.channel.name}',
                        url=event.topic.share_url,
                        colour=Colour.red(),
                        timestamp=datetime.now()
                    )
                    em.add_field(name='User', value=member.mention)
                    em.add_field(name='ID', value=member.id)
                    em.add_field(name='Topic title', value=event.topic.title, inline=False)
                    em.add_field(name='Deleted reply contents', value=event.reply.content, inline=False)
                    em.set_thumbnail(url=member.display_avatar.aws_url)
                    await channel.send(embed=em)
        bot.topic_reply_delete_listeners.append(on_forum_topic_reply_delete)

        async def on_announcement_reply_create(event: AnnouncementReplyCreateEvent):
            if event.reply.author.bot:
                return
            member = await event.server.getch_member(event.reply.author_id)
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(event.reply):
                return
        bot.announcement_reply_create_listeners.append(on_announcement_reply_create)
        
        async def on_announcement_reply_update(event: AnnouncementReplyUpdateEvent):
            if event.reply.author.bot:
                return
            if await handle_text_message(event.reply):
                return
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                channel = await bot.getch_channel(message_log_channel)
                member = event.reply.author
                em = Embed(
                    title=f'Announcement reply edited in {event.reply.channel.name}',
                    url=event.announcement.share_url,
                    colour=Colour.gilded(),
                    timestamp=datetime.now()
                )
                em.add_field(name='User', value=member.mention)
                em.add_field(name='ID', value=member.id)
                em.add_field(name='Announcement title', value=event.announcement.title, inline=False)
                em.add_field(name='Edited reply contents', value=event.reply.content, inline=False)
                em.set_thumbnail(url=member.display_avatar.aws_url)
                await channel.send(embed=em)
        bot.announcement_reply_update_listeners.append(on_announcement_reply_update)
        
        async def on_announcement_reply_delete(event: AnnouncementReplyDeleteEvent):
            if event.reply.author.bot:
                return
            if event.reply is not None:
                guild_data: dict = self.get_guild_data(event.server_id)
                message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

                if message_log_channel is not None and message_log_channel != '':
                    channel = await bot.getch_channel(message_log_channel)
                    member = event.reply.author
                    em = Embed(
                        title=f'Announcement reply deleted in {event.reply.channel.name}',
                        url=event.announcement.share_url,
                        colour=Colour.red(),
                        timestamp=datetime.now()
                    )
                    em.add_field(name='User', value=member.mention)
                    em.set_thumbnail(url=member.display_avatar.aws_url)
                    await channel.send(embed=em)
        bot.announcement_reply_delete_listeners.append(on_announcement_reply_delete)

        async def on_bulk_member_roles_update(event: BulkMemberRolesUpdateEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            user_log_channel = config.get('user_logs_channel')

            if user_log_channel is not None and user_log_channel != '':
                channel = await bot.getch_channel(user_log_channel)
                if config.get('log_role_changes'):
                    for member_after in event.after:
                        member_before = None
                        for before in event.before:
                            if before.id == member_after.id:
                                member_before = before
                                break
                        if member_before:
                            added, removed = [], []
                            for role in member_before._role_ids:
                                if role not in member_after._role_ids:
                                    removed.append(role)
                            for role in member_after._role_ids:
                                if role not in member_before._role_ids:
                                    added.append(role)
                            # Generate log embed
                            em = Embed(
                                title=f'Roles changed for <@{member_after.id}>',
                                colour=Colour.gilded(),
                                timestamp=datetime.now(),
                                url=member_after.profile_url
                            ) \
                                .set_thumbnail(url=member_after.display_avatar.aws_url)
                            if len(added) > 0:
                                em.add_field(name='Added roles', value=', '.join([f'<@{role}>' for role in added]))
                            if len(removed) > 0:
                                em.add_field(name='Removed roles', value=', '.join([f'<@{role}>' for role in removed]))
                            
                            if len(removed) > 0 or len(added) > 0:
                                await channel.send(embed=em, silent=True)
        bot.member_role_update_listeners.append(on_bulk_member_roles_update)

        async def on_server_channel_create(event: ServerChannelCreateEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            mgmt_log_channel = config.get('management_logs_channel')

            if mgmt_log_channel is not None and mgmt_log_channel != '':
                channel = await bot.getch_channel(mgmt_log_channel)
                em = Embed(
                    title=f'Channel "{event.channel.name}" created',
                    url=event.channel.share_url,
                    colour=Colour.green(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=em)
        bot.channel_create_listeners.append(on_server_channel_create)
        
        async def on_server_channel_update(event: ServerChannelUpdateEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            mgmt_log_channel = config.get('management_logs_channel')

            if mgmt_log_channel is not None and mgmt_log_channel != '':
                channel = await bot.getch_channel(mgmt_log_channel)
                em = Embed(
                    title=f'Channel "{event.channel.name}" updated',
                    url=event.channel.share_url,
                    colour=Colour.gilded(),
                    timestamp=event.channel.created_at
                )
                await channel.send(embed=em)
        bot.channel_update_listeners.append(on_server_channel_update)
        
        async def on_server_channel_delete(event: ServerChannelDeleteEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            mgmt_log_channel = config.get('management_logs_channel')

            if mgmt_log_channel is not None and mgmt_log_channel != '':
                channel = await bot.getch_channel(mgmt_log_channel)
                em = Embed(
                    title=f'Channel "{event.channel.name}" deleted',
                    url=event.channel.share_url,
                    colour=Colour.red(),
                    timestamp=datetime.now()
                )
                await channel.send(embed=em)
        bot.channel_delete_listeners.append(on_server_channel_delete)

        # TODO: Translate these events into callback handlers in init
        @bot.event
        async def on_webhook_create(event: WebhookCreateEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            mgmt_log_channel = config.get('management_logs_channel')

            if mgmt_log_channel is not None and mgmt_log_channel != '':
                channel = await bot.getch_channel(mgmt_log_channel)
                em = Embed(
                    title=f'Webhook created in {event.webhook.channel.name}',
                    url=event.webhook.channel.share_url,
                    colour=Colour.gilded(),
                    timestamp=event.webhook.created_at
                ) \
                    .set_thumbnail(url=event.webhook.display_avatar.aws_url) \
                    .add_field(name='Created By',  value=f'<@{event.webhook.created_by_id}>')
                await channel.send(embed=em)

        @bot.event
        async def on_webhook_update(event: WebhookUpdateEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            mgmt_log_channel = config.get('management_logs_channel')

            if mgmt_log_channel is not None and mgmt_log_channel != '':
                channel = await bot.getch_channel(mgmt_log_channel)
                em = Embed(
                    title=f'Webhook {event.webhook.deleted_at and "deleted" or "updated"} in {event.webhook.channel.name}',
                    url=event.webhook.channel.share_url,
                    colour=Colour.gilded(),
                    timestamp=event.webhook.deleted_at or event.webhook.created_at
                ) \
                    .set_thumbnail(url=event.webhook.display_avatar.aws_url) \
                    .add_field(name='Created By',  value=f'<@{event.webhook.created_by_id}>')
                await channel.send(embed=em)