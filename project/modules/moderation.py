from datetime import datetime
from project.helpers.embeds import *
from project.helpers.images import *
from project.helpers.Cache import Cache
from project.modules.base import Module
from project import bot_config, bot_api, malicious_urls
from guilded.ext import commands
from guilded import Embed, Colour, MemberJoinEvent, MemberRemoveEvent, MessageUpdateEvent, MessageDeleteEvent, ChatMessage, http
from humanfriendly import parse_timespan, format_timespan
from better_profanity import Profanity

import os
import requests
import aiohttp
import joblib
import numpy as np

user_converter = commands.UserConverter()

MODELS_ROOT = bot_config.PROJECT_ROOT + '/project/ml_models'

filters = {
    'toxicity': {
        'vectorizer': joblib.load(MODELS_ROOT + '/toxicity/vectorizer.joblib'),
        'model': joblib.load(MODELS_ROOT + '/toxicity/model.joblib')
    },
    'hatespeech': {
        'vectorizer': joblib.load(MODELS_ROOT + '/hatespeech/vectorizer.joblib'),
        'model': joblib.load(MODELS_ROOT + '/hatespeech/model.joblib')
    },
    'spam': {
        'vectorizer': joblib.load(MODELS_ROOT + '/spam/vectorizer.joblib'),
        'model': joblib.load(MODELS_ROOT + '/spam/model.joblib')
    }
}

filter_cache = Cache()
spam_cache = Cache(3)

def _get_prob(prob):
    return prob[1]

def apply_filter(filter: str, texts: list):
    if not filters.get(filter):
        raise Exception('Filter not found')
    f = filters[filter]
    return np.apply_along_axis(
        _get_prob, 1, f['model'].predict_proba(f['vectorizer'].transform(texts))
    )

