from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, db
from sqlalchemy import func

from project.server.api.auth import get_user_auth
from project.server.models import BotData, AnalyticsItem, Guild

data_blueprint = Blueprint('data', __name__)

class AnalyticsDashResource(MethodView):
    """ Analytics Dash Resource """
    async def get(self, days=14):
        auth = get_user_auth()

        if auth != 'm6YxwpQd':
            return 'Forbidden.', 403
        
        dt = AnalyticsItem.get_date(round_to='hour') - timedelta(days=int(days))
        
        serverHistorical: list = AnalyticsItem.query.filter(AnalyticsItem.date >= dt) \
            .filter(AnalyticsItem.key == 'servers') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .all()
        
        userHistorical: list = AnalyticsItem.query.filter(AnalyticsItem.date >= dt) \
            .filter(AnalyticsItem.key == 'users') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .filter(AnalyticsItem.value > 0) \
            .all()
        
        largestServers = db.session.query(Guild) \
            .filter(Guild.active == True) \
            .filter(Guild.members > 0) \
            .order_by(Guild.members.desc()) \
            .limit(10) \
            .all()
        
        return jsonify({
            'servers': [{
                'time': item.date.timestamp(),
                'value': item.value
            } for item in serverHistorical],
            'users': [{
                'time': item.date.timestamp(),
                'value': item.value
            } for item in userHistorical],
            'largestServers': [{
                'id': server.guild_id,
                'name': server.name,
                'bio': server.bio,
                'avatar': server.avatar,
                'members': server.members
            } for server in largestServers]
        }), 200

