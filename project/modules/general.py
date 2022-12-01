import re
from project.modules.base import Module
from project.modules.moderation import reset_filter_cache
from project.helpers.embeds import *
from project.helpers.Cache import Cache
from project import bot_config
from guilded.ext import commands
from guilded.ext.commands.help import HelpCommand, Paginator
from guilded import Embed, BulkMemberRolesUpdateEvent, BotAddEvent, BotRemoveEvent, ChatMessage, http
from datetime import datetime
from humanfriendly import format_timespan

import os
import requests
import itertools

LOGIN_CHANNEL_ID = '1f6fae7f-6cdf-403d-80b9-623a76f8b621'

member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

xp_cache = Cache(60)

class CustomHelpCommand(HelpCommand):
    def __init__(self, **options):
        self.sort_commands = options.pop('sort_commands', True)
        self.commands_heading = options.pop('commands_heading', "Commands")
        self.dm_help = options.pop('dm_help', False)
        self.dm_help_threshold = options.pop('dm_help_threshold', 1000)
        self.aliases_heading = options.pop('aliases_heading', "Aliases:")
        self.no_category = options.pop('no_category', 'No Category')
        self.paginator = options.pop('paginator', None)

        if self.paginator is None:
            self.paginator = Paginator(prefix=None, suffix=None)

        super().__init__(**options)
    
    async def send_pages(self):
        """A helper utility to send the page output from :attr:`paginator` to the destination."""
        destination = self.get_destination()
        for page in self.paginator.pages:
            em = Embed(
                title = 'Commands',
                description = page,
                colour = Colour.gilded()
            ) \
            .set_footer(text='Server Guard') \
            .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
            .add_field(name='Links', value='[Support Server](https://www.guilded.gg/server-guard) • [Invite](https://www.guilded.gg/b/c10ac149-0462-4282-a632-d7a8808c6c6e) • [Docs](https://www.guilded.gg/server-guard/groups/D57rgP7z/channels/7ad31d28-0577-4f18-a80d-d401ceacf9db/docs)', inline=False)
            await destination.send(embed=em)
    
    def shorten_text(self, text):
        """:class:`str`: Shortens text to fit into the :attr:`width`."""
        if len(text) > self.width:
            return text[:self.width - 3].rstrip() + '...'
        return text

    def get_ending_note(self):
        """:class:`str`: Returns help command's ending note. This is mainly useful to override for i18n purposes."""
        command_name = self.invoked_with
        return (
            f"Type {self.context.clean_prefix}{command_name} command for more info on a command."
        )
    
    def add_bot_commands_formatting(self, commands, heading):
        """Adds the minified bot heading with commands to the output.
        The formatting should be added to the :attr:`paginator`.
        The default implementation is a bold underline heading followed
        by commands separated by an EN SPACE (U+2002) in the next line.
        Parameters
        -----------
        commands: Sequence[:class:`Command`]
            A list of commands that belong to the heading.
        heading: :class:`str`
            The heading to add to the line.
        """
        if commands:
            joined = ', '.join(f'`{c.name}`' for c in commands)
            self.paginator.add_line(f'__**{heading}**__')
            self.paginator.add_line(joined)
    
    def add_subcommand_formatting(self, command):
        """Adds formatting information on a subcommand.
        The formatting should be added to the :attr:`paginator`.
        The default implementation is the prefix and the :attr:`Command.qualified_name`
        optionally followed by an En dash and the command's :attr:`Command.short_doc`.
        Parameters
        -----------
        command: :class:`Command`
            The command to show information of.
        """
        fmt = '`{0}` \N{EN DASH} {1}' if command.short_doc else '`{0}`'
        self.paginator.add_line(fmt.format(command.name, command.short_doc))
    
    def add_aliases_formatting(self, aliases):
        """Adds the formatting information on a command's aliases.
        The formatting should be added to the :attr:`paginator`.
        The default implementation is the :attr:`aliases_heading` bolded
        followed by a comma separated list of aliases.
        This is not called if there are no aliases to format.
        Parameters
        -----------
        aliases: Sequence[:class:`str`]
            A list of aliases to format.
        """
        self.paginator.add_line(f'**{self.aliases_heading}** {", ".join([f"`{c}`" for c in aliases])}', empty=True)
    
    def add_command_formatting(self, command):
        """A utility function to format commands and groups.
        Parameters
        ------------
        command: :class:`Command`
            The command to format.
        """

        if command.description:
            self.paginator.add_line(command.description, empty=True)

        signature = self.get_command_signature(command)
        if command.aliases:
            self.paginator.add_line(signature)
            self.add_aliases_formatting(command.aliases)
        else:
            self.paginator.add_line(signature, empty=True)

        if command.help:
            try:
                self.paginator.add_line(command.help, empty=True)
            except RuntimeError:
                for line in command.help.splitlines():
                    self.paginator.add_line(line)
                self.paginator.add_line()
    
    def get_destination(self):
        ctx = self.context
        if self.dm_help is True:
            return ctx.author
        elif self.dm_help is None and len(self.paginator) > self.dm_help_threshold:
            return ctx.author
        else:
            return ctx.channel
    
    async def prepare_help_command(self, ctx, command):
        self.paginator.clear()
        await super().prepare_help_command(ctx, command)

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        if bot.description:
            self.paginator.add_line(bot.description, empty=True)

        no_category = f'\u200b{self.no_category}'

        def get_category(command, *, no_category=no_category):
            cog = command.cog
            return cog.qualified_name if cog is not None else no_category

        filtered = await self.filter_commands(bot.commands, sort=True, key=get_category)
        to_iterate = itertools.groupby(filtered, key=get_category)

        for category, commands in to_iterate:
            commands = sorted(commands, key=lambda c: c.name) if self.sort_commands else list(commands)
            self.add_bot_commands_formatting(commands, category)

        note = self.get_ending_note()
        if note:
            self.paginator.add_line()
            self.paginator.add_line(note)

        await self.send_pages()

    async def send_cog_help(self, cog):
        bot = self.context.bot
        if bot.description:
            self.paginator.add_line(bot.description, empty=True)

        if cog.description:
            self.paginator.add_line(cog.description, empty=True)

        filtered = await self.filter_commands(cog.get_commands(), sort=self.sort_commands)
        if filtered:
            self.paginator.add_line(f'**{cog.qualified_name} {self.commands_heading}**')
            for command in filtered:
                self.add_subcommand_formatting(command)

            note = self.get_ending_note()
            if note:
                self.paginator.add_line()
                self.paginator.add_line(note)

        await self.send_pages()

    async def send_group_help(self, group):
        self.add_command_formatting(group)

        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
        if filtered:

            self.paginator.add_line(f'**{self.commands_heading}**')
            for command in filtered:
                self.add_subcommand_formatting(command)

            note = self.get_ending_note()
            if note:
                self.paginator.add_line()
                self.paginator.add_line(note)

        await self.send_pages()

    async def send_command_help(self, command):
        self.add_command_formatting(command)
        self.paginator.close_page()
        await self.send_pages()

