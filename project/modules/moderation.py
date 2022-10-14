from datetime import datetime
from project.modules.base import Module
from project import bot_config, bot_api
from guilded.ext import commands, tasks
from guilded import Embed, Colour, MemberJoinEvent
from humanfriendly import parse_timespan, format_timespan

import requests
import aiohttp

member = commands.MemberConverter()
user_converter = commands.UserConverter()

class ModerationModule(Module):
    name = 'Moderation'

    def initialize(self):
        bot = self.bot

        @bot.command()
        async def ban(ctx: commands.Context, target: str, timespan: str=None, *_reason):
            await self.validate_permission_level(1, ctx)
            user = await member.convert(ctx, target)

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
            user = await member.convert(ctx, target)

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
            user = await member.convert(ctx, target)

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
            user = await member.convert(ctx, target)

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
            user = await member.convert(ctx, target)

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
            user = await member.convert(ctx, target)

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
            await bot_api.session.close()
        
        bot.join_listeners.append(on_member_join)

        # TODO: Warnings
        # TODO: Mute/Temp-mute