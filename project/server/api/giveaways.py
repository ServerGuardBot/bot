from datetime import datetime, timedelta
from http import server
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import BotAPI, app, db
from guilded import Embed, Colour
from project.server.api.auth import get_user_auth

from project.server.models import Giveaway, Guild, GuildUser

import random

giveaways_blueprint = Blueprint('giveaways', __name__)

async def rollWinners(giveaway: Giveaway, save: bool):
    winners = []
    entries = [id for id in giveaway.entries]
    for i in range(giveaway.winner_amount):
        if len(entries) > 0:
            winner = entries[len(entries) > 1 and random.randrange(1, len(entries)) - 1 or 0]
            winners.append(winner)
            entries.remove(winner)
    giveaway.winners = winners

    with BotAPI() as bot_api:
        await bot_api.update_channel_message(
            channel_id=giveaway.channel_id,
            message_id=giveaway.original_message_id,
            payload={
                'embeds': [
                    generateEmbed(
                        giveaway.guild_id,
                        giveaway.ended,
                        giveaway.ends_at,
                        giveaway.winners,
                        giveaway.prize,
                        giveaway.winner_amount,
                        giveaway.hosted_by
                    )
                ]
            }
        )
    if save:
        db.session.add(giveaway)
        db.session.commit()
    return winners

async def endGiveaway(giveaway: Giveaway, save: bool):
    giveaway.ended = True
    await rollWinners(giveaway, save)

    with BotAPI() as bot_api:
        em = Embed(
            title='Giveaway Ended',
            description=f':tada: Giveaway "{giveaway.prize}" has ended and winners have been chosen!',
            colour=Colour.gilded(),
        ).to_dict()

        await bot_api.create_channel_message(
                channel_id=giveaway.channel_id, 
                payload={
                    'embeds': [
                        em
                    ],
                    'replyMessageIds': [giveaway.original_message_id]
                }
            )

def generateEmbed(server_id: str, ended: bool, ends_at: datetime, winners: list, prize: str, winners_count: int, hosted_by: str):
    guild: Guild = Guild.query \
        .filter(Guild.guild_id == server_id) \
        .first()
    
    content = ''
    
    if guild:
        ping_role = guild.config.get('giveaway_ping')
        if ping_role and ping_role != '':
            content = f'<@{ping_role}>\n'

    return Embed(
        title=prize,
        description=f'{content}React with :tada: to participate!',
        colour=Colour.gilded(),
        timestamp=ends_at,
    ) \
        .add_field(
            name='Winners',
            value=ended and '\n'.join([f'<@{id}>' for id in winners])  or (winners_count > 1 and f'{winners_count} winners' or '1 winner')
        ) \
        .add_field(
            name='Hosted by',
            value=f'<@{hosted_by}>'
        ) \
        .set_footer(
            text=ended and 'Ended' or 'Ends at'
        ) \
        .to_dict()

class GiveawayCheckResource(MethodView):
    """ Resource for automatically ending giveaways once their end time has been reached """
    async def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403

        giveaways: list = Giveaway.query \
            .filter(Giveaway.ended == False) \
            .filter(datetime.now() > Giveaway.ends_at) \
            .all()
        
        for giveaway in giveaways:
            await endGiveaway(giveaway, False)
            db.session.add(giveaway)
        if len(giveaways) > 0:
            db.session.commit()
        return 'Success', 200

