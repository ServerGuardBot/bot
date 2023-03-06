from datetime import timedelta
from project.modules.base import Module
from project.helpers.embeds import *
from project import bot_config
from project.helpers.translator import translate
from project.modules.general import General
from humanfriendly import parse_timespan, format_timespan

from guilded import MessageReactionAddEvent, MessageReactionRemoveEvent
from guilded.utils import hyperlink
from guilded.ext import commands

import requests

class GiveawaysModule(Module):
    name = 'Giveaways'

    def initialize(self):
        bot = self.bot

        cog = General()

        @bot.group(invoke_without_command=True)
        async def giveaway(_, ctx: commands.Context):
            """[Moderator+] Manage giveaways"""
            pass

        giveaway.cog = cog

        @giveaway.command()
        async def host(ctx: commands.Context, timespan: str, winners: str, *_prize):
            """Host a giveaway in the current channel"""
            await self.validate_permission_level(1, ctx)

            prize = ' '.join(_prize)
            if timespan is not None:
                try:
                    timespan = parse_timespan(timespan)
                except:
                    timespan = None
            if timespan is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'command.error.timespan')), private=True)
                return
            try:
                int(winners)
            except:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.missingwinners')), private=True)
                return
            result = requests.post(f'http://localhost:5000/giveaways/{ctx.server.id}/{ctx.channel.id}/host', headers={
                'authorization': bot_config.SECRET_KEY
            }, json={
                'winners': int(winners),
                'ends_at': (datetime.now() + timedelta(seconds=timespan)).timestamp(),
                'prize': prize,
                'host': ctx.author.id
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
            await ctx.message.delete()
        
        @giveaway.command()
        async def list(ctx: commands.Context):
            """Lists all active giveaways"""
            await self.validate_permission_level(1, ctx)

            result = requests.get(f'http://localhost:5000/giveaways/{ctx.server.id}', headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.ok:
                em = Embed(
                    title=await translate(ctx.message.language, 'giveaway.list.title'),
                    description=len(result.json()) > 0 and '\n'.join(
                        [
                            f'[{giveaway["id"]}] {giveaway["prize"]} - {giveaway["entrants"]} entries, ends in {format_timespan(datetime.fromtimestamp(giveaway["ends_at"]) - datetime.now())}' for giveaway in result.json()
                        ]
                    ) or await translate(ctx.message.language, 'giveaway.list.none')
                )
                await ctx.reply(embed=em)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @giveaway.command()
        async def extend(ctx: commands.Context, giveaway_id: str, *_timespan: str):
            """Extend a giveaway by the specified amount of time"""
            await self.validate_permission_level(1, ctx)

            timespan = ' '.join(_timespan)
            if timespan is not None:
                try:
                    timespan = parse_timespan(timespan)
                except:
                    timespan = None
            if timespan is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'command.error.timespan')), private=True)
                return
            elif giveaway_id is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.noid')), private=True)
                return
            result = requests.patch(f'http://localhost:5000/giveaways/{ctx.server.id}/{giveaway_id}', headers={
                'authorization': bot_config.SECRET_KEY
            }, json={
                'extend': timespan
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @giveaway.command()
        async def set_prize(ctx: commands.Context, giveaway_id: str, *_prize: str):
            """Alter the prize of a giveaway"""
            await self.validate_permission_level(1, ctx)

            prize = ' '.join(_prize)
            if giveaway_id is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.noid')), private=True)
                return
            result = requests.patch(f'http://localhost:5000/giveaways/{ctx.server.id}/{giveaway_id}', headers={
                'authorization': bot_config.SECRET_KEY
            }, json={
                'prize': prize
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @giveaway.command()
        async def set_winners(ctx: commands.Context, giveaway_id: str, winners: str):
            """Change the amount of winners for a giveaway"""
            await self.validate_permission_level(1, ctx)

            if giveaway_id is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.noid')), private=True)
                return
            try:
                int(winners)
            except:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.missingwinners')), private=True)
                return
            result = requests.patch(f'http://localhost:5000/giveaways/{ctx.server.id}/{giveaway_id}', headers={
                'authorization': bot_config.SECRET_KEY
            }, json={
                'winners': max(int(winners), 1)
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @giveaway.command()
        async def delete(ctx: commands.Context, giveaway_id: str):
            """Delete a giveaway"""
            await self.validate_permission_level(1, ctx)

            if giveaway_id is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.noid')), private=True)
                return
            result = requests.delete(f'http://localhost:5000/giveaways/{ctx.server.id}/{giveaway_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @giveaway.command()
        async def end(ctx: commands.Context, giveaway_id: str):
            """End a giveaway"""
            await self.validate_permission_level(1, ctx)

            if giveaway_id is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.noid')), private=True)
                return
            result = requests.post(f'http://localhost:5000/giveaways/{ctx.server.id}/{giveaway_id}/end', headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        @giveaway.command()
        async def reroll(ctx: commands.Context, giveaway_id: str):
            """Reroll the winners of a giveaway"""
            await self.validate_permission_level(1, ctx)

            if giveaway_id is None:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(await translate(ctx.message.language, 'giveaway.noid')), private=True)
                return
            result = requests.post(f'http://localhost:5000/giveaways/{ctx.server.id}/{giveaway_id}/reroll', headers={
                'authorization': bot_config.SECRET_KEY
            })

            if result.ok:
                await ctx.reply(embed=EMBED_SUCCESS(), private=True)
            else:
                await ctx.reply(embed=EMBED_COMMAND_ERROR(), private=True)
        
        async def on_message_reaction_add(event: MessageReactionAddEvent):
            if event.member.bot:
                return
            message = await event.channel.fetch_message(event.message_id)
            if event.emote.id == 90001815 and message.author_id == bot.user_id:
                result = requests.put(f'http://localhost:5000/giveaways/{event.server_id}/entry/{event.message_id}/{event.user_id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
        bot.reaction_add_listeners.append(on_message_reaction_add)

        async def on_message_reaction_remove(event: MessageReactionRemoveEvent):
            if event.member.bot:
                return
            message = await event.channel.fetch_message(event.message_id)
            if event.emote.id == 90001815 and message.author_id == bot.user_id:
                result = requests.delete(f'http://localhost:5000/giveaways/{event.server_id}/entry/{event.message_id}/{event.user_id}', headers={
                    'authorization': bot_config.SECRET_KEY
                })
        bot.reaction_remove_listeners.append(on_message_reaction_remove)