def reset_filter_cache(guild_id):
    filter_cache.remove(guild_id)

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

        @bot.command()
        async def ban(ctx: commands.Context, target: str, timespan: str=None, *_reason):
            await self.validate_permission_level(1, ctx)
            user = self.convert_member(ctx, target)

            if await self.is_moderator(user):
                ctx.reply('This user is a moderator, I can\'t do that!')
                return
            
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()

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
                if guild_data.get('config', {}).get('logs_channel'):
                    channel = await ctx.server.fetch_channel(guild_data['config']['logs_channel'])
                    await channel.send(embed=em)
        
        @bot.command()
        async def unban(ctx: commands.Context, target: str):
            await self.validate_permission_level(1, ctx)
            user = await user_converter.convert(ctx, target)

            await ctx.server.unban(user)
            requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/ban', headers={
                'authorization': bot_config.SECRET_KEY
            })
        
        @bot.command()
        async def mute(ctx: commands.Context, target: str, timespan: str=None, *_reason):
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            bot_api.session = aiohttp.ClientSession()

            if await self.is_moderator(user):
                ctx.reply('This user is a moderator, I can\'t do that!')
                return

            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()

            reason = ' '.join(_reason)

            if timespan is not None:
                try:
                    timespan = parse_timespan(timespan)
                except:
                    reason = timespan + ' ' + reason
                    timespan = None
            
            if user is not None:
                if guild_data.get('config', {}).get('mute_role'):
                    await bot_api.assign_role_to_member(ctx.server.id, user.id, guild_data['config']['mute_role'])
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
                if guild_data.get('config', {}).get('logs_channel'):
                    channel = await ctx.server.fetch_channel(guild_data['config']['logs_channel'])
                    await channel.send(embed=em)
                await bot_api.session.close()
        
        @bot.command()
        async def unmute(ctx: commands.Context, target: str):
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

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
            await bot_api.session.close()
        
        @bot.command()
        async def warn(ctx: commands.Context, target: str, timespan: str=None, *_reason):
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()

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
                if guild_data.get('config', {}).get('logs_channel'):
                    channel = await ctx.server.fetch_channel(guild_data['config']['logs_channel'])
                    await channel.send(embed=em)
        
        @bot.command()
        async def warnings(ctx: commands.Context, target: str):
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            result = requests.get(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', headers={
                'authorization': bot_config.SECRET_KEY
            })
            em = Embed(
                title = f'Warnings for {user.name}',
                description = ''.join([f'{item["id"]} | <@{item["issuer"]}> - {item["reason"]}\n' for item in result.json()['result']]),
                colour = Colour.orange()
            )
            await ctx.reply(embed=em)
        
        @bot.command()
        async def delwarn(ctx: commands.Context, target: str, id: str=None):
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

            if id:
                result = requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings/{id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                em = Embed(
                    title = f'Deleted warning {id} for {user.name}',
                    description = f'Successfully cleared warning {id} for {user.name}',
                    colour = Colour.green()
                )
                await ctx.reply(embed=em)
            else:
                result = requests.delete(f'http://localhost:5000/moderation/{ctx.server.id}/{user.id}/warnings', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                em = Embed(
                    title = f'Warnings for {user.name} cleared',
                    description = f'Successfully cleared all warnings for {user.name}!',
                    colour = Colour.green()
                )
                await ctx.reply(embed=em)
        
        @bot.command()
        async def userinfo(ctx: commands.Context, target: str):
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)

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
                )
                em.add_field(name='Roles', value=', '.join([f'<@{role}>' for role in role_ids]), inline=False)
                em.add_field(name='Account created', value=user.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                em.add_field(name='Joined at', value=user.joined_at.strftime("%b %d %Y at %H:%M %p %Z"))
                await ctx.reply(embed=em)
        
        async def on_member_join(event: MemberJoinEvent):
            member = event.member

            bot_api.session = aiohttp.ClientSession()

            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()

            mute_req = requests.get(f'http://localhost:5000/moderation/{event.server_id}/{member.id}/mute', headers={
                'authorization': bot_config.SECRET_KEY
            })

            if mute_req.status_code == 200:
                if guild_data.get('config', {}).get('mute_role'):
                    await bot_api.assign_role_to_member(event.server_id, member.id, guild_data['config']['mute_role'])
            
            traffic_log_channel = guild_data.get('config', {}).get('traffic_logs_channel')

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
                channel = await bot.getch_channel(traffic_log_channel)
                await channel.send(embed=em)

            await bot_api.session.close()
        
        bot.join_listeners.append(on_member_join)

        async def on_member_remove(event: MemberRemoveEvent):
            member = await bot.getch_user(event.user_id)

            guild_data: dict = self.get_guild_data(event.server_id)
            traffic_log_channel = guild_data.get('config', {}).get('traffic_logs_channel')

            if traffic_log_channel is not None and traffic_log_channel != '':
                created_time = member.created_at.timestamp()
                diff = abs(datetime.now().timestamp() - created_time)
                em = Embed(
                    title=f'{member.name} left the server',
                    url=member.profile_url,
                    colour=Colour.gilded()
                )
                em.set_thumbnail(url=member.avatar is not None and member.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                em.add_field(name='User ID', value=member.id)
                em.add_field(name='Account created', value=member.created_at.strftime("%b %d %Y at %H:%M %p %Z") + (diff <= 60 * 60 * 24 * 3 and '\n:warning: Recent' or ''))
                channel = await bot.getch_channel(traffic_log_channel)
                await channel.send(embed=em)
        
        bot.leave_listeners.append(on_member_remove)

        async def on_message_update(event: MessageUpdateEvent):
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
                if event.before is not None:
                    em.add_field(name='Before', value=event.before.content, inline=False)
                em.add_field(name='After', value=event.after.content, inline=False)
                em.set_thumbnail(url=member.avatar.aws_url)
                await channel.send(embed=em)
        
        bot.message_update_listeners.append(on_message_update)

        async def on_message_delete(event: MessageDeleteEvent):
            guild_data: dict = self.get_guild_data(event.server_id)
            message_log_channel = guild_data.get('config', {}).get('message_logs_channel')

            if message_log_channel is not None and message_log_channel != '':
                if event.message is None:
                    return # Don't process if the message doesn't exist in cache
                channel = await bot.getch_channel(message_log_channel)
                member = event.message.author
                em = Embed(
                    title=f'Message deleted in {event.message.channel.name}',
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
            guild_data: dict = self.get_guild_data(message.server_id)
            config = guild_data.get('config', {})
            custom_filter = config.get('filters')
            logs_channel_id = config.get('automod_logs_channel')
            if logs_channel_id:
                logs_channel = await bot.getch_channel(logs_channel_id)
            else:
                logs_channel = None
            
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
            
            if config.get('url_filter', 0) == 1:
                for url in malicious_urls.keys():
                    if url in message.content:
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
                        return

            if config.get('toxicity', 0) > 0:
                toxicity_proba = apply_filter('toxicity', [message.content])[0] * 100
            else:
                toxicity_proba = 0
            if config.get('hatespeech', 0) > 0:
                hatespeech_proba = apply_filter('hatespeech', [message.content])[0] * 100
            else:
                hatespeech_proba = 0
            if config.get('spam', 0) > 0:
                spam_proba = apply_filter('spam', [message.content])[0] * 100
            else:
                spam_proba = 0
            
            if toxicity_proba >= config['toxicity']:
                await message.reply(embed=EMBED_FILTERED(message.author, 'Toxicity'),private=True)
                await message.delete()
            if hatespeech_proba >= config['hatespeech']:
                await message.reply(embed=EMBED_FILTERED(message.author, 'Hate Speech'),private=True)
                await message.delete()
            if spam_proba >= config['spam']:
                await message.reply(embed=EMBED_FILTERED(message.author, 'Spam'),private=True)
                await message.delete()
            if max(toxicity_proba, spam_proba, hatespeech_proba) >= 50:
                if logs_channel is not None:
                    which = toxicity_proba >= 50 and 'Toxicity' or spam_proba >= 50 and 'Spam' or 'Hate Speech'
                    await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                        title=f'{which} Filter Triggered',
                        description=message.content,
                        url=message.share_url,
                        colour = Colour.orange(),
                    ).set_footer(text=f'Certainty: {round(max(toxicity_proba, spam_proba, hatespeech_proba))}%').add_field(name='User', value=message.author.name))
            if custom_filter is not None and len(custom_filter) > 0:
                filter = self.get_filter(message.server_id)
                if filter.contains_profanity(message.content):
                    await message.reply(embed=EMBED_FILTERED(message.author, 'Blacklisted Word'),private=True)
                    await message.delete()
                    if logs_channel is not None:
                        await logs_channel.send(embed=EMBED_TIMESTAMP_NOW(
                            title='Blacklisted Word Filter Triggered',
                            description=message.content,
                            url=message.share_url,
                            colour = Colour.orange(),
                        ).add_field(name='User', value=message.author.name).add_field(name='Filtered Message', value=filter.censor(message.content), inline=False))
        self.bot.message_listeners.append(on_message)