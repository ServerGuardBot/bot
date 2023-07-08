from datetime import datetime
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import BotAPI, app, db
from project.server.models import Guild, GuildUserStatus
from guilded import Embed, Colour

import re
import requests

WARNING_ID_REGEX = '^%s/%s/warning/' + r'([a-zA-Z]+)'
REMINDER_ID_REGEX = '^%s/%s/reminder/' + r'([a-zA-Z]+)'

moderation_blueprint = Blueprint('moderation', __name__)

def get_warning_id(guild_id, user_id, internal_id):
    match: re.Match = re.search(WARNING_ID_REGEX % (guild_id, user_id), internal_id)
    warn_id = match.group(1)

    return warn_id

def get_reminder_id(guild_id, user_id, internal_id):
    match: re.Match = re.search(REMINDER_ID_REGEX % (guild_id, user_id), internal_id)
    reminder_id = match.group(1)

    return reminder_id

class UserWarnings(MethodView):
    """ User Warning Resource """
    def get(self, guild_id, user_id, warn_id=None):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if warn_id is not None:
            warning: GuildUserStatus = GuildUserStatus.query.filter_by(internal_id = f'{guild_id}/{user_id}/warning/{warn_id}').first()

            if warning is not None:
                return jsonify({
                    'result': warning.value
                }), 200
            else:
                return 'Not found', 404
        else:
            warnings: list[GuildUserStatus] = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'warning').all()

            return jsonify({
                'result': [{
                    'reason': warn.value['reason'],
                    'issuer': warn.value['issuer'],
                    'id': get_warning_id(guild_id, user_id, warn.internal_id),
                    'when': warn.created_at is not None and warn.created_at.timestamp() or None
                } for warn in warnings]
            }), 200
    def patch(self, guild_id, user_id, warn_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        warning: GuildUserStatus = GuildUserStatus.query.filter_by(internal_id = f'{guild_id}/{user_id}/warning/{warn_id}').first()

        if warning is not None:
            post_data = request.get_json()
            reason = post_data.get('reason')

            if reason is None:
                return 'Bad request', 400
            else:
                warning['reason'] = reason

                db.session.add(warning)
                db.session.commit()

                return 'Success', 200
        else:
            return 'Not found', 404
    def delete(self, guild_id, user_id, warn_id=None):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if warn_id is not None:
            warning: GuildUserStatus = GuildUserStatus.query.filter_by(internal_id = f'{guild_id}/{user_id}/warning/{warn_id}').first()

            if warning is not None:
                db.session.delete(warning)
                db.session.commit()

                return 'Success', 204
            else:
                return 'Not found', 404
        else:
            warnings: list[GuildUserStatus] = GuildUserStatus.query.filter_by(user_id = user_id, guild_id = guild_id).all()

            for warning in warnings:
                db.session.delete(warning)
            
            db.session.commit()

            return 'Success', 204
    def post(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data = request.get_json()
        reason = post_data.get('reason')
        issuer = post_data.get('issuer')
        ends_at = post_data.get('ends_at')
        
        if reason is not None and issuer is not None:
            warning: GuildUserStatus = GuildUserStatus(guild_id, user_id, 'warning', {
                'reason': reason,
                'issuer': issuer
            }, ends_at is not None and datetime.fromtimestamp(ends_at) or None)

            warn_id = get_warning_id(guild_id, user_id, warning.internal_id)

            db.session.add(warning)
            db.session.commit()

            return jsonify({
                'warn_id': warn_id
            }), 201
        else:
            return 'Bad request', 400

class UserTempBans(MethodView):
    def post(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data = request.get_json()
        reason = post_data.get('reason')
        issuer = post_data.get('issuer')
        ends_at = post_data.get('ends_at')

        if reason is not None and issuer is not None and ends_at is not None:
            ban: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'ban').first()

            if ban is not None:
                return 'User is already banned', 400
            else:
                ban = GuildUserStatus(guild_id, user_id, 'ban', {
                    'reason': reason,
                    'issuer': issuer,
                }, ends_at is not None and datetime.fromtimestamp(ends_at) or None)

                db.session.add(ban)
                db.session.commit()

                return 'Success', 201
        else:
            return 'Bad request', 400
    def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data = request.get_json()
        reason = post_data.get('reason')
        ends_at = post_data.get('ends_at')

        ban: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'ban').first()
        if ban is None:
            return 'Not found', 404

        if reason is not None:
            ban.value['reason'] = reason

            db.session.add(ban)
            db.session.commit(ban)
        elif ends_at is not None:
            ban.ends_at = reason

            db.session.add(ban)
            db.session.commit(ban)
        else:
            return 'Bad request', 400
        
        return 'Success', 200
    def delete(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        ban: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'ban').first()

        if ban is not None:
            db.session.delete(ban)
            db.session.commit()

            return 'Success', 204
        else:
            return 'Not found', 404
    def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        ban: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'ban').first()

        if ban is not None:
            return jsonify({
                'issuer': ban.value['issuer'],
                'reason': ban.value['reason'],
                'ends_at': ban.ends_at.timestamp()
            }), 200
        else:
            return 'Not found', 404

