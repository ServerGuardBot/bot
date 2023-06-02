from csv import reader
import os
import random
import re
import string
import uuid
import project.helpers.token as token
import geoip2.database as geoip

from user_agents import parse as parse_ua
from json import JSONDecoder
from datetime import datetime
from werkzeug.exceptions import Forbidden
from flask import Blueprint, request, jsonify, make_response
from flask.views import MethodView
from project import app, db, get_shared_state, BotAPI
from project.helpers.Cache import Cache
from project.helpers.images import *
from guilded import http

from project.server.models import GuildUser, UserInfo, Guild, BlacklistedRefreshToken, GuildActivity

AUTH_TOKEN_EXPIRY = 60 * 60 # Auth tokens expire after an hour
REFRESH_TOKEN_EXPIRY = 60 * 60 * 24 * 14 # Refresh tokens expire after two weeks

auth_blueprint = Blueprint('auth', __name__)

shared_dict, shared_lock = get_shared_state(port=35794, key=b"auth_code")
code_cache = Cache(60*10, shared_dict) # Codes expire after 10 minutes

shared_dict2, shared_lock2 = get_shared_state(port=35795, key=b"config_cache")
config_cache = Cache(60*10, shared_dict2) # Config check caches expire after 10 minutes

geoip_reader = geoip.Reader(os.getenv('GEOIP_DB', '/usr/share/GeoIP/GeoLite2-City.mmdb'))

class AuthToken:
    user_id: str

    @staticmethod
    def generate(user_id: str):
        return token.encodeToken({
            'user': user_id,
            'exp': datetime.now().timestamp() + AUTH_TOKEN_EXPIRY
        })
    
    @staticmethod
    def decode(t: str):
        payload = token.decodeToken(t)
        return AuthToken(payload.get('user'))

    def __init__(self, user_id: str):
        self.user_id = user_id

class RefreshToken:
    user_id: str
    expires: datetime

    @staticmethod
    def generate(user_id: str):
        return token.encodeToken({
            'user': user_id,
            'exp': datetime.now().timestamp() + REFRESH_TOKEN_EXPIRY
        })
    
    @staticmethod
    def decode(t: str):
        payload = token.decodeToken(t)
        return RefreshToken(payload.get('user'), datetime.fromtimestamp(payload.get('exp')))

    def __init__(self, user_id: str, expires: datetime):
        self.user_id = user_id
        self.expires = expires

def get_user_auth():
    auth = request.cookies.get('auth')

    if auth is None:
        raise Forbidden('Please provide a valid auth token')
    
    try:
        auth_token = AuthToken.decode(auth)

        return auth_token.user_id
    except:
        raise Forbidden('Please provide a valid auth token')

def blacklist_token(refresh: str):
    is_blacklisted = BlacklistedRefreshToken.query \
        .filter(BlacklistedRefreshToken.token == refresh) \
        .first()
    
    if is_blacklisted is None:
        try:
            t = RefreshToken.decode(refresh)
            blacklist = BlacklistedRefreshToken(refresh, t.expires)

            db.session.add(blacklist)
            db.session.commit()
        except:
            # Silently fail as the token is already expired or invalid
            pass

def log_guild_activity(guild_id: str, user_id: str, action: dict):
    activity = GuildActivity(guild_id, user_id, action)
    db.session.add(activity)
    db.session.commit()

    return activity.activity_id

def is_guild_active(guild_id: str):
    guild: Guild = Guild.query \
        .filter(Guild.guild_id == guild_id) \
        .first()
    
    if guild is not None:
        return guild.active == True
    return False

async def handle_channel_config(server, value):
    with BotAPI() as bot_api:
        if str(value) == None and value != '':
            raise Exception
        elif str(value).strip() != '':
            uuid.UUID(value) # This will error if it is not a valid UUID
            cached = config_cache.get(f'channel/{value}')
            if cached is not None:
                if not cached:
                    raise Exception
            else:
                try:
                    await bot_api.get_channel(value) # Only check this if it is not a blank string
                    cached = True
                except:
                    cached = False
                config_cache.set(f'channel/{value}', cached)
                if not cached:
                    raise Exception
        return value

async def handle_role_config(server, value):
    server: Guild = server
    if int(value) == None:
        raise Exception
    if int(value) == 0:
        return None
    cached = config_cache.get(f'{server.guild_id}/role/{value}')
    if cached is not None:
        if not cached:
            raise Exception
        # TODO: Validate role's existence in server once bot API supports it natively
    return value

