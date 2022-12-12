from csv import reader
import random
import re
import string
import uuid
import aiohttp
import project.helpers.token as token
import geoip2.database as geoip

from user_agents import parse as parse_ua
from json import JSONDecoder
from datetime import datetime
from werkzeug.exceptions import Forbidden
from flask import Blueprint, request, jsonify, make_response
from flask.views import MethodView
from project import app, db, get_shared_state, bot_api
from project.helpers.Cache import Cache

from project.server.models import GuildUser, UserInfo, Guild, BlacklistedRefreshToken

AUTH_TOKEN_EXPIRY = 60 * 60 # Auth tokens expire after an hour
REFRESH_TOKEN_EXPIRY = 60 * 60 * 24 * 14 # Refresh tokens expire after two weeks

auth_blueprint = Blueprint('auth', __name__)

shared_dict, shared_lock = get_shared_state(port=35794, key=b"auth_code")
code_cache = Cache(60*10, shared_dict) # Codes expire after 10 minutes

shared_dict2, shared_lock2 = get_shared_state(port=35795, key=b"config_cache")
config_cache = Cache(60*10, shared_dict2) # Config check caches expire after 10 minutes

geoip_reader = geoip.Reader('/usr/share/GeoIP/GeoLite2-City.mmdb')

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

def is_guild_active(guild_id: str):
    guild: Guild = Guild.query \
        .filter(Guild.guild_id == guild_id) \
        .first()
    
    if guild is not None:
        return guild.active == True
    return False

async def handle_channel_config(server, value):
    if str(value) == None:
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
    if int(value) == None:
        raise Exception
    cached = config_cache.get(f'{server}/role/{value}')
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
    url = re.search("(?P<url>https?://[^\s\]\[]+)", value).group("url")
    if url is None:
        raise Exception
    return url

config_handlers = {
    'verification_channel': handle_channel_config,
    'logs_channel': handle_channel_config,
    'nsfw_logs_channel': handle_channel_config,
    'automod_logs_channel': handle_channel_config,
    'traffic_logs_channel': handle_channel_config,
    'message_logs_channel': handle_channel_config,
    'welcome_channel': handle_channel_config,
    'verify_logs_channel': handle_channel_config,
    'action_logs_channel': handle_channel_config,
    'verified_role': handle_role_config,
    'unverified_role': handle_role_config,
    'mute_role': handle_role_config,
    'toxicity': handle_threshold_config,
    'hatespeech': handle_threshold_config,
    'automod_spam': handle_number_config,
    'url_filter': handle_bool_config,
    'automod_duplicate': handle_bool_config,
    'invite_link_filter': handle_bool_config,
    'use_welcome': handle_bool_config,
    'welcome_image': handle_url_config,
    'welcome_message': handle_string_config
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
                .filter(GuildUser.guild_id == guild_id) \
                .first()
            
            if guild_data is None:
                return 'Guild not in database', 400
            else:
                return jsonify(guild_data.config), 200
        else:
            return 'Forbidden', 403
    async def patch(self, guild_id: str):
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
                post_data: dict = request.get_json()
                failures = {}
                newValues = {}

                bot_api.session = aiohttp.ClientSession()
                for key in post_data.keys():
                    handler = config_handlers.get(key)
                    if handler is not None:
                        try:
                            guild_data.config[key] = await handler(guild_id, post_data.get(key))
                            newValues[key] = guild_data.config.get(key)
                        except Exception as e:
                            failures[key] = str(e)
                await bot_api.session.close()

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
                guilds.append(guild)

        return jsonify({
            'id': auth,
            'name': user_info.name,
            'avatar': user_info.avatar,
            'premium': user_info.premium,
            'guilds': [{
                'id': guild['id'],
                'avatar': guild['avatar'],
                'name': guild['name'],
                'active': is_guild_active(guild['id'])
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

            return jsonify({
                'auth': AuthToken.generate(refresh_token.user_id),
                'refresh': RefreshToken.generate(refresh_token.user_id)
            }), 200
        except:
            return 'Refresh token has expired, please login again', 403

auth_blueprint.add_url_rule('/auth', view_func=LoginResource.as_view('login'))
auth_blueprint.add_url_rule('/auth/status/<code>', view_func=LoginStatusResource.as_view('login_status'))
auth_blueprint.add_url_rule('/auth/status/<code>/<user_id>', view_func=LoginStatusResource.as_view('login_status_update'))
auth_blueprint.add_url_rule('/auth/refresh', view_func=RefreshResource.as_view('login_refresh'))

auth_blueprint.add_url_rule('/servers/<guild_id>/config', view_func=ServerConfigResource.as_view('server_config'))