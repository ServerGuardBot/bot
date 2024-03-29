from json import JSONEncoder
from pydoc import describe
from project.modules.base import Module
from project.modules.moderation import reset_filter_cache
from project.helpers.embeds import *
from project.helpers.Cache import Cache
from project.server.api.guilds import getLevel
from project import BotAPI, bot_config
from guilded.ext import commands
from guilded.ext.commands.help import HelpCommand, Paginator
from guilded import Embed, BulkMemberRolesUpdateEvent, MessageReactionAddEvent, BotAddEvent, BotRemoveEvent, ChatMessage, Emote, \
    ServerChannelCreateEvent, ServerChannelDeleteEvent, RoleCreateEvent, RoleDeleteEvent, RoleUpdateEvent, MemberRemoveEvent, \
    MemberJoinEvent
from datetime import datetime
from humanfriendly import format_timespan, parse_timespan
from project.helpers.translator import getLanguages, translate
from pyppeteer import launch

import guilded.http as http

import os
import re
import requests
import itertools

LOGIN_CHANNEL_ID = '1f6fae7f-6cdf-403d-80b9-623a76f8b621'
TEST_LOGIN_CHANNEL_ID = 'aa853405-37f8-4d8a-a4f8-3196b7a4a379'
SUPPORT_SERVER_ID = 'aE9Zg6Kj'

member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

xp_cache = Cache(60)
login_cache = Cache(60)
xp_update_cache = Cache(30)

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
                title = await translate(self.language, 'help.title'),
                description = page,
                colour = Colour.gilded()
            ) \
            .set_footer(text='Server Guard') \
            .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
            .add_field(name=(await translate(self.language, 'help.links')), value=f'[{await translate(self.language, "link.support")}](https://serverguard.xyz/support) • [{await translate(self.language, "link.website")}](https://serverguard.xyz) • [{await translate(self.language, "link.invite")}](https://serverguard.xyz/invite) • [{await translate(self.language, "link.docs")}](https://serverguard.xyz/docs)', inline=False)
            await destination.send(embed=em)
    
    def shorten_text(self, text):
        """:class:`str`: Shortens text to fit into the :attr:`width`."""
        if len(text) > self.width:
            return text[:self.width - 3].rstrip() + '...'
        return text

    async def get_ending_note(self):
        """:class:`str`: Returns help command's ending note. This is mainly useful to override for i18n purposes."""
        command_name = self.invoked_with
        return (
            await translate(self.language, 'help.info')
        )
    
    def generate_command_translation_key(self, command: commands.Command):
        key = command.name.lower()
        parent = command.parent

        while parent is not None and parent.name.lower() != 'config':
            key = f'{parent.name.lower()}.{key}'
            parent = parent.parent
        key = f'command.{key}'
        return key
    
    async def add_bot_commands_formatting(self, commands, heading):
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
            joined = ', '.join([c.name for c in commands])
            self.paginator.add_line(f'__**{await translate(self.language, "category." + heading)}**__')
            self.paginator.add_line(joined)
    
    async def add_subcommand_formatting(self, command):
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
        self.paginator.add_line(fmt.format(command.name, await translate(self.language, self.generate_command_translation_key(command))))
    
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
    
    async def add_command_formatting(self, command):
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
                self.paginator.add_line(await translate(self.language, self.generate_command_translation_key(command)), empty=True)
            except RuntimeError:
                for line in (await translate(self.language, self.generate_command_translation_key(command))).splitlines():
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
        self.language = self.context.message.language
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
            await self.add_bot_commands_formatting(commands, category)

        note = await self.get_ending_note()
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
                await self.add_subcommand_formatting(command)

            note = await self.get_ending_note()
            if note:
                self.paginator.add_line()
                self.paginator.add_line(note)

        await self.send_pages()

    async def send_group_help(self, group):
        await self.add_command_formatting(group)

        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)
        if filtered:

            self.paginator.add_line(f'**{self.commands_heading}**')
            for command in filtered:
                await self.add_subcommand_formatting(command)

            note = await self.get_ending_note()
            if note:
                self.paginator.add_line()
                self.paginator.add_line(note)

        await self.send_pages()

    async def send_command_help(self, command):
        await self.add_command_formatting(command)
        self.paginator.close_page()
        await self.send_pages()

class General(commands.Cog):
    pass

