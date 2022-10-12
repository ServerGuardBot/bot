from json import JSONEncoder
from guilded import Server, Member, ChatChannel, Embed, BanDeleteEvent, BanCreateEvent, MemberJoinEvent
from guilded.ext import commands
from project.modules.base import Module
from project import bot_config

from project.helpers import social_links, user_evaluator, verif_token

import requests

encoder = JSONEncoder()
member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

class VerificationModule(Module):
    name = "Verification"

    def initialize(self):
        bot = self.bot

        @bot.command()
        async def evaluate(ctx: commands.Context, target: str=None):
            await self.validate_permission_level(1, ctx)
            user = target == None and ctx.author or await member.convert(ctx, target)
            if user.bot:
                pass # We know bots aren't real users lol
            links = await social_links.get_connections(ctx.guild.id, user.id)
            eval_result = await user_evaluator.evaluate_user(ctx.guild.id, user.id, encoder.encode(links))

            await ctx.reply(embed=user_evaluator.generate_embed(eval_result))
        
        @bot.command()
        async def verify(ctx: commands.Context):
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            unverified_role = guild_data.get('config').get('unverified_role')
            verified_role = guild_data.get('config').get('verified_role')

            guilded_member = await ctx.server.fetch_member(ctx.author.id)
            member_roles = await guilded_member.fetch_role_ids()
            if unverified_role:
                if int(unverified_role) not in member_roles:
                    await ctx.reply('You\'re already verified!')
                    return
            elif verified_role:
                if int(verified_role) in member_roles:
                    await ctx.reply('You\'re already verified!')
                    return

            token = verif_token.generate_token(ctx.guild.id, ctx.author.id, await social_links.get_connections(ctx.guild.id, ctx.author.id))
            link = requests.post('http://localhost:5000/verify/shorten', json={
                'token': token
            }, headers={
                'authorization': bot_config.SECRET_KEY
            }).json()['result']

            await ctx.reply(content=f'Here\'s your verification link: [{link}](https://serverguard.reapimus.com/verify/{link})', private=True)
        
        @bot.group(description='Configure bot settings', invoke_without_command=True)
        async def config(ctx: commands.Context):
            pass
        
        @config.command(name='help')
        async def config_help(ctx: commands.Context):
            await self.validate_permission_level(2, ctx)
            await ctx.reply(
                embed=Embed(
                    title='Config Help',
                    description='The following configuration options are available: verification_channel, logs_channel, verified_role, unverified_role, mod_role <add/remove>, admin_role <add/remove>\n NOTE: all role-related configurations expect a ROLE ID due to Guilded limitations.'
                )
            )

        @config.command(name='verification_channel')
        async def config_verif_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await channel.convert(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed verification channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='logs_channel')
        async def config_logs_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await channel.convert(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed logs channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='verified_role')
        async def config_verified_role(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verified_role', json={
                    'value': ref
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed verified role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='unverified_role')
        async def config_unverified_role(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/unverified_role', json={
                    'value': ref
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed unverified role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.group(name='mod_role')
        async def mod_role(ctx: commands.Context):
            pass

        @mod_role.command(name='add')
        async def mod_add(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref,
                        'level': 0
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully added mod role.')
                elif result.status_code == 400:
                    await ctx.reply('This is already a mod role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @mod_role.command(name='remove')
        async def mod_remove(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref,
                        'level': 0
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 204:
                    await ctx.reply('Successfully removed mod role.')
                elif result.status_code == 400:
                    await ctx.reply('This is not a mod role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.group(name='admin_role')
        async def admin_role(ctx: commands.Context):
            pass

        @admin_role.command(name='add')
        async def admin_add(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref,
                        'level': 1
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully added admin role.')
                elif result.status_code == 400:
                    await ctx.reply('This is already an admin role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @admin_role.command(name='remove')
        async def admin_remove(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref,
                        'level': 1
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 204:
                    await ctx.reply('Successfully removed admin role.')
                elif result.status_code == 400:
                    await ctx.reply('This is not an admin role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
        
        @bot.command()
        async def bypass(ctx: commands.Context, target: str):
            await self.validate_permission_level(1, ctx)
            user = await member.convert(ctx, target)
            if user.bot:
                pass # We know bots aren't real users lol
            result = requests.patch(f'http://localhost:5000/verify/bypass/{ctx.server.id}/{user.id}', json={
                'value': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200:
                await ctx.reply('Successfully allowed verification bypass.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @bot.command()
        async def unbypass(ctx: commands.Context, target: str):
            await self.validate_permission_level(1, ctx)
            user = await member.convert(ctx, target)
            if user.bot:
                pass # We know bots aren't real users lol
            result = requests.patch(f'http://localhost:5000/verify/bypass/{ctx.server.id}/{user.id}', json={
                'value': False
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200:
                await ctx.reply('Successfully disallowed verification bypass.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')

        @bot.event
        async def on_server_join(server: Server):
            requests.get(f'http://localhost:5000/guilddata/{server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            }) # Initialize server data

            owner = await bot.fetch_user(server.owner_id)
            await owner.send('Hey! Thanks for using Server Guard. To properly setup your server make sure to setup config using `/config`!')
        
        @bot.event
        async def on_member_join(event: MemberJoinEvent):
            if event.member.bot:
                return
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            unverified_role = guild_data.get('config').get('unverified_role')
            verification_channel = guild_data.get('config').get('verification_channel')
            
            if unverified_role:
                requests.put(f'https://www.guilded.gg/api/v1/servers/{event.server_id}/members/{event.member.id}/roles/{unverified_role}',
                headers={
                    'Authorization': f'Bearer {bot_config.GUILDED_BOT_TOKEN}'
                })
            if verification_channel:
                channel: ChatChannel = await event.server.fetch_channel(verification_channel)
                await channel.send(f'Welcome {event.member.name}! Please verify using the /verify command.')
        
        @bot.event
        async def on_ban_create(event: BanCreateEvent):
            if event.ban.user.bot:
                return
            guild_data_req = requests.patch(f'http://localhost:5000/verify/setbanned/{event.server_id}/{event.ban.user.id}', json={
                'value': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
        
        @bot.event
        async def on_ban_delete(event: BanDeleteEvent):
            if event.ban.user.bot:
                return
            guild_data_req = requests.patch(f'http://localhost:5000/verify/setbanned/{event.server_id}/{event.ban.user.id}', json={
                'value': False
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
