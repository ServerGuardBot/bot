from datetime import datetime
from json import JSONEncoder
from guilded import Colour, ChatChannel, Embed, BanDeleteEvent, BanCreateEvent, MemberJoinEvent, MessageReactionAddEvent, BulkMemberRolesUpdateEvent, ChatMessage, Server, User, Emote
from guilded.ext import commands
from project.modules.base import Module
from project import bot_config

from project.helpers import social_links, user_evaluator, verif_token
from project.helpers.embeds import *

import requests

encoder = JSONEncoder()
member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

class Verification(commands.Cog):
    pass

class VerificationModule(Module):
    name = "Verification"

    async def send_welcome_embed(self, server: Server, user: User):
        guild_data = self.get_guild_data(server.id)
        config = guild_data.get('config', {})
        welcome_message: str = config.get('welcome_message', 'Hello {mention} and welcome to {server_name}!\n\nRemember to read the rules before interacting in this server!')
        welcome_image = config.get('welcome_image')
        welcome_channel_id = config.get('welcome_channel', server.default_channel_id)
        welcomer_enabled = config.get('use_welcome', 0)

        if welcomer_enabled == 1:
            replacements = {
                '{mention}': user.mention,
                '{server_name}': server.name
            }

            for key, value in replacements.items():
                welcome_message = welcome_message.replace(key, value)

            em = Embed(
                title='Welcome!',
                description=welcome_message,
                colour=Colour.gilded()
            )
            if welcome_image is not None and welcome_image != '':
                em.set_image(url=welcome_image)
            
            try:
                welcome_channel = await self.bot.getch_channel(welcome_channel_id)
                await welcome_channel.send(embed=em)
            except Exception as e:
                print(f'Failed to send welcomer message in {server.name} ({server.id}) for user {user.name} ({user.id}): {str(e)}')
    
    async def initiate_verification(self, server: Server, member: Member, channel: ChatChannel):
        token = verif_token.generate_token(server.id, member.id, await social_links.get_connections(server.id, member.id))
        link = requests.post('http://localhost:5000/verify/shorten', json={
            'token': token
        }, headers={
            'authorization': bot_config.SECRET_KEY
        }).json()['result']

        em = Embed(
            title='Verification',
            description=f'Here\'s your verification link, {member.mention}!',
            colour=Colour.gilded(),
            timestamp=datetime.now()
        ) \
        .set_footer(text='Server Guard') \
        .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
        .add_field(name='Click Below', value=f'[{link}](https://serverguard.reapimus.com/verify/{link})', inline=False)

        await channel.send(embed=em, private=True)

    def initialize(self):
        bot = self.bot

        cog = Verification()

        @bot.command()
        async def evaluate(_, ctx: commands.Context, target: str=None):
            """[Moderator+] Evaluate a user"""
            await self.validate_permission_level(1, ctx)
            user = target == None and ctx.author or await self.convert_member(ctx, target)
            if user.bot:
                pass # We know bots aren't real users lol
            links = await social_links.get_connections(ctx.guild.id, user.id)
            eval_result = await user_evaluator.evaluate_user(ctx.guild.id, user.id, encoder.encode(links))

            await ctx.reply(embed=user_evaluator.generate_embed(eval_result))
        
        evaluate.cog = cog
        
        @bot.command()
        async def verify(_, ctx: commands.Context):
            """Verify with the bot"""
            if ctx.author.bot:
                return
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            unverified_role = guild_data.get('config').get('unverified_role')
            verified_role = guild_data.get('config').get('verified_role')

            guilded_member = await ctx.server.getch_member(ctx.author.id)
            member_roles = await guilded_member.fetch_role_ids()
            if unverified_role:
                if int(unverified_role) not in member_roles:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('You\'re already verified!'), private=True)
                    return
            elif verified_role:
                if int(verified_role) in member_roles:
                    await ctx.reply(embed=EMBED_COMMAND_ERROR('You\'re already verified!'), private=True)
                    return

            await self.initiate_verification(ctx.server, guilded_member, ctx.channel)
        
        verify.cog = cog
        
        @bot.command()
        async def bypass(_, ctx: commands.Context, target: str):
            """[Moderator+] Grant a user a verification bypass"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)
            if user.bot:
                pass # We know bots aren't real users lol
            result = requests.patch(f'http://localhost:5000/verify/bypass/{ctx.server.id}/{user.id}', json={
                'value': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200:
                await ctx.reply(EMBED_SUCCESS('Successfully allowed verification bypass.'))
            else:
                await ctx.reply(EMBED_COMMAND_ERROR())
        
        bypass.cog = cog
        
        @bot.command()
        async def unbypass(_, ctx: commands.Context, target: str):
            """[Moderator+] Revoke a user's verification bypass"""
            await self.validate_permission_level(1, ctx)
            user = await self.convert_member(ctx, target)
            if user.bot:
                pass # We know bots aren't real users lol
            result = requests.patch(f'http://localhost:5000/verify/bypass/{ctx.server.id}/{user.id}', json={
                'value': False
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.status_code == 200:
                await ctx.reply(EMBED_SUCCESS('Successfully disallowed verification bypass.'))
            else:
                await ctx.reply(EMBED_COMMAND_ERROR())
        
        unbypass.cog = cog

        async def on_member_join(event: MemberJoinEvent):
            if event.member.bot:
                return
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{event.server_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            guild_data: dict = guild_data_req.json()
            unverified_role = guild_data.get('config').get('unverified_role')
            verification_channel = guild_data.get('config').get('verification_channel')
            
            if verification_channel and verification_channel.isspace() is False and verification_channel != '':
                # Only trigger these if verification is enabled, indicated by whether or not verification_channel is specified
                if unverified_role:
                    requests.put(f'https://www.guilded.gg/api/v1/servers/{event.server_id}/members/{event.member.id}/roles/{unverified_role}',
                    headers={
                        'Authorization': f'Bearer {bot_config.GUILDED_BOT_TOKEN}'
                    })
                if verification_channel:
                    channel: ChatChannel = await event.server.getch_channel(verification_channel)
                    em = Embed(
                        title='Verification',
                        description=f'Welcome {event.member.mention}! Please react to this message with a :white_check_mark: to start verification!\n\n**If you are unable to send messages here or after verifying, please try reloading your Guilded client!**',
                        colour=Colour.gilded(),
                        timestamp=datetime.now()
                    ) \
                    .set_footer(text='Server Guard') \
                    .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
                    .add_field(name='Links', value='[Support Server](https://www.guilded.gg/server-guard) • [Invite](https://www.guilded.gg/b/c10ac149-0462-4282-a632-d7a8808c6c6e)', inline=False)
                    msg = await channel.send(embed=em)
                    await msg.add_reaction(Emote(state=bot.http, data={
                        'id': 90002171,
                        'name': 'white_check_mark'
                    })) # 90002171 = white_check_mark
            else:
                # The verification system is not in place, send the welcome message if it is enabled
                await self.send_welcome_embed(event.server, event.member)
        bot.join_listeners.append(on_member_join)

        @bot.event
        async def on_message_reaction_add(event: MessageReactionAddEvent):
            if event.member.bot:
                return
            if event.emote.id == 90002171:
                message = await event.channel.fetch_message(event.message_id)
                if message.author_id == bot.user_id and len(message.embeds) > 0 and message.embeds[0].title == 'Verification':
                    member = await event.server.getch_member(event.member.id)
                    guild_data = self.get_guild_data(event.server_id)
                    unverified_role = guild_data.get('config').get('unverified_role')
                    verified_role = guild_data.get('config').get('verified_role')
                    member_roles = await member.fetch_role_ids()
                    if unverified_role:
                        if int(unverified_role) not in member_roles:
                            return
                    elif verified_role:
                        if int(verified_role) in member_roles:
                            return
                    await self.initiate_verification(event.server, member, event.channel)

        async def on_ban_create(event: BanCreateEvent):
            if event.ban.user.bot:
                return
            guild_data_req = requests.patch(f'http://localhost:5000/verify/setbanned/{event.server_id}/{event.ban.user.id}', json={
                'value': True
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
        bot.ban_create_listeners.append(on_ban_create)
        
        async def on_ban_delete(event: BanDeleteEvent):
            if event.ban.user.bot:
                return
            guild_data_req = requests.patch(f'http://localhost:5000/verify/setbanned/{event.server_id}/{event.ban.user.id}', json={
                'value': False
            }, headers={
                'authorization': bot_config.SECRET_KEY
            })
        bot.ban_delete_listeners.append(on_ban_delete)
        
        async def on_message(message: ChatMessage):
            if message.author.bot:
                return
            guild_data = self.get_guild_data(message.server_id)
            verification_channel = guild_data.get('config').get('verification_channel')
            if verification_channel and message.channel_id == verification_channel:
                member = await message.guild.getch_member(message.author.id)
                if (await self.is_moderator(member)) or await self.user_can_manage_server(member):
                    return
                if not message.content.startswith('/verify'):
                    if message.content.lower().startswith('/verify'):
                        await message.reply(private=True, embed=EMBED_DENIED(
                                description=f'{member.mention}, Unfortunately due to technical reasons, commands are caps sensitive, please use `/verify` with no capitals.',
                                title='Message Filtered'
                            )
                        )
                    else:
                        await message.reply(private=True, embed=EMBED_DENIED(
                                description=f'{member.mention}, Only usage of the `/verify` command is permitted here.',
                                title='Message Filtered'
                            )
                        )
                    await message.delete()
        self.bot.message_listeners.append(on_message)

        async def on_bulk_member_roles_update(event: BulkMemberRolesUpdateEvent):
            guild_data = self.get_guild_data(event.server_id)
            config = guild_data.get('config', {})
            unverified_role = config.get('unverified_role')
            verified_role = config.get('verified_role')
            if config.get('verification_channel', '') is not '':
                who_verified = []
                for member in event.after:
                    roles = member._role_ids
                    before_member = None
                    for other_member in event.before:
                        if other_member.id == member.id:
                            before_member = other_member
                    if before_member is not None:
                        before_roles = before_member._role_ids
                        if verified_role is not None:
                            if int(verified_role) not in before_roles and int(verified_role) in roles:
                                who_verified.append(member)
                        elif unverified_role is not None:
                            if int(unverified_role) in before_roles and int(unverified_role) not in roles:
                                who_verified.append(member)

                for member in who_verified:
                    await self.send_welcome_embed(event.server, member)

        bot.member_role_update_listeners.append(on_bulk_member_roles_update)