class GeneralModule(Module):
    name = 'General'

    async def scan_auto_roles(self, member: Member, user_join: bool=False):
        bot = self.bot

        autoroles_req = requests.get(f'http://localhost:5000/autoroles/{member.server_id}', headers={
            'authorization': bot_config.SECRET_KEY
        })
        if autoroles_req.ok:
            to_add, to_remove = [], []
            print(f'Role ids for member {member.id} on server {member.server_id}:\n{member._role_ids}\n')
            for autorole in autoroles_req.json()['roles']:
                data: dict = autorole['data']
                has_roles: list = data['has_roles']
                has_all: bool = data['has_all']
                not_has_roles: list = data['not_has_roles']
                not_has_all: bool = data['not_has_all']
                target_role: int = autorole['role']
                join_role: bool = data.get('join_role', False)
                delay_time: int = data.get('delay_time', 0)
                should_have = False

                if delay_time > 0 and user_join:
                    # TODO: Send request to schedule role addition for user
                    continue

                if join_role and not user_join:
                    continue
                if len(has_roles) > 0:
                    if has_all:
                        if all([role in member._role_ids for role in has_roles]):
                            should_have = True
                    else:
                        if any([role in member._role_ids for role in has_roles]):
                            should_have = True
                if len(not_has_roles) > 0:
                    if len(has_roles) > 0:
                        # Act like a blacklist if there are roles in has_roles
                        if not_has_all:
                            if all([role in member._role_ids for role in not_has_roles]):
                                should_have = False
                        else:
                            if any([role in member._role_ids for role in not_has_roles]):
                                should_have = False
                    else:
                        # Otherwise, give the role to them as long as they
                        # don't have any of the roles in not_has_roles
                        if not_has_all:
                            if not all([role in member._role_ids for role in not_has_roles]):
                                should_have = True
                        else:
                            if not any([role in member._role_ids for role in not_has_roles]):
                                should_have = True
                if should_have:
                    print(f'Checking if can add {target_role} to {member.id} on server {member.server_id}\n')
                    if not target_role in member._role_ids:
                        to_add.append(target_role)
                        print(f'Will add {target_role} to {member.id} on server {member.server_id}\n')
                else:
                    print(f'Checking if can remove {target_role} from {member.id} on server {member.server_id}\n')
                    if target_role in member._role_ids:
                        to_remove.append(target_role)
                        print(f'Will remove {target_role} from {member.id} on server {member.server_id}\n')
            for role in to_add:
                if role in to_remove:
                    pass
                try:
                    await bot.http.assign_role_to_member(member.server_id, member.id, role)
                except Exception as e:
                    # Only have this try block so that the request failing
                    # does not interrupt the rest of the process
                    print(f'Failed to assign role {role} to {member.id} on server {member.server_id} due to {e}\n')
            for role in to_remove:
                try:
                    await bot.http.remove_role_from_member(member.server_id, member.id, role)
                except Exception as e:
                    print(f'Failed to remove role {role} from {member.id} on server {member.server_id} due to {e}\n')

    def initialize(self):
        bot = self.bot

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
        async def reload(_, ctx: commands.Context):
            """Bot creator-only command to reload the bot"""
            if ctx.author.id == 'm6YxwpQd':
                await ctx.reply('Reloading bot...')
                
                os.system('killall -KILL gunicorn') # Forcefully kill the bot no matter what state it is in
        
        reload.cog = cog

        @bot.command()
        async def language(_, ctx: commands.Context, lang: str):
            """Set the language the bot will respond in"""
            validLangs = await getLanguages()

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            for key in validLangs.keys():
                name = validLangs[key]
                if lang.lower() == name.lower():
                    user_data_req = requests.patch(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', json={
                        'language': key
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(key, 'command.language.success')))
                    return
            await ctx.reply(embed=EMBED_COMMAND_ERROR((await translate(curLang, 'command.language.failure')
                + '\n'
                + '\n'.join(validLangs.values())
            )))
        
        language.cog = cog

        @bot.command()
        async def serverinfo(_, ctx: commands.Context):
            """Get information about the server you are in"""
            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')
            server = ctx.server

            em = Embed(
                title = server.name,
                colour = Colour.gilded()
            ) \
            .set_footer(text='Server Guard') \
            .set_thumbnail(url=(server.icon and server.icon.aws_url) or IMAGE_DEFAULT_AVATAR) \
            .add_field(name=(await translate(curLang, 'serverinfo.about')), value=server.about, inline=False) \
            .add_field(name=(await translate(curLang, 'serverinfo.owner')), value=f'<@{server.owner_id}>', inline=True) \
            .add_field(name=(await translate(curLang, 'serverinfo.members')), value=server.member_count, inline=True) \
            .add_field(name=(await translate(curLang, 'serverinfo.verified')), value=server.verified and 'Yes' or 'No', inline=True) \
            .add_field(name=(await translate(curLang, 'serverinfo.timezone')), value=server.timezone and server.timezone.key or 'None', inline=True) \
            .add_field(name=(await translate(curLang, 'serverinfo.created')), value=format_timespan(datetime.now() - server.created_at), inline=True) \
            .add_field(name=(await translate(curLang, 'serverinfo.type')), value=server.type.name.capitalize(), inline=True)
            await ctx.reply(embed=em, silent=True)
        
        serverinfo.cog = cog

        @bot.command()
        async def support(_, ctx: commands.Context):
            """Get a link to the support server"""
            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            await ctx.reply(embed=Embed(
                title=await translate(curLang, 'link.support'),
                description=f'[{await translate(curLang, "link")}](https://serverguard.xyz/support)'
            ).set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80'))
        
        support.cog = cog
        
        @bot.command()
        async def invite(_, ctx: commands.Context):
            """Get an invite link for the bot"""
            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            await ctx.reply(embed=Embed(
                title=await translate(curLang, 'link.invite'),
                description=f'[{await translate(curLang, "link")}](https://serverguard.xyz/invite)'
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

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_spam', json={
                'value': amount
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.spam.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @config.command(name='admin_contact')
        async def config_admin_contact(ctx: commands.Context, *_account):
            """Specify an admin account the user can contact"""
            await self.validate_permission_level(2, ctx)
            account = ' '.join(_account)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

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
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.admin_contact.error")))
                    return

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.admin_contact.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @config.command(name='tor_block')
        async def config_tor_block(ctx: commands.Context, on: str):
            """Turn on or off the tor exit node blocklist for verification"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/block_tor', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.tor_block.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))

        @config.command(name='invite_link_filter')
        async def config_invite_link_filter(ctx: commands.Context, on: str):
            """Turn on or off the discord/guilded invite link filter"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/invite_link_filter', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.invite_link_filter.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @config.command(name='duplicate_filter')
        async def config_duplicate_filter(ctx: commands.Context, on: str):
            """Turn on or off the duplicate text filter"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_duplicate', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.duplicate_filter.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @config.command(name='url_filter')
        async def config_url_filter(ctx: commands.Context, on: str):
            """Turn on or off the malicious URL filter"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/url_filter', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.url_filter.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @config.command(name='mute_role')
        async def config_mute_role(ctx: commands.Context, *_target):
            """Set the mute role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/mute_role', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.mute_role.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))

        @config.command(name='verification_channel')
        async def config_verif_channel(ctx: commands.Context, *_target):
            """Set the verification channel, specifying no channel disables verification"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.verification_channel.changed")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            elif target.isspace() or target == '':
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verification_channel', json={
                    'value': ''
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.verification_channel.disabled")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))
        
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

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/nsfw_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.nsfw_logs_channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))
        
        @config.command(name='disable_nsfw')
        async def config_disable_nsfw(ctx: commands.Context):
            """Disable the NSFW filter"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/nsfw_logs_channel', json={
                'value': ''
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.disable_nsfw.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @config.command(name='message_logs_channel')
        async def config_message_logs_channel(ctx: commands.Context, *_target):
            """Set the message logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/message_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.message_logs_channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))
        
        @config.command(name='traffic_logs_channel')
        async def config_traffic_logs_channel(ctx: commands.Context, *_target):
            """Set the traffic logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/traffic_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.traffic_logs_channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))

        @config.command(name='verify_logs_channel')
        async def config_verify_logs_channel(ctx: commands.Context, *_target):
            """Set the verify logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verify_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.verify_logs_channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))

        @config.command(name='action_logs_channel')
        async def config_action_logs_channel(ctx: commands.Context, *_target):
            """Set the action logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/action_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.action_logs_channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))

        @config.command(name='automod_logs_channel')
        async def config_automod_logs_channel(ctx: commands.Context, *_target):
            """Set the automod logs channel"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_channel(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/automod_logs_channel', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.automod_logs_channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))
        
        @config.command(name='verified_role')
        async def config_verified_role(ctx: commands.Context, *_target):
            """Set the verified role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/verified_role', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.verified_role.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
        @config.command(name='unverified_role')
        async def config_unverified_role(ctx: commands.Context, *_target):
            """Set the unverified role"""
            print(_target)
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/unverified_role', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.unverified_role.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
        @config.group(name='filter')
        async def filter(ctx: commands.Context):
            """Configure the filters"""
            pass
        
        @filter.command(name='add')
        async def filter_add_word(ctx: commands.Context, word: str):
            """Add a word to the filter list"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/filters', json={
                'value': word.lower()
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                reset_filter_cache(ctx.server.id)
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.filter.add.success", {'word': word})))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @filter.command(name='remove')
        async def filter_remove_word(ctx: commands.Context, word: str):
            """Remove a word from the filter list"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/filters', json={
                'value': word.lower()
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 204:
                reset_filter_cache(ctx.server.id)
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.filter.remove.success", {'word': word})))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))

        @filter.command(name='toxicity')
        async def filter_toxicity(ctx: commands.Context, sensitivity: int=0):
            """Set the toxicity filter's threshold, [0-100] (0 disables)"""
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/toxicity', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.filter.toxicity.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @filter.command(name='hatespeech')
        async def filter_hatespeech(ctx: commands.Context, sensitivity: int=0):
            """Set the hate-speech filter's threshold, [0-100] (0 disables)"""
            await self.validate_permission_level(2, ctx)
            sensitivity = min(sensitivity, 100)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/hatespeech', json={
                'value': sensitivity
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.filter.hatespeech.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
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

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

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
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.mod_role.add.success")))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.mod_role.add.error")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
        @mod_role.command(name='remove')
        async def mod_remove(ctx: commands.Context, *_target):
            """Remove a moderator role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

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
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.mod_role.remove.success")))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.mod_role.remove.error")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
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

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

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
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.admin_role.add.success")))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.admin_role.add.error")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
        @admin_role.command(name='remove')
        async def admin_remove(ctx: commands.Context, *_target):
            """Remove an administrator role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

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
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.admin_role.remove.success")))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.admin_role.remove.error")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
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

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.post(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/trusted_roles', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.trusted_role.add.success")))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.trusted_role.add.error")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
        @trusted_role.command(name='remove')
        async def trusted_remove(ctx: commands.Context, *_target):
            """Remove a trusted role"""
            target = ' '.join(_target)
            await self.validate_permission_level(2, ctx)
            ref = await self.convert_role(ctx, target)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if ref is not None:
                result = requests.delete(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/trusted_roles', json={
                    'value': ref.id
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 204:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.trusted_role.remove.success")))
                elif result.status_code == 400:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.trusted_role.remove.error")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
        
        @trusted_role.command(name='block_images')
        async def trusted_block_images(ctx: commands.Context, on: str):
            """Turn on or off image link blocking for untrusted users"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/untrusted_block_images', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.trusted_role.block_images.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))

        @config.group(name='welcomer')
        async def welcomer(ctx: commands.Context):
            """Configure the welcomer"""
            pass

        @welcomer.command(name='set_enabled')
        async def welcomer_set_enabled(ctx: commands.Context, on: str):
            """Enable/disable the welcomer"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/use_welcome', json={
                'value': on == 'yes' and 1 or 0
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.welcomer.set_enabled.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))

        @welcomer.command(name='message')
        async def welcomer_message(ctx: commands.Context, *_target):
            """Set the welcomer's message, supports the following translation phrases:
            {mention} - Welcomed user's ping
            {server_name} - The name of the server"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            message = ' '.join(_target)
            if message.isspace():
                message = 'Hello {mention} and welcome to {server_name}!\n\nRemember to read the rules before interacting in this server!' # fallback

            result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/welcome_message', json={
                'value': message
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200 or result.status_code == 201:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.welcomer.message.success")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))

        @welcomer.command(name='image')
        async def welcomer_image(ctx: commands.Context, image: str = ''):
            """Set the welcomer's image"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

            url = re.search("(?P<url>https?://[^\s\]\[]+)", image).group("url")

            if url:
                result = requests.patch(f'http://localhost:5000/guilddata/{ctx.server.id}/cfg/welcome_image', json={
                    'value': url
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })

                if result.status_code == 200 or result.status_code == 201:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.welcomer.image.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.image")))

        @welcomer.command(name='channel')
        async def welcomer_channel(ctx: commands.Context, *_target):
            """Set the welcomer's channel"""
            await self.validate_permission_level(2, ctx)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')

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
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.welcomer.channel.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.channel")))
        
        @bot.group(invoke_without_command=True)
        async def reminder(_, ctx: commands.Context):
            """Manage reminders"""
            pass

        reminder.cog = cog
        
        @reminder.command(name='add')
        async def remindme(ctx: commands.Context, timespan: str, *_reason):
            """Remind yourself to do something"""
            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')
            reason = ' '.join(_reason)
            try:
                timespan = parse_timespan(timespan)
            except:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
                timespan = None
            if timespan is not None:
                result = requests.post(f'http://localhost:5000/reminders/{ctx.server.id}/{ctx.author.id}', json={
                    'channel': ctx.channel.id,
                    'description': reason,
                    'ends': timespan is not None and datetime.now().timestamp() + timespan or None
                }, headers={
                    'authorization': bot_config.SECRET_KEY
                })
                if result.ok:
                    em = Embed(
                        title = await translate(curLang, 'command.reminder.title'),
                        colour = Colour.blue(),
                        description = await translate(curLang, 'command.reminder.success')
                    )
                    await ctx.reply(embed=em)
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
        
        @reminder.command(name='list')
        async def remindme_list(ctx: commands.Context):
            """List your reminders"""
            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')
            result = requests.get(f'http://localhost:5000/reminders/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            if result.ok:
                warns = result.json()
                em = Embed(
                    title = await translate(curLang, 'command.reminders.title'),
                    description = len(warns) > 0 and ''.join([f'{item["id"]} | {item["description"]} - {datetime.fromtimestamp(item["ends"]).strftime("%b %d %Y at %H:%M %p %Z")}\n' for item in warns['result']]) or await translate(curLang, 'command.reminders.none'),
                    colour = Colour.blue()
                )
                await ctx.reply(embed=em, private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @reminder.command(name='delete')
        async def remindme_delete(ctx: commands.Context, id: str):
            """Delete a reminder"""
            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')
            result = requests.delete(f'http://localhost:5000/reminders/{ctx.server.id}/{ctx.author.id}/{id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, 'command.reminders.delete.success')))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, 'command.error')))

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

                user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                user_info = user_data_req.json()
                curLang = user_info.get('language', 'en')

                if result.status_code >= 200 and result.status_code < 300:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.xp.all.success")))
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.number")))
        
        @xp.command(name='role')
        async def xp_role(ctx: commands.Context, role: str, value: str):
            """Set the XP gain for a specified role, setting to 0 disables"""
            role_object = await self.convert_role(ctx, role)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{ctx.server.id}/{ctx.author.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info = user_data_req.json()
            curLang = user_info.get('language', 'en')
            if role_object is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.role")))
                return
            if int(value) is not None:
                result = change_xp_gain(ctx.server.id, role_object.get('id'), int(value))

                if result.status_code >= 200 and result.status_code < 300:
                    await ctx.reply(embed=EMBED_SUCCESS(await translate(curLang, "command.xp.role.success", {"role_id": role_object.get("id")})), silent=True)
                else:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error")))
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(curLang, "command.error.number")))

        async def on_bulk_member_roles_update(event: BulkMemberRolesUpdateEvent):
            # xp_remove_old
            guild_data: dict = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            xp_remove_old = config.get('xp_remove_old', 0) == 1
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
                    requests.patch(f'http://localhost:5000/userinfo/aE9Zg6Kj/{member.id}', json={
                        'premium': lvl
                    }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
            for member in event.after:
                if xp_remove_old:
                    __cache = config.get('__cache', {})
                    level_roles = __cache.get('level_roles')

                    with BotAPI() as bot_api:
                        if level_roles is None or level_roles['0']['lastUpdated'] + (60 * 15) < datetime.now().timestamp():
                                level_roles_req = (await bot_api.request(http.Route('GET', f'/teams/{event.server_id}/level_rewards', override_base=http.Route.USER_BASE))) or []
                                level_roles = [
                                    {
                                        'lastUpdated': datetime.now().timestamp(),
                                        'id': '0',
                                        'roles': [
                                            {
                                                'level': role['level'],
                                                'id': role['teamRoleId'],
                                            } for role in level_roles_req],
                                    }
                                ]
                                requests.put(f'http://localhost:5000/data/cache/{event.server_id}/level_roles', headers={
                                    'authorization': bot_config.SECRET_KEY
                                }, json=level_roles)
                                level_roles = {
                                    '0': level_roles[0],
                                }
                        level_roles = (level_roles['0'])['roles']
                        lower_roles, highest_role = [], {'level': 0, 'id': -3429785678456}
                        for role in level_roles:
                            role: dict
                            if role['id'] in member._role_ids:
                                if role['level'] >= highest_role['level']:
                                    if role['level'] != highest_role['level'] and highest_role['level'] > 0:
                                        # Only add the highest role to lower_roles if the level is actually lower than this role
                                        lower_roles.append(highest_role['id'])
                                    highest_role = role
                        if len(lower_roles) > 0:
                            for role in lower_roles:
                                await bot_api.request(http.Route('DELETE', f'/servers/{event.server_id}/members/{member.id}/roles/{role}'))
                
                await self.scan_auto_roles(member)

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

        automated_responses = [
            {
                'triggers': [['how','help'], ['get','invite','add','inviting','adding','getting'], ['server guard','bot']],
                'response': Embed(
                    title='Invite our Bot',
                    description='[Link](https://serverguard.xyz/invite)'
                ) \
                .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80')
            },
            {
                'triggers': ['how', 'use', ['bot','verification','filter','filters','warnings','warns']],
                'response': Embed(
                    title='Read our Documentation',
                    description='[Link](https://serverguard.xyz/docs)'
                ) \
                .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80')
            },
            {
                'triggers': ['how', ['setup','configure','config','change','modify','alter'], ['bot','verification','filter','filters','warnings','warns']],
                'response': Embed(
                    title='Read our Documentation',
                    description='[Link](https://serverguard.xyz/docs)'
                ) \
                .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80')
            }
        ]

        async def on_message(message: ChatMessage):
            id = f'{message.guild.id}/{message.author.id}'
            if message.author.bot:
                return
            channel_payload = []

            thisChannel = await message.server.getch_channel(message.channel_id)
            channel_payload.append({
                'id': thisChannel.id,
                'name': thisChannel.name,
                'type': thisChannel.type.name,
                'jump': thisChannel.jump_url,
            })

            if len(message.raw_channel_mentions) > 0:
                for channel_id in message.raw_channel_mentions:
                    if channel_id == message.channel_id: continue # This channel is already in the payload
                    channel = await message.server.getch_channel(channel_id)
                    channel_payload.append({
                        'id': channel.id,
                        'name': channel.name,
                        'type': channel.type.name,
                        'jump': channel.jump_url,
                    })
            if len(channel_payload) > 0:
                requests.put(f'http://localhost:5000/data/cache/{message.guild.id}/channels', headers={
                    'authorization': bot_config.SECRET_KEY
                }, json=channel_payload)
            if message.server_id == SUPPORT_SERVER_ID and not (message.channel_id == LOGIN_CHANNEL_ID or message.channel_id == TEST_LOGIN_CHANNEL_ID):
                content = message.content.lower().strip()
                for item in automated_responses:
                    triggered = True
                    for word in item['triggers']:
                        if isinstance(word, list):
                            t = False
                            for w in word:
                                if w in content:
                                    t = True
                            if not t:
                                triggered = False
                                break
                        else:
                            if not word in content:
                                triggered = False
                                break
                    if triggered:
                        await message.reply(embed=item['response'])
            if message.channel_id == LOGIN_CHANNEL_ID or message.channel_id == TEST_LOGIN_CHANNEL_ID:
                # Do login stuff
                await message.delete() # Delete it first so there is minimal time-frame for others to see the code
                status_result = requests.get(f'http://localhost:5000/auth/status/{message.content}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                if status_result.status_code == 200:
                    login_cache.set(message.author_id, message.content)
                    data: dict = status_result.json()
                    em = Embed(
                        title='Verify Login',
                        description=f'{message.author.mention}, Are you trying to log in from **{data.get("location")}** on **{data.get("browser")} {data.get("platform")}?** If so, please react to this message with a :white_check_mark:',
                        colour=Colour.gilded()
                    )
                    resp = await message.reply(embed=em, private=True, delete_after=60)
                    await resp.add_reaction(Emote(state=bot.http, data={
                        'id': 90002171,
                        'name': 'white_check_mark'
                    })) # 90002171 = white_check_mark
                else:
                    em = Embed(
                        title='Failure',
                        description=f'{message.author.mention}, Please submit a valid login code here, and remember not to post anything here that other users tell you to!',
                        colour=Colour.gilded()
                    )
                    await message.reply(embed=em, private=True, delete_after=10)
            guild_data: dict = self.get_guild_data(message.server_id)
            config = guild_data.get('config', {})
            xp_gain = config.get('xp_gain', {})

            try:
                if xp_update_cache.get(id) == None:
                    xp_update_cache.set(id, True)
                    current_xp: int = await message.author.award_xp(0) # Guilded doesn't support fetching XP, but returns the total amount after awarding
                    # so we award 0 XP to get the current XP, it's a hack but it works I guess
                    db_xp_user_req = requests.get(f'http://localhost:5000/getguilduser/{message.server_id}/{message.author.id}/xp', headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    requests.patch(f'http://localhost:5000/getguilduser/{message.server_id}/{message.author.id}/xp', json={
                        'xp': current_xp
                        }, headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    if db_xp_user_req.ok:
                        db_xp_user = db_xp_user_req.json()
                        level_now, level_before = getLevel(current_xp), getLevel(db_xp_user.get('xp', 0))
                        if config.get('xp_announce_lu', 0) == 1 and level_now > level_before:
                            print('OUTPUTTING LEVEL UP ANNOUNCEMENT')
                            browser = await launch({
                                'handleSIGINT': False,
                                'handleSIGTERM': False,
                                'handleSIGHUP': False,
                                'headless': True,
                                'args': [
                                    '--no-sandbox',
                                    '--disable-extensions',
                                    '--disable-breakpad',
                                    '--disable-background-networking',
                                    '--disable-background-timer-throttling',
                                    '--disable-backgrounding-occluded-windows',
                                    '--disable-component-update',
                                    '--disable-default-apps',
                                    '--disable-dev-shm-usage',
                                    '--disable-domain-reliability',
                                    '--disable-features=AudioServiceOutOfProcess',
                                    '--disable-hang-monitor',
                                    '--disable-ipc-flooding-protection',
                                    '--disable-notifications',
                                    '--disable-offer-store-unmasked-wallet-cards',
                                    '--disable-popup-blocking',
                                    '--disable-print-preview',
                                    '--disable-prompt-on-repost',
                                    '--disable-renderer-backgrounding',
                                    '--disable-setuid-sandbox',
                                    '--disable-speech-api',
                                    '--disable-sync',
                                    '--hide-scrollbars',
                                    '--ignore-gpu-blacklist',
                                    '--metrics-recording-only',
                                    '--mute-audio',
                                    '--no-default-browser-check',
                                    '--no-first-run',
                                    '--no-pings',
                                    '--no-zygote',
                                    '--password-store=basic',
                                    '--use-gl=swiftshader',
                                    '--use-mock-keychain',
                                ],
                            })
                            page = await browser.newPage()
                            await page.goto(f'http://localhost:5000/rankcard/{message.server_id}/{message.author.id}?levelup=show', {'waitUntil': 'networkidle0'})
                            image = await page.screenshot({
                                'omitBackground': True,
                                'clip': {
                                    'width': 900,
                                    'height': 290,
                                    'x': 0,
                                    'y': 0,
                                }
                            })
                            await browser.close()
                            id = requests.post(f'http://localhost:5000/serve', json={
                                'file': image.hex()
                            }, headers={
                                'authorization': bot_config.SECRET_KEY
                            })
                            print(f'File served with id {id.json()["id"]}')
                            await message.reply(embed=Embed().set_image(url=f'https://api.serverguard.xyz/serve/{id.json()["id"]}'))
            except Exception as e:
                print(f"Failed to update internal user xp: {e}")

            if xp_cache.get(id):
                return # They cannot gain xp at this point in time

            requests.patch(f'http://localhost:5000/guilddata/{message.server_id}', json={
                'active': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            }) # Since the bot received a message from the server, make sure its active state is accurate in the DB
            # As in some cases, a server might be added while the bot is restarting.

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
            if message.content.lower().startswith(bot.command_prefix) and await self.is_moderator(await message.server.getch_member(message.author_id)):
                guild_data: dict = self.get_guild_data(message.server_id)
                config: dict = guild_data.get('config', {})

                if config.get('silence_commands', False):
                    await message.delete()
                if config.get('log_commands', False):
                    logs_channel_id = config.get('action_logs_channel')
                    if logs_channel_id != None:
                        logs_channel = await message.server.getch_channel(logs_channel_id)

                        em = Embed(
                            title = 'Command Usage',
                            colour = Colour.gilded()
                        )
                        em.set_thumbnail(url=message.author.avatar != None and message.author.avatar.aws_url or IMAGE_DEFAULT_AVATAR)
                        em.add_field(name='User', value=message.author.name)
                        em.add_field(name='Command', value=message.content, inline=False)

                        await logs_channel.send(embed=em)
        self.bot.message_listeners.append(on_message)

        async def on_message_reaction_add(event: MessageReactionAddEvent):
            if event.member.bot:
                return
            if event.emote.id == 90002171:
                code = login_cache.get(event.user_id)
                if code is not None:
                    message = await event.channel.fetch_message(event.message_id)
                    await message.delete()

                    result = requests.post(f'http://localhost:5000/auth/status/{code}/{event.user_id}', headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    if result.status_code == 200:
                        em = Embed(
                            title='Success',
                            description=f'{event.member.mention}, You should now be logged in on your browser. If you closed the login page before this then you will have to login again.',
                            colour=Colour.gilded()
                        )
                        await event.channel.send(embed=em, private=True, delete_after=10)
                    else:
                        em = Embed(
                            title='Failure',
                            description=f'{event.member.mention}, This login prompt has expired, please reinput your code or generate a new one.',
                            colour=Colour.gilded()
                        )
                        await event.channel.send(embed=em, private=True, delete_after=10)
        bot.reaction_add_listeners.append(on_message_reaction_add)

        async def on_server_channel_create(event: ServerChannelCreateEvent):
            channel = await event.server.getch_channel(event.channel.id)
            channel_payload = [{
                'id': channel.id,
                'name': channel.name,
                'type': channel.type.name,
                'jump': channel.jump_url,
            }]
            requests.put(f'http://localhost:5000/data/cache/{event.server_id}/channels', headers={
                'authorization': bot_config.SECRET_KEY
            }, json=channel_payload)
        bot.channel_create_listeners.append(on_server_channel_create)
        
        async def on_server_channel_delete(event: ServerChannelDeleteEvent):
            channel = event.channel
            channel_payload = [{
                'id': channel.id,
            }]
            requests.delete(f'http://localhost:5000/data/cache/{event.server_id}/channels', headers={
                'authorization': bot_config.SECRET_KEY
            }, json=channel_payload)
        bot.channel_delete_listeners.append(on_server_channel_delete)

        async def on_member_removed(event: MemberRemoveEvent):
            user = await bot.getch_user(event.user_id)
            if user.bot:
                return
            server = event.server
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            config: dict =  guild_data.get('config', {})
            leave_message: str = config.get('leave_message', 'Goodbye, {mention}, we hope to see you again!')
            leave_image = config.get('leave_image')
            welcome_channel_id = config.get('welcome_channel', server.default_channel_id)
            leave_enabled = config.get('use_leave', 0)

            user_data_req = requests.get(f'http://localhost:5000/userinfo/{server.id}/{user.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            user_info: dict = user_data_req.json()
            curLang = user_info.get('language', 'en')

            if leave_enabled == 1:
                replacements = {
                    '{mention}': user.mention,
                    '{server_name}': server.name
                }

                for key, value in replacements.items():
                    leave_message = leave_message.replace(key, value)

                em = Embed(
                    title=await translate(curLang, 'embed.goodbye'),
                    description=leave_message,
                    colour=Colour.gilded()
                )
                if leave_image is not None and leave_image != '':
                    em.set_image(url=leave_image)
                
                try:
                    welcome_channel = await self.bot.getch_channel(welcome_channel_id)
                    await welcome_channel.send(embed=em)
                except Exception as e:
                    print(f'Failed to send leave message in {server.name} ({server.id}) for user {user.name} ({user.id}): {str(e)}')
        bot.leave_listeners.append(on_member_removed)

        async def on_member_added(event: MemberJoinEvent):
            await self.scan_auto_roles(event.member, True)
        bot.join_listeners.append(on_member_added)

        async def on_role_create(event: RoleCreateEvent):
            role = event.role
            role_payload = [{
                'id': role.id,
                'name': role.name,
                'position': role.position,
                'base': role.base,
                'colour': str(role.colour),
                'colours': [str(colour) for colour in role.colours],
                'icon': role.icon != None and role.icon.aws_url or '',
                'permissions': role.permissions.values
            }]
            requests.put(f'http://localhost:5000/data/cache/{event.server_id}/roles', headers={
                'authorization': bot_config.SECRET_KEY
            }, json=role_payload)
        bot.role_create_listeners.append(on_role_create)

        async def on_role_update(event: RoleUpdateEvent):
            role = event.after
            role_payload = [{
                'id': role.id,
                'name': role.name,
                'position': role.position,
                'base': role.base,
                'colour': str(role.colour),
                'colours': [str(colour) for colour in role.colours],
                'icon': role.icon != None and role.icon.aws_url or '',
                'permissions': role.permissions.values
            }]
            requests.put(f'http://localhost:5000/data/cache/{event.server_id}/roles', headers={
                'authorization': bot_config.SECRET_KEY
            }, json=role_payload)
        bot.role_update_listeners.append(on_role_update)

        async def on_role_delete(event: RoleDeleteEvent):
            role_payload = [{
                'id': event.role.id,
            }]
            requests.delete(f'http://localhost:5000/data/cache/{event.server_id}/roles', headers={
                'authorization': bot_config.SECRET_KEY
            }, json=role_payload)
        bot.role_delete_listeners.append(on_role_delete)

        @bot.event
        async def on_bot_remove(event: BotRemoveEvent):
            requests.patch(f'http://localhost:5000/guilddata/{event.server_id}', json={
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
                description=f'Thanks <@{event.member_id}> for inviting me to **{server.name}!** To start configuring Server Guard, access your server\'s dashboard [here](https://serverguard.xyz/account)!',
                timestamp=datetime.now(),
                colour=Colour.gilded()
            ) \
            .set_footer(text='Server Guard') \
            .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
            .add_field(name='Links', value='[Support Server](https://www.guilded.gg/server-guard) • [Website](https://serverguard.xyz) • [Invite](https://www.guilded.gg/b/c10ac149-0462-4282-a632-d7a8808c6c6e)', inline=False)
            await default.send(embed=em)

            requests.patch(f'http://localhost:5000/guilddata/{event.server_id}', json={
                'active': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            requests.patch(f'http://localhost:5000/getguilduser/{event.server_id}/{event.server.owner_id}', json={
                'permission_level': 4
                }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            role_payload = []

            roles = await event.server.fetch_roles()
            for role in roles:
                role_payload.append({
                    'id': role.id,
                    'name': role.name,
                    'position': role.position,
                    'base': role.base,
                    'colour': str(role.colour),
                    'colours': [str(colour) for colour in role.colours],
                    'icon': role.icon != None and role.icon.aws_url or '',
                    'permissions': role.permissions.values
                })

            requests.put(f'http://localhost:5000/data/cache/{event.server_id}/roles', headers={
                'authorization': bot_config.SECRET_KEY
            }, json=role_payload)

            bot_api = bot.http
            channels_req = await bot_api.request(http.Route('GET', f'/teams/{event.server_id}/channels', override_base=http.Route.USER_BASE))
            if channels_req is not None:
                channels = channels_req['channels']
                channel_payload = []

                for channel in channels:
                    channel_payload.append({
                        'id': channel['id'],
                        'name': channel['name'],
                        'type': channel['contentType'],
                        'jump': f'https://www.guilded.gg/{event.server.slug}/groups/{channel["groupId"]}/channels/{channel["id"]}',
                    })
                requests.put(f'http://localhost:5000/data/cache/{event.server_id}/channels', headers={
                    'authorization': bot_config.SECRET_KEY
                }, json=channel_payload)