async def handle_number_config(server, value):
    if int(value) == None:
        raise Exception
    return int(value)

async def handle_threshold_config(server, value):
    if int(value) == None:
        raise Exception
    return max(min(int(value), 100), 0)

async def handle_bool_config(server, value):
    if int(value) is not None:
        value = int(value) == 1
    elif bool(value) is None:
        raise Exception
    return value and 1 or 0

async def handle_string_config(server, value):
    if str(value) is None:
        raise Exception
    return str(value)

async def handle_url_config(server, value):
    value = str(value)
    if value is None:
        raise Exception
    if value == '':
        return value
    url = re.search("(?P<url>https?://[^\s\]\[]+)", value).group("url")
    if url is None:
        raise Exception
    return url

async def handle_list_config(server, value):
    value = JSONDecoder().decode(value)
    if type(value) is not list:
        raise Exception
    return value

async def handle_perm_config(server, value):
    value = JSONDecoder().decode(value)
    if type(value) is not list:
        raise Exception
    permsList = []
    for role in value:
        role: dict
        if len(role.get('perms', [])) > 0 and ('Admin' in role['perms'] or 'Moderator' in role['perms']):
            permsList.append({
                'id': role['id'],
                'level': 'Admin' in role['perms'] and 1 or 0
            })
    return permsList

async def handle_trusted_config(server, value):
    value = JSONDecoder().decode(value)
    if type(value) is not list:
        raise Exception
    permsList = []
    for role in value:
        role: dict
        if 'Trusted' in role.get('perms', []):
            permsList.append(role['id'])
    return permsList

async def handle_xp_gain(server, value):
    value = JSONDecoder().decode(value)
    if type(value) is not list:
        raise Exception
    xpGains = {}
    for role in value:
        role: dict
        if role['xp'] == 0: continue
        xpGains[str(role['id'])] = role['xp']
    return xpGains

def premium_config(level, handler):
    async def handle(server, value):
        server: Guild = server
        premium = 0
        guild_owner: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == server.guild_id) \
            .filter(GuildUser.permission_level == 4) \
            .first()
        if guild_owner is not None:
            guild_owner_user: UserInfo = UserInfo.query \
                .filter(UserInfo.user_id == guild_owner.user_id) \
                .first()
            if guild_owner_user is not None:
                premium = int(guild_owner_user.premium)
        if premium < level:
            raise Exception
        return await handler(server, value)
    return handle

config_handlers = {
    'verification_channel': handle_channel_config,
    'log_commands': handle_bool_config,
    'silence_commands': handle_bool_config,
    'logs_channel': handle_channel_config,
    'nsfw_logs_channel': premium_config(1, handle_channel_config),
    'automod_logs_channel': handle_channel_config,
    'traffic_logs_channel': handle_channel_config,
    'message_logs_channel': handle_channel_config,
    'welcome_channel': handle_channel_config,
    'verify_logs_channel': handle_channel_config,
    'action_logs_channel': handle_channel_config,
    'user_logs_channel': handle_channel_config,
    'management_logs_channel': handle_channel_config,
    'log_role_changes': handle_bool_config,
    'verified_role': handle_role_config,
    'unverified_role': handle_role_config,
    'mute_role': handle_role_config,
    'toxicity': handle_threshold_config,
    'hatespeech': handle_threshold_config,
    'automod_spam': handle_number_config,
    'url_filter': handle_bool_config,
    'automod_duplicate': handle_bool_config,
    'invite_link_filter': handle_bool_config,
    'admin_contact': handle_url_config,
    'use_welcome': handle_bool_config,
    'welcome_image': handle_url_config,
    'welcome_message': handle_string_config,
    'block_tor': handle_bool_config,
    'raid_guard': handle_bool_config,
    'filters': handle_list_config,
    'rf_blacklist': handle_list_config,
    'rf_toxicity': handle_threshold_config,
    'rf_hatespeech': handle_threshold_config,
    'rf_nsfw': premium_config(1, handle_threshold_config),
    'roles': handle_perm_config,
    'trusted_roles': handle_trusted_config,
    'untrusted_block_images': handle_bool_config,
    'xp_gain': handle_xp_gain,
    'use_leave': handle_bool_config,
    'leave_image': handle_url_config,
    'leave_message': handle_string_config,
}

