from datetime import datetime
from json import JSONEncoder
from guilded import Colour, ChatChannel, Embed, BanDeleteEvent, BanCreateEvent, MemberJoinEvent
from guilded.ext import commands
from project.modules.base import Module
from project import bot_config

from project.helpers import social_links, user_evaluator, verif_token

import requests

encoder = JSONEncoder()
member = commands.MemberConverter()
channel = commands.ChatChannelConverter()
role = commands.RoleConverter()

class Verification(commands.Cog):
    pass

class VerificationModule(Module):
    name = "Verification"

    def initialize(self):
        bot = self.bot

        cog = Verification()

        @bot.command()
        async def evaluate(self, ctx: commands.Context, target: str=None):
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
        async def verify(self, ctx: commands.Context):
            """Verify with the bot"""
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

            em = Embed(
                title='Verification',
                description=f'Here\'s your verification link!',
                colour=Colour.gilded(),
                timestamp=datetime.now()
            ) \
            .set_footer(text='Server Guard') \
            .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp') \
            .add_field(name='Link', value=f'[{link}](https://serverguard.reapimus.com/verify/{link})', inline=False)

            await ctx.reply(embed=em, private=True)
        
        verify.cog = cog
        
        @bot.command()
        async def bypass(self, ctx: commands.Context, target: str):
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
                await ctx.reply('Successfully allowed verification bypass.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
        bypass.cog = cog
        
        @bot.command()
        async def unbypass(self, ctx: commands.Context, target: str):
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
                await ctx.reply('Successfully disallowed verification bypass.')
            else:
                await ctx.reply('An unknown error occurred while performing this action.')
        
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
                        description=f'Welcome {event.member.mention}! Please verify using the `/verify` command.\n\n**If you are unable to send messages here or after verifying, please try reloading your Guilded client!**',
                        colour=Colour.gilded(),
                        timestamp=datetime.now()
                    ) \
                    .set_footer(text='Server Guard') \
                    .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Medium.webp')
                    await channel.send(embed=em)
        
        bot.join_listeners.append(on_member_join)

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
