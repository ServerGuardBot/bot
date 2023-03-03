from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, db
from sqlalchemy import func

from project.server.api.auth import get_user_auth
from project.server.models import BotData, AnalyticsItem, Guild, GuildUser, UserInfo

import os
import psutil

data_blueprint = Blueprint('data', __name__)

class ServerCacheResource(MethodView):
    """ Server Cache Resource """
    async def get(self, guild_id):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            guild_data: Guild = Guild.query \
                .filter(GuildUser.guild_id == guild_id) \
                .first()
            
            if guild_data is None:
                return 'Guild not in database', 400
            else:
                cache: dict = guild_data.config.get('__cache', {})

                return jsonify({
                    'message': 'Success',
                    'cache': cache
                }), 200
    async def put(self, guild_id, type):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        guild_data: Guild = Guild.query \
            .filter(Guild.guild_id == guild_id) \
            .first()
        
        if guild_data is None:
            return 'Guild not in database', 400
        else:
            post_data: list = request.get_json()
            cache: dict = guild_data.config.get('__cache')

            if cache is None:
                cache = {}
                guild_data.config['__cache'] = cache

            cache_store: dict = cache.get(type)

            if cache_store is None:
                cache_store = {}
                cache[type] = cache_store

            for item in post_data:
                cache_store[item['id']] = item
            
            db.session.add(guild_data)
            db.session.commit()

            return jsonify({
                'message': 'Success'
            }), 200
    async def delete(self, guild_id, type):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        guild_data: Guild = Guild.query \
            .filter(Guild.guild_id == guild_id) \
            .first()
        
        if guild_data is None:
            return 'Guild not in database', 400
        else:
            post_data: list = request.get_json()
            cache: dict = guild_data.config.get('__cache')

            if cache is None:
                cache = {}
                guild_data.config['__cache'] = cache

            cache_store: dict = cache.get(type)

            if cache_store is None:
                cache_store = {}
                cache[type] = cache_store

            for item in post_data:
                del cache_store[item['id']]
            
            db.session.add(guild_data)
            db.session.commit()

            return jsonify({
                'message': 'Success'
            }), 200

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
        
        premiumHistorical: list = AnalyticsItem.query.filter(AnalyticsItem.date >= dt) \
            .filter(AnalyticsItem.key == 'premium_users') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .filter(AnalyticsItem.value > 0) \
            .all()
        
        largestServers = db.session.query(Guild) \
            .filter(Guild.active == True) \
            .filter(Guild.members > 0) \
            .order_by(Guild.members.desc()) \
            .limit(10) \
            .all()
        
        load1, load5, load15 = psutil.getloadavg()
        cpu_usage = (load15/os.cpu_count()) * 100
        total_memory, used_memory, free_memory = map(
            int, os.popen('free -t -m').readlines()[-1].split()[1:])
        hdd = psutil.disk_usage('/')
        
        return jsonify({
            'servers': [{
                'time': item.date.timestamp(),
                'value': item.value
            } for item in serverHistorical],
            'users': [{
                'time': item.date.timestamp(),
                'value': item.value
            } for item in userHistorical],
            'premium': [{
                'time': item.date.timestamp(),
                'value': item.value
            } for item in premiumHistorical],
            'largestServers': [{
                'id': server.guild_id,
                'name': server.name,
                'bio': server.bio,
                'avatar': server.avatar,
                'members': server.members
            } for server in largestServers],
            'cpu': cpu_usage,
            'ram': [round((used_memory/total_memory) * 100, 2), total_memory, used_memory, free_memory],
            'disk': [hdd.total / (2**30), hdd.used / (2**30), hdd.free / (2**30)]
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
        value2 = db.session.query(UserInfo.user_id) \
            .filter(UserInfo.premium > 0) \
            .count()

        item: AnalyticsItem = AnalyticsItem.query.filter(AnalyticsItem.date == dt) \
            .filter(AnalyticsItem.key == 'users') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .first()
        if item is None:
            item = AnalyticsItem('BOT INTERNAL', 'users', value, dt)
        else:
            item.value = value
        
        item2: AnalyticsItem = AnalyticsItem.query.filter(AnalyticsItem.date == dt) \
            .filter(AnalyticsItem.key == 'premium_users') \
            .filter(AnalyticsItem.guild_id == 'BOT INTERNAL') \
            .first()
        if item2 is None:
            item2 = AnalyticsItem('BOT INTERNAL', 'premium_users', value2, dt)
        else:
            item2.value = value2

        db.session.add(item)
        db.session.add(item2)
        db.session.commit()

        return jsonify({
            'time': dt.timestamp(),
            'value': value,
            'value2': value2,
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

data_blueprint.add_url_rule('/data/cache/<guild_id>', view_func=ServerCacheResource.as_view('servercache_get'))
data_blueprint.add_url_rule('/data/cache/<guild_id>/<type>', view_func=ServerCacheResource.as_view('servercache'))

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