class ServerConfigResource(MethodView):
    """ Server Config Resource """
    async def get(self, guild_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            guild_data: Guild = Guild.query \
                .filter(Guild.guild_id == guild_id) \
                .first()
            
            if guild_data is None:
                return 'Guild not in database', 400
            else:
                print(guild_data.config)
                return jsonify(guild_data.config), 200
        else:
            return 'Forbidden', 403
    async def patch(self, guild_id: str):
        with BotAPI() as bot_api:
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == guild_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
            
            if guild_user is not None and guild_user.permission_level > 2:
                guild_data: Guild = Guild.query \
                    .filter(Guild.guild_id == guild_id) \
                    .first()
                
                if guild_data is None:
                    return 'Guild not in database', 400
                else:
                    post_data: dict = request.get_json()
                    failures = {}
                    newValues = {}

                    for key in post_data.keys():
                        handler = config_handlers.get(key)
                        if handler is not None:
                            try:
                                guild_data.config[key] = await handler(guild_data, post_data.get(key))
                                newValues[key] = guild_data.config.get(key)
                            except Exception as e:
                                failures[key] = str(e)
                    
                    db.session.add(guild_data)
                    db.session.commit()

                    if len(failures) == len(post_data):
                        return jsonify({
                            'failures': failures
                        }), 400
                    else:
                        return jsonify({
                            'failures': failures,
                            'values': newValues
                        }), 200
            else:
                return 'Forbidden', 403

def get_user(user_id: str):
    user: UserInfo = UserInfo.query \
        .filter(UserInfo.user_id == user_id) \
        .first()
    
    if user is None:
        return {
            'id': user_id,
            'name': f'Unknown <{user_id}>',
            'avatar': IMAGE_DEFAULT_AVATAR
        }
    else:
        return {
            'id': user_id,
            'name': user.name,
            'avatar': user.avatar
        }

class ServerActivityResource(MethodView):
    async def get(self, guild_id: str, start_index: int):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            activity = GuildActivity.query \
                .filter(GuildActivity.guild_id == guild_id) \
                .order_by(GuildActivity.logged_at.desc()) \
                .limit(50)
            if start_index is not None:
                activity = activity.offset(start_index)
            activity = activity.all()
            
            return jsonify([
                {
                    'id': a.activity_id,
                    'action': a.action,
                    'user': get_user(a.user_id),
                    'logged_at': a.logged_at.timestamp()
                } for a in activity
            ])
        else:
            return 'Forbidden', 403

class LoginResource(MethodView):
    """ Login Resource """
    async def get(self):
        auth = get_user_auth()

        user_info: UserInfo = UserInfo.query \
            .filter(UserInfo.user_id == auth) \
            .first()
        
        guilds = []

        for guild in JSONDecoder().decode(user_info.guilds):
            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == guild['id']) \
                .filter(GuildUser.user_id == auth) \
                .first()
            if guild_user is not None and guild_user.permission_level > 2:
                guild_owner: GuildUser = GuildUser.query \
                    .filter(GuildUser.guild_id == guild['id']) \
                    .filter(GuildUser.permission_level == 4) \
                    .first()
                if guild_owner is not None:
                    guild_owner_user: UserInfo = UserInfo.query \
                        .filter(UserInfo.user_id == guild_owner.user_id) \
                        .first()
                    if guild_owner_user is not None:
                        guild['premium'] = int(guild_owner_user.premium)
                guilds.append(guild)

        return jsonify({
            'id': auth,
            'name': user_info.name,
            'avatar': user_info.avatar,
            'premium': int(user_info.premium),
            'guilds': [{
                'id': guild['id'],
                'avatar': guild['avatar'],
                'name': guild['name'],
                'active': is_guild_active(guild['id']),
                'premium': guild.get('premium', 0),
            } for guild in guilds]
        }), 200
    async def post(self):
        try:
            get_user_auth()

            return 'You must be logged out to do that!', 403
        except Forbidden:
            code = ''.join(random.choices(string.ascii_letters + '_-' + string.digits, k=32))
            while code.startswith('_') and code.endswith('_'):
                # Make sure the code cannot start with or end with markdown formatters
                code = ''.join(random.choices(string.ascii_letters + '_-' + string.digits, k=32))
            
            post_data = request.get_json()

            ip = request.headers.get('cf-connecting-ip', request.environ.get('HTTP_X_REAL_IP', request.remote_addr))
            try:
                response = geoip_reader.city(ip)
                location = f'{response.city.name}, {response.country.name}'
            except:
                location = 'Unknown, Space'
            
            parsed_ua = parse_ua(request.user_agent.string)

            code_cache.set(code, {
                'lock': post_data.get('lock'),
                'browser': parsed_ua.browser.family,
                'platform': parsed_ua.os.family,
                'location': location
            })
            return jsonify({
                'code': code
            }), 200
    async def delete(self):
        get_user_auth() # This will fail the request if they are logged out already

        refresh = request.cookies.get('refresh')
        if refresh is not None and refresh is not '':
            blacklist_token(refresh)

        return 'Success', 200