class GiveawayResource(MethodView):
    """ Resource for creating, removing, or getting giveaway(s) """
    async def get(self, server_id: str, giveaway_id: str=None):
        auth = request.headers.get('authorization')
        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or guild_user.permission_level < 3:
                return 'Forbidden', 403
        
        if giveaway_id == None:
            giveaways = Giveaway.query \
                .filter(Giveaway.guild_id == server_id) \
                .filter(Giveaway.ended == False) \
                .all()
            return jsonify([
                {
                    'id': giveaway.id,
                    'ends_at': giveaway.ends_at.timestamp(),
                    'prize': giveaway.prize,
                    'winners': giveaway.winner_amount,
                    'channel_id': giveaway.channel_id,
                    'message_id': giveaway.original_message_id,
                    'entrants': len(giveaway.entries)
                } for giveaway in giveaways
            ]), 200
        else:
            giveaway = Giveaway.query \
                .filter(Giveaway.guild_id == server) \
                .filter(Giveaway.id == giveaway_id) \
                .first()
            
            if giveaway:
                return jsonify({
                    'id': giveaway.id,
                    'ends_at': giveaway.ends_at.timestamp(),
                    'prize': giveaway.prize,
                    'winners': giveaway.winner_amount,
                    'channel_id': giveaway.channel_id,
                    'message_id': giveaway.original_message_id
                }), 200
            else:
                return 'Not Found', 404
    async def post(self, server_id: str, channel_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or guild_user.permission_level < 3:
                return 'Forbidden', 403
        
        post_data: dict = request.get_json()

        winners = post_data.get('winners', 1)
        ends_at = datetime.fromtimestamp(post_data.get('ends_at', (datetime.now() + timedelta(days=1)).timestamp()))
        prize = post_data.get('prize', '')
        hosted_by = post_data.get('host', '')

        guild: Guild = Guild.query \
            .filter(Guild.guild_id == server_id) \
            .first()
        
        if guild:
            target_channel = guild.config.get('giveaway_channel')
            if target_channel and target_channel != '': channel_id = target_channel
        
        with BotAPI() as bot_api:
            response = await bot_api.create_channel_message(
                channel_id=channel_id, 
                payload={
                    'embeds': [
                        generateEmbed(
                            server_id,
                            False,
                            ends_at,
                            [],
                            prize,
                            winners,
                            hosted_by
                        )
                    ]
                }
            )
            message_id = response['message']['id']
            await bot_api.add_reaction_emote(
                channel_id=channel_id,
                content_id=message_id,
                emote_id=90001815
            ) # 90001815 = tada
        
        giveaway: Giveaway = Giveaway(
            server_id,
            channel_id,
            message_id,
            winners,
            ends_at,
            prize,
            hosted_by
        )
        db.session.add(giveaway)
        db.session.commit()
        return 'Success', 200
    async def patch(self, server_id: str, giveaway_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or guild_user.permission_level < 3:
                return 'Forbidden', 403
        
        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.id == giveaway_id) \
            .first()
        
        if giveaway:
            post_data: dict = request.get_json()

            with BotAPI() as bot_api:
                dirty = False
                if post_data.get('extend'):
                    if giveaway.ended:
                        return 'Bad Request', 400
                    giveaway.ends_at += timedelta(seconds=post_data['extend'])
                    dirty = True
                if post_data.get('prize'):
                    giveaway.prize = post_data['prize']
                    dirty = True
                if post_data.get('winners'):
                    giveaway.winner_amount = post_data['winners']
                    dirty = True
                if dirty:
                    await bot_api.update_channel_message(
                        channel_id=giveaway.channel_id,
                        message_id=giveaway.original_message_id, 
                        payload={
                            'embeds': [
                                generateEmbed(
                                    giveaway.guild_id,
                                    giveaway.ended,
                                    giveaway.ends_at,
                                    giveaway.winners,
                                    giveaway.prize,
                                    giveaway.winner_amount,
                                    giveaway.hosted_by
                                )
                            ]
                        }
                    )
                    db.session.add(giveaway)
                    db.session.commit()
                return 'Success', 200
        else:
            return 'Not Found', 404
    async def delete(self, server_id: str, giveaway_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or guild_user.permission_level < 3:
                return 'Forbidden', 403
        
        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.id == giveaway_id) \
            .first()
        
        if giveaway:
            with BotAPI() as bot_api:
                await bot_api.delete_channel_message(
                    channel_id=giveaway.channel_id,
                    message_id=giveaway.original_message_id
                )

            db.session.delete(giveaway)
            db.session.commit()
            return 'Success', 204
        else:
            return 'Not Found', 404

class GiveawayRerollResource(MethodView):
    """ Resource for re-rolling an ended giveaway """
    async def post(self, server_id: str, giveaway_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or guild_user.permission_level < 3:
                return 'Forbidden', 403

        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.id == giveaway_id) \
            .first()
        
        if giveaway:
            if not giveaway.ended:
                return 'Bad Request', 400
            await rollWinners(giveaway, True)
            with BotAPI() as bot_api:
                em = Embed(
                    title='Rerolling winners',
                    description=f':tada: Winners for "{giveaway.prize}" are being rerolled!',
                    colour=Colour.gilded(),
                ).to_dict()

                await bot_api.create_channel_message(
                        channel_id=giveaway.channel_id, 
                        payload={
                            'embeds': [
                                em
                            ],
                            'replyMessageIds': [giveaway.original_message_id]
                        }
                    )
            return 'Success', 200
        else:
            return 'Not Found', 404

class GiveawayEndResource(MethodView):
    """ Resource for ending a giveaway """
    async def post(self, server_id: str, giveaway_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or guild_user.permission_level < 3:
                return 'Forbidden', 403

        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.id == giveaway_id) \
            .first()
        
        if giveaway:
            await endGiveaway(giveaway, True)
            return 'Success', 200
        else:
            return 'Not Found', 404

class GiveawayEnterResource(MethodView):
    """ Resource for adding or removing a user from a giveaway """
    async def get(self, server_id: str, message_id: str, user_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or user_id != auth:
                return 'Forbidden', 403

        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.original_message_id == message_id) \
            .first()
        
        if giveaway:
            try:
                giveaway.entries.index(user_id)
                return jsonify({
                    'result': True
                }), 200
            except:
                giveaway.entries.index(user_id)
                return jsonify({
                    'result': False
                }), 200
        else:
            return 'Not Found', 404
    async def put(self, server_id: str, message_id: str, user_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or user_id != auth:
                return 'Forbidden', 403

        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.original_message_id == message_id) \
            .first()
        
        if giveaway:
            giveaway.entries.append(user_id)
            db.session.add(giveaway)
            db.session.commit()
            return 'Success', 200
        else:
            return 'Not Found', 404
    async def delete(self, server_id: str, message_id: str, user_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == server_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is None or user_id != auth:
                return 'Forbidden', 403

        giveaway: Giveaway = Giveaway.query \
            .filter(Giveaway.guild_id == server_id) \
            .filter(Giveaway.original_message_id == message_id) \
            .first()
        
        if giveaway:
            try:
                giveaway.entries.remove(user_id)
                db.session.add(giveaway)
                db.session.commit()
                return 'Success', 200
            except:
                return 'Not in Giveaway', 400
        else:
            return 'Not Found', 404

giveaways_blueprint.add_url_rule('/giveaways/check', view_func=GiveawayCheckResource.as_view('giveaway_check'))
giveaways_blueprint.add_url_rule('/giveaways/<server_id>', view_func=GiveawayResource.as_view('giveaway_info'))
giveaways_blueprint.add_url_rule('/giveaways/<server_id>/<giveaway_id>', view_func=GiveawayResource.as_view('giveaway_info_get'))
giveaways_blueprint.add_url_rule('/giveaways/<server_id>/<channel_id>/host', view_func=GiveawayResource.as_view('giveaway_host'))
giveaways_blueprint.add_url_rule('/giveaways/<server_id>/entry/<message_id>/<user_id>', view_func=GiveawayEnterResource.as_view('giveaway_entry'))
giveaways_blueprint.add_url_rule('/giveaways/<server_id>/<giveaway_id>/end', view_func=GiveawayEndResource.as_view('giveaway_end'))
giveaways_blueprint.add_url_rule('/giveaways/<server_id>/<giveaway_id>/reroll', view_func=GiveawayRerollResource.as_view('giveaway_reroll'))