class General(commands.Cog):
    pass

class GeneralModule(Module):
    name = 'General'

    def initialize(self):
        bot = self.bot

        self.bot_api = http.HTTPClient()
        self.bot_api.token = os.getenv('BOT_KEY')

        start_time = datetime.now().timestamp()

        bot.help_command = CustomHelpCommand()

        cog = General()

        bot._help_command.cog = cog

        @bot.command()
        async def analytics(_, ctx: commands.Context):
            """Bot creator-only command that displays bot analytics"""
            if ctx.author.id == 'm6YxwpQd':
                uptime = abs(datetime.now().timestamp() - start_time)

                # Make sure we have data for the current hour
                requests.post(f'http://localhost:5000/analytics/servers', headers={
                    'authorization': bot_config.SECRET_KEY
                })

                result_server_count = requests.get(f'http://localhost:5000/analytics/servers', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                result_largest_servers = requests.get(f'http://localhost:5000/analytics/servers/largest', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                result_unindexed_servers = requests.get(f'http://localhost:5000/analytics/servers/unindexed', headers={
                    'authorization': bot_config.SECRET_KEY
                })

                for id in result_unindexed_servers.json():
                    try:
                        await self._update_guild_data(id)
                    except:
                        result = requests.patch(f'http://localhost:5000/guilddata/{id}', json={
                            'active': False
                        }, headers={
                            'authorization': bot_config.SECRET_KEY
                        })

                await ctx.reply(embed=Embed(
                    title='Bot Analytics',
                    colour=Colour.gilded(),
                )\
                .add_field(name='Server Count', value=str(result_server_count.json().get('value', 1))) \
                .add_field(name='Uptime', value=format_timespan(uptime)) \
                .add_field(name='Largest Servers', value='\n'.join([f'{server.get("members")} Members, {server.get("name")}' for server in result_largest_servers.json()]), inline=False) \
                .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'))

        analytics.cog = cog

        @bot.command()
        async def support(_, ctx: commands.Context):
            """Get a link to the support server"""
            await ctx.reply(embed=Embed(
                title='Support Server',
                description='[Link](https://www.guilded.gg/server-guard)'
            ).set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'))
        
        support.cog = cog
        
        @bot.command()
        async def invite(_, ctx: commands.Context):
            """Get an invite link for the bot"""
            await ctx.reply(embed=Embed(
                title='Invite our Bot',
                description='[Link](https://www.guilded.gg/b/c10ac149-0462-4282-a632-d7a8808c6c6e)'
            ).set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'))
        
        invite.cog = cog
        
        @bot.group(invoke_without_command=True)
        async def config(_, ctx: commands.Context):
            """[Administrator] Configure the bot"""
            pass

        config.cog = cog

        @config.command(name='spam')
        async def config_spam(ctx: commands.Context, amount: int=0):
            """Set how many messages a user can say in a short timespan before the bot removes them, setting to 0 disables"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_spam', json={
                'value': amount
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed automod spam limit.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.command(name='admin_contact')
        async def config_admin_contact(ctx: commands.Context, *_account):
            """Specify an admin account the user can contact"""
            await self.validate_permission_level(2, ctx)
            account = ' '.join(_account)

            ref = await self.convert_member(ctx, account)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/admin_contact', json={
                    'value': ref.profile_url
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })
            elif re.match(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", account):
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/admin_contact', json={
                    'value': f'mailto:{account}'
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })
            else:
                link_match = re.search(r'\[(.*?)\]\((.*?)\)', account)
                if link_match:
                    result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/admin_contact', json={
                        'value': link_match.groups()[1]
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This command expects a URL, Valid Email, or User to be specified.'))
                    return

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed server admin contact.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.command(name='tor_block')
        async def config_tor_block(ctx: commands.Context, on: str):
            """Turn on or off the tor exit node blocklist for verification"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/block_tor', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed tor blocking status.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))

        @config.command(name='invite_link_filter')
        async def config_invite_link_filter(ctx: commands.Context, on: str):
            """Turn on or off the discord/guilded invite link filter"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/invite_link_filter', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed invite filtering status.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.command(name='duplicate_filter')
        async def config_duplicate_filter(ctx: commands.Context, on: str):
            """Turn on or off the duplicate text filter"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_duplicate', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed duplicate text filtering status.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.command(name='url_filter')
        async def config_url_filter(ctx: commands.Context, on: str):
            """Turn on or off the malicious URL filter"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/url_filter', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed url filtering status.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.command(name='mute_role')
        async def config_mute_role(ctx: commands.Context, *_target):
            """Set the mute role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/mute_role', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed muted role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))

        @config.command(name='verification_channel')
        async def config_verif_channel(ctx: commands.Context, *_target):
            """Set the verification channel, specifying no channel disables verification"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed verification channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            elif target.isspace() or target == '':
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ''
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully disabled verification.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))
        
        @config.command(name='nsfw_logs_channel')
        async def config_nsfw_logs_channel(ctx: commands.Context, *_target):
            """[Premium Tier 1] Set the NSFW logs channel (Enables the NSFW filter)"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            premium_status = await self.get_user_premium_status(ctx.server.owner_id)
            if premium_status == 0:
                await ctx.reply(embed=EMBED_NEEDS_PREMIUM(1))
                return
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/nsfw_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed NSFW logs channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))
        
        @config.command(name='disable_nsfw')
        async def config_disable_nsfw(ctx: commands.Context):
            """Disable the NSFW filter"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/nsfw_logs_channel', json={
                'value': ''
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed NSFW logs channel.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.command(name='message_logs_channel')
        async def config_message_logs_channel(ctx: commands.Context, *_target):
            """Set the message logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/message_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed message logs channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))
        
        @config.command(name='traffic_logs_channel')
        async def config_traffic_logs_channel(ctx: commands.Context, *_target):
            """Set the traffic logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/traffic_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed traffic logs channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))

        @config.command(name='verify_logs_channel')
        async def config_verify_logs_channel(ctx: commands.Context, *_target):
            """Set the verify logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verify_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed verify logs channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))

        @config.command(name='action_logs_channel')
        async def config_action_logs_channel(ctx: commands.Context, *_target):
            """Set the action logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/action_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed action logs channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))

        @config.command(name='automod_logs_channel')
        async def config_automod_logs_channel(ctx: commands.Context, *_target):
            """Set the automod logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed automod logs channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))
        
        @config.command(name='verified_role')
        async def config_verified_role(ctx: commands.Context, *_target):
            """Set the verified role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verified_role', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed verified role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @config.command(name='unverified_role')
        async def config_unverified_role(ctx: commands.Context, *_target):
            """Set the unverified role"""
            print(_target)
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/unverified_role', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed unverified role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @config.group(name='filter')
        async def filter(ctx: commands.Context):
            """Configure the filters"""
            pass
        
        @filter.command(name='add')
        async def filter_add_word(ctx: commands.Context, word: str):
            """Add a word to the filter list"""
            await self.validate_permission_level(2, ctx)

            result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/filters', json={
                'value': word.lower()
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                reset_filter_cache(ctx.server.id)
                await ctx.reply(embed=EMBED_SUCCESS(f'Successfully added "{word}" to filter.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @filter.command(name='remove')
        async def filter_remove_word(ctx: commands.Context, word: str):
            """Remove a word from the filter list"""
            await self.validate_permission_level(2, ctx)

            result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/filters', json={
                'value': word.lower()
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 204:
                reset_filter_cache(ctx.server.id)
                await ctx.reply(embed=EMBED_SUCCESS(f'Successfully removed "{word}" from filter.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))

        @filter.command(name='toxicity')
        async def filter_toxicity(ctx: commands.Context, sensitivity: int=0):
            """Set the toxicity filter's threshold, [0-100] (0 disables)"""
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/toxicity', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully set toxicity filter.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @filter.command(name='hatespeech')
        async def filter_hatespeech(ctx: commands.Context, sensitivity: int=0):
            """Set the hate-speech filter's threshold, [0-100] (0 disables)"""
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/hatespeech', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully set hate speech filter.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
        
        @config.group(name='mod_role')
        async def mod_role(ctx: commands.Context):
            """Configure the moderator roles"""
            pass

        @mod_role.command(name='add')
        async def mod_add(ctx: commands.Context, *_target):
            """Add a moderator role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref.id,
                        'level': 0
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully added mod role.'))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This is already a mod role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @mod_role.command(name='remove')
        async def mod_remove(ctx: commands.Context, *_target):
            """Remove a moderator role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref.id,
                        'level': 0
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 204:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully removed mod role.'))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This is not a mod role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @config.group(name='admin_role')
        async def admin_role(ctx: commands.Context):
            """Configure administrator roles"""
            pass

        @admin_role.command(name='add')
        async def admin_add(ctx: commands.Context, *_target):
            """Add a administrator role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref.id,
                        'level': 1
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully added admin role.'))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This is already an admin role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @admin_role.command(name='remove')
        async def admin_remove(ctx: commands.Context, *_target):
            """Remove an administrator role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/roles', json={
                    'value': {
                        'id': ref.id,
                        'level': 1
                    }
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 204:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully removed admin role.'))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This is not an admin role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @config.group(name='trusted_role')
        async def trusted_role(ctx: commands.Context):
            """Configure trusted roles"""
            pass

        @trusted_role.command(name='add')
        async def trusted_add(ctx: commands.Context, *_target):
            """Add a trusted role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/trusted_roles', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully added trusted role.'))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This is already a trusted role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @trusted_role.command(name='remove')
        async def trusted_remove(ctx: commands.Context, *_target):
            """Remove a trusted role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/trusted_roles', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 204:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully removed trusted role.'))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('This is not a trusted role.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
        
        @trusted_role.command(name='block_images')
        async def trusted_block_images(ctx: commands.Context, on: str):
            """Turn on or off image link blocking for untrusted users"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/untrusted_block_images', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully toggled untrusted user image blocking.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))

        @config.group(name='welcomer')
        async def welcomer(ctx: commands.Context):
            """Configure the welcomer"""
            pass

        @welcomer.command(name='set_enabled')
        async def welcomer_set_enabled(ctx: commands.Context, on: str):
            """Enable/disable the welcomer"""
            await self.validate_permission_level(2, ctx)

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/use_welcome', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully toggled welcomer.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))

        @welcomer.command(name='message')
        async def welcomer_message(ctx: commands.Context, *_target):
            """Set the welcomer's message, supports the following translation phrases:
            {mention} - Welcomed user's ping
            {server_name} - The name of the server"""
            await self.validate_permission_level(2, ctx)

            message = ' '.join(_target)
            if message.isspace():
                message = 'Hello {mention} and welcome to {server_name}!\n\nRemember to read the rules before interacting in this server!' # fallback

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/welcome_message', json={
                'value': message
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS('Successfully changed welcome message.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))

        @welcomer.command(name='image')
        async def welcomer_image(ctx: commands.Context, image: str = ''):
            """Set the welcomer's image"""
            await self.validate_permission_level(2, ctx)

            url = re.search("(?P<url>https?://[^\s]+)", image).group("url")

            if url:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/welcome_image', json={
                    'value': url
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed welcome image.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please provide a valid image URL!'))

        @welcomer.command(name='channel')
        async def welcomer_channel(ctx: commands.Context, *_target):
            """Set the welcomer's channel"""
            await self.validate_permission_level(2, ctx)

            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/welcome_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed the welcomer channel.'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('An unknown error occurred while performing this action.'))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid channel!'))
        
        @config.group(name='xp')
        async def xp(ctx: commands.Context):
            """Configure the xp giver"""
            pass

        def change_xp_gain(guild, role_id, value):
            orig_result = requests.get(f'http://localhost:5000/guilddata/{guild}/cfg/xp_gain', headers={
                'authorization': bot_config.SECRET_KEY
            })

            orig = (orig_result.status_code == 200 and orig_result.json().get('result')) or {}
            orig[role_id] = value
            
            result = requests.patch(f'http://localhost:5000/guilddata/{guild}/cfg/xp_gain', json={
                'value': orig
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
            return result

        @xp.command(name='all')
        async def xp_all(ctx: commands.Context, value):
            """Set the XP gain for all users"""
            if int(value) is not None:
                result = change_xp_gain(ctx.server.id, -1, int(value))

                if result.status_code >= 200 and result.status_code < 300:
                    await ctx.reply(embed=EMBED_SUCCESS('Successfully changed the XP gain for all members'))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR())
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid number!'))
        
        @xp.command(name='role')
        async def xp_role(ctx: commands.Context, role: str, value: str):
            """Set the XP gain for a specified role, setting to 0 disables"""
            role_object = await self.convert_role(ctx, role)
            if role_object is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid role!'))
                return
            if int(value) is not None:
                result = change_xp_gain(ctx.server.id, role_object.get('id'), int(value))

                if result.status_code >= 200 and result.status_code < 300:
                    await ctx.reply(embed=EMBED_SUCCESS(f'Successfully changed the XP gain for role <@{role_object.get("id")}>'), silent=True)
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR())
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR('Please specify a valid number!'))

        async def on_bulk_member_roles_update(event: BulkMemberRolesUpdateEvent):
            if event.server_id == 'aE9Zg6Kj':
                for member in event.after:
                    roles = member._role_ids

                    if 32612283 in roles:
                        lvl = 3
                    elif 32612284 in roles:
                        lvl = 2
                    elif 32612285 in roles:
                        lvl = 1
                    else:
                        lvl = 0
                    user_data_req = requests.patch(f'http://localhost:5000/userinfo/aE9Zg6Kj/{member.id}', json={
                        'premium': lvl
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
            for member in event.after:
                if member.id == event.server.owner.id:
                    permission_level = 4 # We know the owner of the guild is a moderator, bypass any unnecessary calls and checks
                elif await self.user_can_manage_server(member):
                    permission_level = 3
                else:
                    _lvl = 0
                    role_config_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}/cfg/roles', headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    role_config_json: dict = role_config_req.json()
                    if role_config_req.status_code == 200:
                        role_set: list[dict] = role_config_json['result']
                        role_ids: list[int] = member._role_ids
                        for cfg in role_set:
                            try:
                                i = role_ids.index(int(cfg.get('id')))
                                lvl = int(cfg.get('level'))
                                if lvl + 1 > _lvl:
                                    _lvl = lvl + 1
                            except Exception as e:
                                pass
                    permission_level = _lvl
                user_data_set_req = requests.patch(f'http://localhost:5000/getguilduser/{event.server_id}/{member.id}', json={
                    'permission_level': permission_level
                    }, headers={
                    'authorization': bot_config.SECRET_KEY
                })
        bot.member_role_update_listeners.append(on_bulk_member_roles_update)

        async def on_message(message: ChatMessage):
            id = f'{message.guild.id}/{message.author.id}'
            if message.author.bot:
                return
            if message.channel_id == LOGIN_CHANNEL_ID:
                # Do login stuff
                result = requests.post(f'http://localhost:5000/auth/status/{message.content}/{message.author_id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                if result.status_code == 200:
                    em = Embed(
                        title='Success',
                        description='You should now be logged in on your browser. If you closed the login page before this then you will have to login again.',
                        colour=Colour.gilded()
                    )
                    await message.reply(embed=em, private=True, delete_after=10)
                else:
                    em = Embed(
                        title='Failure',
                        description='Please submit a valid login code here, and remember not to post anything here that other users tell you to!',
                        colour=Colour.gilded()
                    )
                    await message.reply(embed=em, private=True, delete_after=10)
                await message.delete()
            if xp_cache.get(id):
                return # They cannot gain xp at this point in time
            guild_data: dict = self.get_guild_data(message.server_id)
            config = guild_data.get('config', {})
            xp_gain = config.get('xp_gain', {})
            print(xp_gain)
            if len(xp_gain) > 0 and any([item > 0 for item in list(xp_gain.values())]):
                # Only go further if there are any gains that a user can possibly obtain
                member = await message.guild.getch_member(message.author.id)
                role_ids = await member.fetch_role_ids()
                gain = 0
                for role_id in xp_gain.keys():
                    role_id = int(role_id)
                    value = int(xp_gain.get(str(role_id)))
                    if role_id == -1 or int(role_id) in role_ids:
                        gain += value
                if gain > 0:
                    xp_cache.set(id, True)
                    await member.award_xp(gain)
        self.bot.message_listeners.append(on_message)

        @bot.event
        async def on_bot_remove(event: BotRemoveEvent):
            result = requests.patch(f'http://localhost:5000/guilddata/{event.server_id}', json={
                'active': False
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
        
        @bot.event
        async def on_bot_add(event: BotAddEvent):
            server = event.server
            default = await server.fetch_default_channel()
            em = Embed(
                title='Hello!',
                description=f'Thanks <@{event.member_id}> for inviting me to **{server.name}!** To learn more about Server Guard use the /help command, or join our support server and look at the Information channel!',
                timestamp=datetime.now(),
                colour=Colour.gilded()
            ) \
            .set_footer(text='Server Guard') \
            .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
            .add_field(name='Links', value='[Support Server](https://www.guilded.gg/server-guard) • [Invite](https://www.guilded.gg/b/c10ac149-0462-4282-a632-d7a8808c6c6e)', inline=False)
            await default.send(embed=em)

            result = requests.patch(f'http://localhost:5000/guilddata/{event.server_id}', json={
                'active': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