class LoginStatusResource(MethodView):
    """ Login Status Resource """
    async def get(self, code):
        status = code_cache.get(code)

        auth = request.headers.get('authorization')

        if status is None:
            return 'Not Found', 404
        else:
            if status.get('user') == None:
                if auth == app.config.get('SECRET_KEY'):
                    return jsonify(status), 200 # If it's the bot getting this, then we return the status object
                return 'Waiting', 204
            else:
                post_data: dict = request.args
                if post_data.get('lock') != status.get('lock'):
                    return 'Forbidden', 403
                code_cache.remove(code)

                return jsonify({
                    'auth': AuthToken.generate(status.get('user')),
                    'refresh': RefreshToken.generate(status.get('user'))
                }), 200
    async def post(self, code, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if isinstance(code_cache.get(code), dict):
            code_cache.set(code, {
                'user': user_id,
                'lock': code_cache.get(code).get('lock')
            })

            user = UserInfo.query.filter(UserInfo.user_id == user_id).first()
            if user is not None:
                with BotAPI() as bot_api:
                    try:
                        guilds: list = (await bot_api.request(http.Route('GET', f'/users/{user_id}/teams', override_base=http.Route.USER_BASE))).get('teams', [])
                    except:
                        guilds = None
                    if guilds is not None:
                        UserInfo.update_guilds(user, guilds)
                        db.session.add(user)
                        db.session.commit()

            return 'Success', 200
        else:
            return 'Not Found', 404

class RefreshResource(MethodView):
    """ Refresh Resource """
    async def post(self):
        refresh = request.cookies.get('refresh')

        if refresh is None:
            return 'Bad Request', 400
        
        try:
            refresh_token = RefreshToken.decode(refresh)

            is_blacklisted = BlacklistedRefreshToken.query \
                .filter(BlacklistedRefreshToken.token == refresh) \
                .first()
            
            if is_blacklisted is not None:
                return 'Bad Request', 400
            
            blacklist_token(refresh)

            user = UserInfo.query.filter(UserInfo.user_id == refresh_token.user_id).first()
            if user is not None:
                with BotAPI() as bot_api:
                    try:
                        guilds: list = (await bot_api.request(http.Route('GET', f'/users/{refresh_token.user_id}/teams', override_base=http.Route.USER_BASE))).get('teams', [])
                    except:
                        guilds = None
                    if guilds is not None:
                        UserInfo.update_guilds(user, guilds)
                        db.session.add(user)
                        db.session.commit()

            return jsonify({
                'auth': AuthToken.generate(refresh_token.user_id),
                'refresh': RefreshToken.generate(refresh_token.user_id)
            }), 200
        except:
            return 'Refresh token has expired, please login again', 403

class CleanupResource(MethodView):
    """ Database Cleanup Resource """
    async def post(self):
        tokens: dict = BlacklistedRefreshToken.query \
            .filter(datetime.now() > BlacklistedRefreshToken.expires) \
            .all()
        
        for token in tokens:
            db.session.delete(token)
        db.session.commit()
        return 'Success', 200

auth_blueprint.add_url_rule('/auth', view_func=LoginResource.as_view('login'))
auth_blueprint.add_url_rule('/auth/status/<code>', view_func=LoginStatusResource.as_view('login_status'))
auth_blueprint.add_url_rule('/auth/status/<code>/<user_id>', view_func=LoginStatusResource.as_view('login_status_update'))
auth_blueprint.add_url_rule('/auth/refresh', view_func=RefreshResource.as_view('login_refresh'))
auth_blueprint.add_url_rule('/db/cleanup', view_func=CleanupResource.as_view('cleanup_db'))

auth_blueprint.add_url_rule('/servers/<guild_id>/config', view_func=ServerConfigResource.as_view('server_config'))
auth_blueprint.add_url_rule('/servers/<guild_id>/activity', view_func=ServerActivityResource.as_view('server_activity'))
auth_blueprint.add_url_rule('/servers/<guild_id>/activity/<int:start_index>', view_func=ServerActivityResource.as_view('server_activity_start_index'))