from project.modules.base import Module
from project import bot_config
from guilded.ext import commands
from guilded import Embed, http

import os
import requests

member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

class GeneralModule(Module):
    name = 'General'

    def initialize(self):
        bot = self.bot

        self.bot_api = http.HTTPClient()
        self.bot_api.token = os.getenv('GUILDED_BOT_TOKEN')

        # Register help command
        @bot.command(name='commands')
        async def commands_(ctx: commands.Context):
            await ctx.reply(embed=Embed(
                title='Commands',
                description=
        '''
        /verify - start the verification process
        /evaluate `<user>` - Moderator+, shows an evaluation of a user
        /config - Administrator, configure the bot's settings. Use /config help for more information
        /bypass `<user>` - Moderator+, allows a user to bypass verification
        /unbypass `<user>` - Moderator+, revokes a user's verification bypass
        /ban <user> <timespan?> <reason> - Moderator+, bans a user for the specified reason, with an optional ban length
        /unban <user> - Moderator+, unbans a user from the server
        /mute <user> <timespan?> <reason> - Moderator+, mutes a user in the server, with an optional mute length
        /unmute <user> - Moderator+, unmutes a user in the server
        /warn <user> <timespan?> <reason> - Moderator+, warns a user in the server, with an option for when it expires
        /warnings <user> - Moderator+, view a user's warnings
        /delwarn <user> <id?> - Moderator+, delete a user's warnings, optionally only a specific warning by specifying its id
        /commands - brings up this help text

        NOTE: Timespans are precise to the *exact day* not hours or minutes due to technical limitations.
        '''
            ))

        @bot.group(description='Configure bot settings', invoke_without_command=True)
        async def config(ctx: commands.Context):
            pass
        
        @config.command(name='help')
        async def config_help(ctx: commands.Context):
            await self.validate_permission_level(2, ctx)
            await ctx.reply(
                embed=Embed(
                    title='Config Help',
                    description=
        '''
        The following configuration options are available:
        /config verification_channel <channel>
        /config logs_channel <channel>
        /config nsfw_logs_channel <channel>
        /config disable_nsfw - Disables NSFW image detection
        /config verified_role <role>
        /config unverified_role <role>
        /config mod_role <add/remove>
        /config admin_role <add/remove>
        /config mute_role <role>

        NOTE: all role-related configurations expect a ROLE ID due to Guilded limitations.
        '''
                )
            )

        @config.command(name='mute_role')
        async def config_mute_role(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target) #target #await role.convert(ctx, target)
            # NOTE: just gotta hope to god that the user inputs a role id because guilded dum

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/mute_role', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed muted role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')

        @config.command(name='verification_channel')
        async def config_verif_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed verification channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid channel!')
        
        @config.command(name='nsfw_logs_channel')
        async def config_nsfw_logs_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/nsfw_logs_channel', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed NSFW logs channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid channel!')
        
        @config.command(name='disable_nsfw')
        async def config_disable_nsfw(ctx: commands.Context):
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/nsfw_logs_channel', json={
                'value': ''
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully changed NSFW logs channel.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='logs_channel')
        async def config_logs_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/logs_channel', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed logs channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid channel!')
        
        @config.command(name='verified_role')
        async def config_verified_role(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verified_role', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed verified role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid role!')
        
        @config.command(name='unverified_role')
        async def config_unverified_role(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/unverified_role', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed unverified role.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid role!')
        
        @config.group(name='mod_role')
        async def mod_role(ctx: commands.Context):
            pass

        @mod_role.command(name='add')
        async def mod_add(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref['id'],
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
            else:
                await ctx.reply('Please specify a valid role!')
        
        @mod_role.command(name='remove')
        async def mod_remove(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref['id'],
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
            else:
                await ctx.reply('Please specify a valid role!')
        
        @config.group(name='admin_role')
        async def admin_role(ctx: commands.Context):
            pass

        @admin_role.command(name='add')
        async def admin_add(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref['id'],
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
            else:
                await ctx.reply('Please specify a valid role!')
        
        @admin_role.command(name='remove')
        async def admin_remove(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref['id'],
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
            else:
                await ctx.reply('Please specify a valid role!')
