import asyncio
import re
from project.modules.base import Module
from project.modules.moderation import reset_filter_cache
from project.helpers.embeds import *
from project import bot_config
from guilded.ext import commands
from guilded.ext.commands.help import HelpCommand, Paginator
from guilded import Embed, BulkMemberRolesUpdateEvent, BotAddEvent, http
from datetime import datetime
from humanfriendly import format_timespan

import os
import requests
import itertools

member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

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
            .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp')
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
            f"Type {self.context.clean_prefix}{command_name} command for more info on a command.\n"
            f"You can also type {self.context.clean_prefix}{command_name} category for more info on a category."
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
                await ctx.reply(embed=Embed(
                    title='Bot Analytics',
                    colour=Colour.gilded(),
                )\
                .add_field(name='Server Count', value=str(len(bot.servers)))\
                .add_field(name='Uptime', value=format_timespan(uptime))\
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
                await ctx.reply('Successfully changed automod spam limit.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='admin_contact')
        async def config_admin_contact(ctx: commands.Context, *_account):
            """Specify an admin account the user can contact"""
            await self.validate_permission_level(2, ctx)
            account = ' '.join(account)

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
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/admin_contact', json={
                    'value': account
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply('Successfully changed tor blocking status.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
                await ctx.reply('Successfully changed tor blocking status.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')

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
                await ctx.reply('Successfully changed invite filtering status.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
                await ctx.reply('Successfully changed duplicate text filtering status.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
                await ctx.reply('Successfully changed url filtering status.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        @config.command(name='mute_role')
        async def config_mute_role(ctx: commands.Context, *_target):
            """Set the mute role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

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
        async def config_verif_channel(ctx: commands.Context, *_target):
            """Set the verification channel, specifying no channel disables verification"""
            target = ' '.join(_target)
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
            elif target.isspace() or target == '':
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ''
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply('Successfully disabled verification.')
                else:
                    await ctx.reply('An unknown error occurred while performing this action.')
            else:
                await ctx.reply('Please specify a valid channel!')
        
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
            """Disable the NSFW filter"""
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
        async def config_message_logs_channel(ctx: commands.Context, *_target):
            """Set the message logs channel"""
            target = ' '.join(_target)
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
        async def config_traffic_logs_channel(ctx: commands.Context, *_target):
            """Set the traffic logs channel"""
            target = ' '.join(_target)
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
        async def config_logs_channel(ctx: commands.Context, *_target):
            """Set the verify logs channel"""
            target = ' '.join(_target)
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
        async def config_automod_logs_channel(ctx: commands.Context, *_target):
            """Set the automod logs channel"""
            target = ' '.join(_target)
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
        async def config_verified_role(ctx: commands.Context, *_target):
            """Set the verified role"""
            target = ' '.join(_target)
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
        async def config_unverified_role(ctx: commands.Context, *_target):
            """Set the unverified role"""
            print(_target)
            target = ' '.join(_target)
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
                await ctx.reply(f'Successfully added "{word}" to filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
                await ctx.reply(f'Successfully removed "{word}" from filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')

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
                await ctx.reply('Successfully set toxicity filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
                await ctx.reply('Successfully set hate speech filter.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
        async def mod_remove(ctx: commands.Context, *_target):
            """Remove a moderator role"""
            target = ' '.join(_target)
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
        async def admin_remove(ctx: commands.Context, *_target):
            """Remove an administrator role"""
            target = ' '.join(_target)
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
