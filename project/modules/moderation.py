from datetime import datetime
import re
from project.helpers.embeds import *
from project.helpers.images import *
from project.helpers.Cache import Cache
from project.modules.base import Module
from project import bot_config, bot_api, malicious_urls
from guilded.ext import commands
from guilded import Embed, Colour, MemberJoinEvent, MemberRemoveEvent, BanCreateEvent, BanDeleteEvent, MessageUpdateEvent, MessageDeleteEvent, ForumTopicCreateEvent, ForumTopicDeleteEvent, ForumTopicUpdateEvent, ChatMessage, ForumTopic, http
from humanfriendly import parse_timespan, format_timespan
from better_profanity import Profanity
from unidecode import unidecode

import os
import requests
import aiohttp
import joblib
import numpy as np

user_converter = commands.UserConverter()

SERVER_INVITE_REGEX = r'h?t?t?p?s?:?\/?\/?w?w?w?\.?(discord\.gg|discordapp\.com\/invite|guilded\.gg|guilded\.com|guilded\.gg\/i|guilded\.com\/i)\/([\w/-]+)'
IMAGE_EMBED_REGEX = r'\!\[(.*?)\]\((.*?)\)'
USER_AGENT = 'Guilded Server Guard/1.0 (Image Check)'

MODELS_ROOT = bot_config.PROJECT_ROOT + '/project/ml_models'

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
            user = await self.convert_member(ctx, target)

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
                    title = 'Ban Issued',
                    colour = Colour.orange()
                )
                em.add_field(name='User', value=user.name)
                em.add_field(name='Issued By', value=ctx.author.name)
                if timespan is not None:
                    em.add_field(name='Lasts', value=format_timespan(timespan))
                em.add_field(name='Reason', value=reason, inline=False)
                await ctx.reply(embed=em)
                if logs_channel:
                    channel = await ctx.server.fetch_channel(logs_channel)
                    await channel.send(embed=em)
        
        ban.cog = cog
        
        @bot.command()
        async def unban(_, ctx: commands.Context, target: str):
            """[Moderator+] Unban a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target, True)

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            await ctx.server.unban(user)
            requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/ban', headers={
                'authorization': bot_config.SECRET_KEY
            })
            await ctx.reply(embed=EMBED_SUCCESS(f'{user.name} was unbanned'))

        unban.cog = cog
        
        @bot.command()
        async def mute(_, ctx: commands.Context, target: str, timespan: str=None, *_reason):
            """[Moderator+] Mute a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            bot_api.session = aiohttp.ClientSession()

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
                    title = 'Mute Issued',
                    colour = Colour.orange()
                )
                em.add_field(name='User', value=user.name)
                em.add_field(name='Issued By', value=ctx.author.name)
                if timespan is not None:
                    em.add_field(name='Lasts', value=format_timespan(timespan))
                em.add_field(name='Reason', value=reason, inline=False)
                await ctx.reply(embed=em)
                if logs_channel:
                    channel = await ctx.server.fetch_channel(logs_channel)
                    await channel.send(embed=em)
            await bot_api.session.close()
        
        mute.cog = cog
        
        @bot.command()
        async def unmute(_, ctx: commands.Context, target: str):
            """[Moderator+] Unmute a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            bot_api.session = aiohttp.ClientSession()

            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()

            if guild_data.get('config', {}).get('mute_role'):
                await bot_api.remove_role_from_member(ctx.server.id, user.id, guild_data['config']['mute_role'])
            requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/mute', headers={
                'authorization': bot_config.SECRET_KEY
            })
            await ctx.reply(embed=EMBED_SUCCESS(f'{user.mention} was unmuted'))
            await bot_api.session.close()
        
        unmute.cog = cog
        
        @bot.command()
        async def warn(_, ctx: commands.Context, target: str, timespan: str=None, *_reason):
            """[Moderator+] Warn a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

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
                    title = 'Warning Issued',
                    colour = Colour.orange()
                )
                em.add_field(name='User', value=user.name)
                em.add_field(name='Issued By', value=ctx.author.name)
                if timespan is not None:
                    em.add_field(name='Lasts', value=format_timespan(timespan))
                em.add_field(name='Reason', value=reason, inline=False)
                await ctx.reply(embed=em)
                if logs_channel:
                    channel = await ctx.server.fetch_channel(logs_channel)
                    await channel.send(embed=em)
        
        warn.cog = cog
        
        @bot.command()
        async def warnings(_, ctx: commands.Context, target: str):
            """[Moderator+] Get a user's warnings"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            result = requests.get(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', headers={
                'authorization': bot_config.SECRET_KEY
            })
            if result.status_code == 200:
                warns = result.json()
                em = Embed(
                    title = f'Warnings for {user.name}',
                    description = len(warns) > 0 and ''.join([f'{item["id"]} | <@{item["issuer"]}> - {item["reason"]}{item.get("when") and " - " + datetime.fromtimestamp(item["when"]).strftime("%b %d %Y at %H:%M %p %Z") or ""}\n' for item in warns['result']]) or 'This user has no warnings',
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

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            if id:
                result = requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings/{id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                em = Embed(
                    title = f'Deleted warning {id} for {user.name}',
                    description = f'Successfully cleared warning {id} for {user.name}',
                    colour = Colour.green()
                )
                await ctx.reply(embed=result.status_code == 404 and EMBED_COMMAND_ERROR(f'A warning with id {id} for user {user.name} does not exist') or em)
            else:
                result = requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                await ctx.reply(embed=EMBED_SUCCESS(f'Successfully cleared all warnings for {user.name}!'))
        
        delwarn.cog = cog
        
        @bot.command()
        async def userinfo(_, ctx: commands.Context, target: str):
            """[Moderator+] Get information on a user"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            if user is None:
                await ctx.reply(private=True, embed=EMBED_COMMAND_ERROR('Please specify a valid user!'))
                return

            if user is not None:
                user = await ctx.server.fetch_member(user.id)
                role_ids = await user.fetch_role_ids()
                created_time = user.created_at.timestamp()
                diff = abs(datetime.now().timestamp() - created_time)
                em = Embed(
                    title=f'{user.name} ({user.id})',
                    description=f'Information about the user {user.mention}. {user.nick is not None and f"They have the nickname {user.nick}" or "They do not have a nickname."}',
                    colour=Colour.gilded(),
                    url=user.profile_url
                ) \
                .set_thumbnail(url=user.avatar.aws_url)
                em.add_field(name='Roles', value=', '.join([f'<@{role}>' for role in role_ids]), inline=False)
                em.add_field(name='Account created', value=user.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                em.add_field(name='Joined at', value=user.joined_at.strftime("%b %d %Y at %H:%M %p %Z"))
                await ctx.reply(embed=em)
        
        userinfo.cog = cog
        
        @bot.command()
        async def reset_xp(_, ctx: commands.Context, *_target):
            """[Manage XP] Reset the XP of all mentioned users"""
            if (not await self.user_can_manage_xp(ctx.author)) and not ctx.author.id == ctx.server.owner_id:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('You need to be able to manage XP to use this command!'))
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
            await ctx.reply(embed=EMBED_SUCCESS(f'The levels of the following users have been reset:{NEWLINE}{NEWLINE.join([member.mention for member in reset_members])}'))
        
        reset_xp.cog = cog
        
        async def on_member_join(event: MemberJoinEvent):
            member = await event.server.getch_member(event.member.id)

            await self._update_guild_data(event.server_id)

            bot_api.session = aiohttp.ClientSession()

            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            config = guild_data.get('config', {})

            mute_req = requests.get(f'http://localhost:5000/moderation/{event.server_id}/{member.id}/mute', headers={
                'authorization': bot_config.SECRET_KEY
            })

            if mute_req.status_code == 200:
                if config.get('mute_role'):
                    await bot_api.assign_role_to_member(event.server_id, member.id, config['mute_role'])
            
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

            await bot_api.session.close()
        
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
                        await message.reply(embed=EMBED_FILTERED(message.author, 'Duplicate text'), private=True)
                    await message.delete()
                    return True

            if config.get('url_filter', 0) == 1:
                for url in malicious_urls.keys():
                    if url in message.content:
                        if isinstance(message, ChatMessage):
                            await message.reply(embed=EMBED_FILTERED(message.author, 'Malicious URL Detected'), private=True)
                        await message.delete()
                        if logs_channel is not None:
                            await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                                title='Malicious URL Detected',
                                description=message.content,
                                url=message.share_url,
                                colour = Colour.red(),
                            ).add_field(name='Threat Category', value=malicious_urls.get(url, 'unknown'), inline=False)\
                            .add_field(name='User', value=f'[{message.author.name}]({message.author.profile_url})'))
                        return True

            if config.get('invite_link_filter', 0) == 1:
                for domain, invite in re.findall(SERVER_INVITE_REGEX, message.content):
                    if '/' in invite and not 'i/' in invite:
                        continue
                    if isinstance(message, ChatMessage):
                        await message.reply(embed=EMBED_FILTERED(message.author, 'Invite Link Detected'), private=True)
                    await message.delete()
                    if logs_channel is not None:
                        await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                            title='Invite Link Detected',
                            description=message.content,
                            url=message.share_url,
                            colour = Colour.red(),
                        ).add_field(name='Invite Link', value='https://www.' + domain + '/' + invite, inline=False)\
                        .add_field(name='User', value=f'[{message.author.name}]({message.author.profile_url})'))
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
                    await message.reply(embed=EMBED_FILTERED(message.author, 'Toxicity'),private=True)
                await message.delete()
                hit_filter = True
            if config.get('hatespeech', 0) > 0 and hatespeech_proba >= config.get('hatespeech', 0):
                if isinstance(message, ChatMessage):
                    await message.reply(embed=EMBED_FILTERED(message.author, 'Hate Speech'),private=True)
                await message.delete()
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
                return True
            if custom_filter is not None and len(custom_filter) > 0:
                filter = self.get_filter(message.server_id)
                if filter.contains_profanity(message.content):
                    if isinstance(message, ChatMessage):
                        await message.reply(embed=EMBED_FILTERED(message.author, 'Blacklisted Word'),private=True)
                    await message.delete()
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
                        if re.search(r'.+(.(jpe?g?|jif|jfif?|png|gif|bmp|dib|webp|tiff?|raw|arw|cr2|nrw|k25|heif|heic|indd?|indt|jp2|j2k|jpf|jpx|jpm|mj2|svgz?|ai|eps))', link):
                            if isinstance(message, ChatMessage):
                                await message.reply(embed=EMBED_FILTERED(message.author, 'Only trusted users are permitted to post links containing images'), private=True)
                            await message.delete()
                            return True
                        try:
                            head_req = requests.head(link, headers={
                                'user-agent': USER_AGENT
                            })
                            if head_req.status_code == 200:
                                content_type = head_req.headers.get('content-type')
                                content_disposition = head_req.get('content-disposition')
                                blocked = False
                                if 'image' in content_type or re.search(r'.+(.(jpe?g?|jif|jfif?|png|gif|bmp|dib|webp|tiff?|raw|arw|cr2|nrw|k25|heif|heic|indd?|indt|jp2|j2k|jpf|jpx|jpm|mj2|svgz?|ai|eps))', content_disposition):
                                    blocked = True
                                elif 'html' in content_type:
                                    page_req = requests.get(link, headers={
                                        'user-agent': USER_AGENT
                                    })
                                    if page_req.status_code == 200:
                                        for url in re.findall(r"""<meta(?=\s|>)(?=(?:[^>=]|='[^']*'|="[^"]*"|=[^'"][^\s>]*)*?\sproperty=(?:'og:image|"og:image"|og:image|'twitter:image'|"twitter:image"|twitter:image|'twitter:image:src'|"twitter:image:src"|twitter:image:src))(?=(?:[^>=]|='[^']*'|="[^"]*"|=[^'"][^\s>]*)*?\scontent=('[^']*'|"[^"]*"|[^'"][^\s>]*))(?:[^'">=]*|='[^']*'|="[^"]*"|=[^'"][^\s>]*)*>""", page_req.text):
                                            blocked = True
                                            break
                                        for og_type in re.findall(r"""<meta(?=\s|>)(?=(?:[^>=]|='[^']*'|="[^"]*"|=[^'"][^\s>]*)*?\sproperty=(?:'og:type|"og:type"|og:type))(?=(?:[^>=]|='[^']*'|="[^"]*"|=[^'"][^\s>]*)*?\scontent=('[^']*'|"[^"]*"|[^'"][^\s>]*))(?:[^'">=]*|='[^']*'|="[^"]*"|=[^'"][^\s>]*)*>""", page_req.text):
                                            og_type: str = og_type.lower().strip()
                                            if og_type.startswith(('article', 'website', 'book', 'profile', 'video', 'music')):
                                                blocked = False
                                                break
                                        for keywords in re.findall(r"""< *meta +name *= *[\"\'] *keywords *[\"\'] *content= *[\"'](.+)[\"\'] *>""", page_req.text):
                                            keywords: str = keywords.lower()
                                            if 'video' in keywords or not 'image' in keywords:
                                                blocked = False
                                                break
                                if blocked is True:
                                    if isinstance(message, ChatMessage):
                                        await message.reply(embed=EMBED_FILTERED(message.author, 'Only trusted users are permitted to post links containing images'), private=True)
                                    await message.delete()
                                    return True
                        except:
                            pass
            return False

        async def on_message_update(event: MessageUpdateEvent):
            if not event.after.author.bot:
                member = await event.server.getch_member(event.after.author.id)
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
                em.add_field(name='User', value=f'[{member.name}]({member.profile_url})')
                em.add_field(name='ID', value=member.id)
                if event.before is not None:
                    em.add_field(name='Before', value=event.before.content, inline=False)
                em.add_field(name='After', value=event.after.content, inline=False)
                em.set_thumbnail(url=member.avatar.aws_url)
                await channel.send(embed=em)
        
        bot.message_update_listeners.append(on_message_update)

        async def on_message_delete(event: MessageDeleteEvent):
            if event.message.author.bot:
                return
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
                em.add_field(name='User', value=f'[{member.name}]({member.profile_url})')
                em.add_field(name='ID', value=member.id)
                em.add_field(name='Deleted message contents', value=event.message.content, inline=False)
                em.set_thumbnail(url=member.avatar.aws_url)
                await channel.send(embed=em)
        
        bot.message_delete_listeners.append(on_message_delete)

        async def on_message(message: ChatMessage):
            if message.author.bot:
                return
            member = await message.guild.getch_member(message.author.id)
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
                    await message.delete()
                    for item in cached_spam:
                        await item.delete()
                    cached_spam = []
                    spam_cache.set(f'{message.guild.id}/{message.author_id}', cached_spam)
                    return
                else:
                    cached_spam.append(message)
                    spam_cache.set(f'{message.guild.id}/{message.author_id}', cached_spam)
        self.bot.message_listeners.append(on_message)

        async def on_forum_topic_create(event: ForumTopicCreateEvent):
            if event.topic.author.bot:
                return
            member = await event.server.getch_member(event.topic.author.id)
            if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                return
            if await handle_text_message(event.topic):
                return
        self.bot.topic_create_listeners.append(on_forum_topic_create)

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
                em.add_field(name='User', value=f'[{member.name}]({member.profile_url})')
                em.add_field(name='ID', value=member.id)
                em.add_field(name='Edited topic title', value=event.topic.title, inline=False)
                em.add_field(name='Edited topic contents', value=event.topic.content, inline=False)
                em.set_thumbnail(url=member.avatar.aws_url)
                await channel.send(embed=em)
        self.bot.topic_update_listeners.append(on_forum_topic_update)

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
                    em.add_field(name='User', value=f'[{member.name}]({member.profile_url})')
                    em.add_field(name='ID', value=member.id)
                    em.add_field(name='Deleted topic title', value=event.topic.title, inline=False)
                    em.add_field(name='Deleted topic contents', value=event.topic.content, inline=False)
                    em.set_thumbnail(url=member.avatar.aws_url)
                    await channel.send(embed=em)
        self.bot.topic_delete_listeners.append(on_forum_topic_delete)
