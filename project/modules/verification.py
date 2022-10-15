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
            user = target == None and ctx.author or await self.convert_member(ctx, target)
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
        
        @bot.command()
        async def bypass(ctx: commands.Context, target: str):
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
        
        @bot.command()
        async def unbypass(ctx: commands.Context, target: str):
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

        @bot.event
        async def on_server_join(server: Server):
            requests.get(f'http://localhost:5000/guilddata/{server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            }) # Initialize server data

            owner = await bot.fetch_user(server.owner_id)
            await owner.send('Hey! Thanks for using Server Guard. To properly setup your server make sure to setup config using `/config`!')

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
