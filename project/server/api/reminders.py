from datetime import datetime
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import BotAPI, app, db
from project.server.models import Guild, GuildUserStatus

import re

reminders_blueprint = Blueprint('reminders', __name__)

REMINDER_ID_REGEX = '^%s/%s/reminder/' + r'([a-zA-Z]+)'

def get_reminder_id(guild_id, user_id, internal_id):
    match: re.Match = re.search(REMINDER_ID_REGEX % (guild_id, user_id), internal_id)
    reminder_id = match.group(1)

    return reminder_id

class UserReminders(MethodView):
    def get(self, guild_id, user_id, reminder_id=None):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if reminder_id is not None:
            reminder: GuildUserStatus = GuildUserStatus.query.filter_by(internal_id = f'{guild_id}/{user_id}/reminder/{reminder_id}').first()

            if reminder is not None:
                return jsonify({
                    'result': reminder.value
                }), 200
            else:
                return 'Not found', 404
        else:
            reminders: list[GuildUserStatus] = GuildUserStatus.query.filter_by(guild_id = guild_id, user_id = user_id, type = 'reminder').all()

            return jsonify({
                'result': [{
                    'description': reminder.value['description'],
                    'channel': reminder.value['channel'],
                    'id': get_reminder_id(guild_id, user_id, reminder.internal_id),
                    'ends': reminder.ends_at is not None and reminder.ends_at.timestamp() or None
                } for reminder in reminders]
            }), 200
    def delete(self, guild_id, user_id, reminder_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        reminder: GuildUserStatus = GuildUserStatus.query.filter_by(internal_id = f'{guild_id}/{user_id}/reminder/{reminder_id}').first()

        if reminder is not None:
            db.session.delete(reminder)
            db.session.commit()

            return 'Removed.', 204
        else:
            return 'Not found', 404
    def post(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        data = request.get_json()

        if 'description' not in data or 'channel' not in data or 'ends' not in data:
            return 'Bad request.', 400

        description = data['description']
        channel = data['channel']

        ends = datetime.fromtimestamp(data['ends'])

        reminder = GuildUserStatus(guild_id = guild_id, user_id = user_id, type = 'reminder', value = {
            'description': description,
            'channel': channel
        }, ends_at = ends)

        db.session.add(reminder)
        db.session.commit()

        return jsonify({
            'reminder_id': get_reminder_id(guild_id, user_id, reminder.internal_id)
        }), 201

reminders_blueprint.add_url_rule('/reminders/<guild_id>/<user_id>', view_func = UserReminders.as_view('user_reminders'))
reminders_blueprint.add_url_rule('/reminders/<guild_id>/<user_id>/<reminder_id>', view_func = UserReminders.as_view('user_reminder'))