class NoneServersResource(MethodView):
    """ None Servers Resource """
    async def get(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guilds = db.session.query(Guild) \
            .filter(Guild.members == 0) \
            .filter(Guild.active == True) \
            .all()
        
        return jsonify([guild.guild_id for guild in guilds]), 200

class ActiveServersResource(MethodView):
    """ Active Servers Resource """
    async def get(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guilds = db.session.query(Guild) \
            .filter(Guild.members > 0) \
            .filter(Guild.active == True) \
            .order_by(Guild.members.desc()) \
            .limit(300) \
            .all()
        
        return jsonify([guild.guild_id for guild in guilds]), 200

class UserAnalyticsResource(MethodView):
    """ User Analytics Resource """
    async def get(self, year: int=None, month: int=None, day: int=None, hour: int=None):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if hour == None:
            hour = datetime.now().hour
        if day == None:
            day = datetime.now().day
        if month == None:
            month = datetime.now().month
        if year == None:
            year = datetime.now().year
        dt = datetime(year, month, day, hour, 0)

        item: AnalyticsItem = AnalyticsItem.query.filter(AnalyticsItem.date == dt) \
            .filter(AnalyticsItem.key == 'users') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .first()
        
        if item is not None:
            return jsonify({
                'value': item.value
            }), 200
        else:
            return 'Not Found', 404

    async def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        dt = AnalyticsItem.get_date(round_to='hour')
        value = db.session.query(func.sum(Guild.members)) \
            .filter(Guild.active == True) \
            .scalar()

        item: AnalyticsItem = AnalyticsItem.query.filter(AnalyticsItem.date == dt) \
            .filter(AnalyticsItem.key == 'users') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .first()
        if item is None:
            item = AnalyticsItem('BOT INTERNAL', 'users', value, dt)
        else:
            item.value = value

        db.session.add(item)
        db.session.commit()

        return jsonify({
            'time': dt.timestamp(),
            'value': value
        }), 201

class ServerAnalyticsResource(MethodView):
    """ Server Analytics Resource """
    async def get(self, year: int=None, month: int=None, day: int=None, hour: int=None):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if hour == None:
            hour = datetime.now().hour
        if day == None:
            day = datetime.now().day
        if month == None:
            month = datetime.now().month
        if year == None:
            year = datetime.now().year
        dt = datetime(year, month, day, hour, 0)

        item: AnalyticsItem = AnalyticsItem.query.filter(AnalyticsItem.date == dt) \
            .filter(AnalyticsItem.key == 'servers') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .first()
        
        if item is not None:
            return jsonify({
                'value': item.value
            }), 200
        else:
            return 'Not Found', 404
    async def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403

        dt = AnalyticsItem.get_date(round_to='hour')
        value = db.session.query(Guild.active) \
            .filter(Guild.active == True) \
            .count()

        item: AnalyticsItem = AnalyticsItem.query.filter(AnalyticsItem.date == dt) \
            .filter(AnalyticsItem.key == 'servers') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .first()
        if item is None:
            item = AnalyticsItem('BOT INTERNAL', 'servers', value, dt)

        db.session.add(item)
        db.session.commit()

        return jsonify({
            'time': dt.timestamp(),
            'value': value
        }), 201

class LargestServersResource(MethodView):
    """ Largest Servers Resource to get the largest servers the bot has """
    async def get(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403

        guilds = db.session.query(Guild) \
            .filter(Guild.active == True) \
            .filter(Guild.members > 0) \
            .order_by(Guild.members.desc()) \
            .limit(10) \
            .all()
        
        return jsonify([{
            'name': server.name,
            'bio': server.bio,
            'avatar': server.avatar,
            'members': server.members
        } for server in guilds]), 200

class BotDataResource(MethodView):
    """ Bot Data Resource """
    async def get(self, key):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        data: BotData = BotData.query.filter(BotData.key == key).first()

        if data is None:
            return 'Not Found', 404
        else:
            return jsonify({
                'value': data.value
            }), 200
    async def put(self, key, value):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        data: BotData = BotData.query.filter_by(key == key).first()

        if data is None:
            data = BotData(key, value)
        else:
            data.value = value
        
        db.session.add(data)
        db.session.commit()

        return jsonify({
            'value': data.value
        }), 200
    async def patch(self, key, value):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data: dict = request.get_json()
        data: BotData = BotData.query.filter_by(key == key).first()

        method: str = post_data.get('method')
        valid_methods = ['increment']

        if method is None:
            return 'Missing Method', 400
        else:
            if not method in valid_methods:
                return 'Invalid Method', 400
            method = method.lower()

        if data is None:
            if method == 'increment':
                data = BotData(key, value)
            elif method == 'decrement':
                data = BotData(key, 0)
        else:
            data.value = value

            if method == 'increment':
                data.value = str(int(data.value) + int(value))

data_blueprint.add_url_rule('/data/<key>', view_func=BotDataResource.as_view('botdata_get'))
data_blueprint.add_url_rule('/data/<key>/<value>', view_func=BotDataResource.as_view('botdata'))

data_blueprint.add_url_rule('/analytics/servers/dash', view_func=AnalyticsDashResource.as_view('dash_analytics'))
data_blueprint.add_url_rule('/analytics/servers/dash/<days>', view_func=AnalyticsDashResource.as_view('dash_analytics_days'))

data_blueprint.add_url_rule('/analytics/servers/largest', view_func=LargestServersResource.as_view('largest_servers'))
data_blueprint.add_url_rule('/analytics/servers/unindexed', view_func=NoneServersResource.as_view('none_servers'))
data_blueprint.add_url_rule('/analytics/servers/active', view_func=ActiveServersResource.as_view('active_servers'))

data_blueprint.add_url_rule('/analytics/servers', view_func=ServerAnalyticsResource.as_view('server_analytics'))
data_blueprint.add_url_rule('/analytics/servers/<year>', view_func=ServerAnalyticsResource.as_view('server_analytics_y'))
data_blueprint.add_url_rule('/analytics/servers/<year>/<month>', view_func=ServerAnalyticsResource.as_view('server_analytics_ym'))
data_blueprint.add_url_rule('/analytics/servers/<year>/<month>/<day>', view_func=ServerAnalyticsResource.as_view('server_analytics_ymd'))
data_blueprint.add_url_rule('/analytics/servers/<year>/<month>/<day>/<hour>', view_func=ServerAnalyticsResource.as_view('server_analytics_ymdh'))

data_blueprint.add_url_rule('/analytics/users', view_func=UserAnalyticsResource.as_view('user_analytics'))
data_blueprint.add_url_rule('/analytics/users/<year>', view_func=UserAnalyticsResource.as_view('user_analytics_y'))
data_blueprint.add_url_rule('/analytics/users/<year>/<month>', view_func=UserAnalyticsResource.as_view('user_analytics_ym'))
data_blueprint.add_url_rule('/analytics/users/<year>/<month>/<day>', view_func=UserAnalyticsResource.as_view('user_analytics_ymd'))
data_blueprint.add_url_rule('/analytics/users/<year>/<month>/<day>/<hour>', view_func=UserAnalyticsResource.as_view('user_analytics_ymdh'))