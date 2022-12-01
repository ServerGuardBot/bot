from json import JSONDecoder
import random
import string
import project.helpers.token as token

from datetime import datetime
from werkzeug.exceptions import Forbidden
from flask import Blueprint, request, jsonify, make_response
from flask.views import MethodView
from project import app, db, get_shared_state
from project.helpers.Cache import Cache

from project.server.models import GuildUser, UserInfo, Guild, BlacklistedRefreshToken

AUTH_TOKEN_EXPIRY = 60 * 60 # Auth tokens expire after an hour
REFRESH_TOKEN_EXPIRY = 60 * 60 * 24 * 14 # Refresh tokens expire after two weeks

auth_blueprint = Blueprint('auth', __name__)

shared_dict, shared_lock = get_shared_state(port=35794, key=b"auth_code")
code_cache = Cache(60*10, shared_dict) # Codes expire after 10 minutes

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

class LoginResource(MethodView):
    """ Login Resource """
    async def get(self):
        auth = get_user_auth()
        # TODO: Make it provide extra info

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

            code_cache.set(code, False)
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

        if status is None:
            return 'Not Found', 404
        else:
            if status == False:
                return 'Waiting', 204
            else:
                code_cache.remove(code)

                return jsonify({
                    'auth': AuthToken.generate(status),
                    'refresh': RefreshToken.generate(status)
                }), 200
    async def post(self, code, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        if code_cache.get(code) is not None:
            code_cache.set(code, user_id)
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