from project.modules.base import Module
from project.modules.moderation import reset_filter_cache
from project.helpers.embeds import *
from project import bot_config
from guilded.ext import commands
from guilded import Embed, BulkMemberRolesUpdateEvent, http

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
        self.bot_api.token = os.getenv('BOT_KEY')

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
        /support - sends a link to the support server
        /invite - sends an invite link for the bot
        /commands - brings up this help text

        NOTE: Timespans are precise to the *exact day* not hours or minutes due to technical limitations.
        '''
            ))

        @bot.command()
        async def support(ctx: commands.Context):
            await ctx.reply(embed=Embed(
                title='Support Server',
                description='[Link](https://www.guilded.gg/server-guard)'
            ).set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'))
        
        @bot.command()
        async def invite(ctx: commands.Context):
            await ctx.reply(embed=Embed(
                title='Invite our Bot',
                description='[Link](https://www.guilded.gg/b/c10ac149-0462-4282-a632-d7a8808c6c6e)'
            ).set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'))
        
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
        /config automod_logs_channel <channel>
        /config message_logs_channel <channel>
        /config traffic_logs_channel <channel>
        /config nsfw_logs_channel [Premium Tier 1] <channel>
        /config disable_nsfw - Disables NSFW image detection
        /config verified_role <role>
        /config unverified_role <role>
        /config mod_role <add/remove>
        /config admin_role <add/remove>
        /config mute_role <role>
        /config filter <toxicity/hatespeech/spam> <sensitivity> - Set the sensitivity of a filter, setting to 0 disables
        /config filter <add/remove> <word> - Add or remove a word from the filter list
        /config spam <limit> - Set how many messages a user can say in a short timespan before the bot removes them, setting to 0 disables
        /config url_filter <yes/no> - Turn on or off the malicious URL filter

        NOTE: all role-related configurations expect a ROLE ID due to Guilded limitations.
        '''
                )
            )

        @config.command(name='spam')
        async def config_spam(ctx: commands.Context, amount: int=0):
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_spam', json={
                'value': amount
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully changed automod spam limit.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='url_filter')
        async def config_url_filter(ctx: commands.Context, on: str):
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/url_filter', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully changed url filtering status.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
            premium_status = await self.get_user_premium_status(ctx.server.owner_id)
            if premium_status is 0:
                await ctx.reply(embed=EMBED_NEEDS_PREMIUM(1))
                return
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
        
        @config.command(name='message_logs_channel')
        async def config_message_logs_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/message_logs_channel', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed message logs channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid channel!')
        
        @config.command(name='traffic_logs_channel')
        async def config_traffic_logs_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/traffic_logs_channel', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed traffic logs channel.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid channel!')

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
        
        @config.command(name='automod_logs_channel')
        async def config_automod_logs_channel(ctx: commands.Context, target: str):
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_logs_channel', json={
                    'value': ref['id']
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully changed automod logs channel.')
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
        
        @config.group(name='filter')
        async def filter(ctx: commands.Context):
            pass
        
        @filter.command(name='add')
        async def filter_add_word(ctx: commands.Context, word: str):
            await self.validate_permission_level(2, ctx)

            result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/filters', json={
                'value': word.lower()
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                reset_filter_cache(ctx.server.id)
                await ctx.reply(f'Successfully added "{word}" to filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @filter.command(name='remove')
        async def filter_remove_word(ctx: commands.Context, word: str):
            await self.validate_permission_level(2, ctx)

            result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/filters', json={
                'value': word.lower()
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 204:
                reset_filter_cache(ctx.server.id)
                await ctx.reply(f'Successfully removed "{word}" from filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')

        @filter.command(name='toxicity')
        async def filter_toxicity(ctx: commands.Context, sensitivity: int=0):
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/toxicity', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully set toxicity filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @filter.command(name='hatespeech')
        async def filter_hatespeech(ctx: commands.Context, sensitivity: int=0):
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/hatespeech', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully set hate speech filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @filter.command(name='spam')
        async def filter_spam(ctx: commands.Context, sensitivity: int=0):
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/spam', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully set spam filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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

        @bot.event
        async def on_bulk_member_roles_update(event: BulkMemberRolesUpdateEvent):
            if event.server_id == 'aE9Zg6Kj':
                for member in event.after:
                    self.reset_user_premium_cache(member.id)