class UserMutes(MethodView):
    def post(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data = request.get_json()
        reason = post_data.get('reason')
        issuer = post_data.get('issuer')
        ends_at = post_data.get('ends_at')

        if reason is not None and issuer is not None:
            mute: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'mute').first()

            if mute is not None:
                return 'User is already muted', 400
            else:
                mute = GuildUserStatus(guild_id, user_id, 'mute', {
                    'reason': reason,
                    'issuer': issuer,
                }, ends_at is not None and datetime.fromtimestamp(ends_at) or None)

                db.session.add(mute)
                db.session.commit()

                return 'Success', 201
        else:
            return 'Bad request', 400
    def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data = request.get_json()
        reason = post_data.get('reason')
        ends_at = post_data.get('ends_at')

        mute: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'mute').first()
        if mute is None:
            return 'Not found', 404

        if reason is not None:
            mute.value['reason'] = reason

            db.session.add(mute)
            db.session.commit(mute)
        elif ends_at is not None:
            mute.ends_at = reason

            db.session.add(mute)
            db.session.commit(mute)
        else:
            return 'Bad request', 400
        
        return 'Success', 200
    def delete(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        mute: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'mute').first()

        if mute is not None:
            db.session.delete(mute)
            db.session.commit()

            return 'Success', 204
        else:
            return 'Not found', 404
    def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        mute: GuildUserStatus = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'mute').first()

        if mute is not None:
            return jsonify({
                'issuer': mute.value['issuer'],
                'reason': mute.value['reason'],
                'ends_at': mute.ends_at is not None and mute.ends_at.timestamp() or None
            }), 200
        else:
            return 'Not found', 404

class ExpiredStatuses(MethodView):
    """ Resource for getting expired user statuses and handling them """
    async def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403

        with BotAPI() as bot_api:
            statuses = GuildUserStatus.query.filter(datetime.now() >= GuildUserStatus.ends_at).paginate(per_page=50)
            for _ in statuses.iter_pages():
                contents = statuses.items
                for status in contents:
                    status: GuildUserStatus = status
                    guild: Guild = Guild.query.filter_by(guild_id = status.guild_id).first()
                    logs_channel = guild.config.get('action_logs_channel', guild.config.get('logs_channel'))
                    user = (await bot_api.get_user(status.user_id))['user']
                    if status.type == 'ban':
                        try:
                            await bot_api.unban_server_member(status.guild_id, status.user_id)
                        except Exception as e:
                            print(f'Failed to unban user "{status.user_id}" from guild "{status.guild_id}"')
                        if guild.config.get('logs_channel'):
                            em = Embed(
                                title = 'Ban ended',
                                colour = Colour.blue(),
                                timestamp = datetime.now()
                            )
                            em.add_field(name='User', value=f'<@{status.user_id}>')
                            em.add_field(name='Ban Reason', value=status.value['reason'])
                            await bot_api.create_channel_message(logs_channel, payload={
                                'embeds': [em.to_dict()]
                            })
                        requests.delete(f'http://localhost:5000/moderation/{status.guild_id}/{status.user_id}/ban', headers={
                            'authorization': app.config.get('SECRET_KEY')
                        })
                    elif status.type == 'mute':
                        if guild.config.get('mute_role'):
                            try:
                                await bot_api.remove_role_from_member(status.guild_id, status.user_id, guild.config['mute_role'])
                            except Exception as e:
                                print(f'Failed to unmute user "{status.user_id}" from guild "{status.guild_id}"')
                        if guild.config.get('logs_channel'):
                            em = Embed(
                                title = 'Mute ended',
                                colour = Colour.blue(),
                                timestamp = datetime.now()
                            )
                            em.add_field(name='User', value=f'<@{status.user_id}>')
                            em.add_field(name='Mute Reason', value=status.value['reason'])
                            await bot_api.create_channel_message(logs_channel, payload={
                                'embeds': [em.to_dict()]
                            })
                        requests.delete(f'http://localhost:5000/moderation/{status.guild_id}/{status.user_id}/mute', headers={
                            'authorization': app.config.get('SECRET_KEY')
                        })
                    elif status.type == 'warning':
                        if guild.config.get('logs_channel'):
                            em = Embed(
                                title = 'Warning ended',
                                colour = Colour.blue(),
                                timestamp = datetime.now()
                            )
                            em.add_field(name='User', value=f'<@{status.user_id}>')
                            em.add_field(name='Warning Reason', value=status.value['reason'])
                            await bot_api.create_channel_message(logs_channel, payload={
                                'embeds': [em.to_dict()]
                            })
                        requests.delete(f'http://localhost:5000/moderation/{status.guild_id}/{status.user_id}/warnings/{get_warning_id(status.guild_id, status.user_id, status.internal_id)}', headers={
                            'authorization': app.config.get('SECRET_KEY')
                        })
                    elif status.type == 'reminder':
                        em = Embed(
                            title = 'Reminder ended',
                            colour = Colour.blue(),
                            timestamp = datetime.now(),
                            description = f'<@{status.user_id}>'
                        )
                        em.add_field(name='Reminder', value=status.value['description'], inline=False)
                        await bot_api.create_channel_message(status.value['channel'], payload={
                            'embeds': [em.to_dict()],
                            'isPrivate': True
                        })
                        requests.delete(f'http://localhost:5000/reminders/{status.guild_id}/{status.user_id}/{get_reminder_id(status.guild_id, status.user_id, status.internal_id)}', headers={
                            'authorization': app.config.get('SECRET_KEY')
                        })
                        
                statuses.next()

            return 'Success', 200

moderation_blueprint.add_url_rule('/moderation/<guild_id>/<user_id>/warnings', view_func=UserWarnings.as_view('warnings'))
moderation_blueprint.add_url_rule('/moderation/<guild_id>/<user_id>/warnings/<warn_id>', view_func=UserWarnings.as_view('warnings_id'))
moderation_blueprint.add_url_rule('/moderation/<guild_id>/<user_id>/ban', view_func=UserTempBans.as_view('ban'))
moderation_blueprint.add_url_rule('/moderation/<guild_id>/<user_id>/mute', view_func=UserMutes.as_view('mute'))
moderation_blueprint.add_url_rule('/moderation/expirestatuses', view_func=ExpiredStatuses.as_view('expiredstatuses'))