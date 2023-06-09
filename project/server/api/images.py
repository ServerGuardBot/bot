VALID_RESOURCES = [
    'avatar',
    'banner'
]
DEFAULT_RESOURCES = {
    'avatar': 'https://img.guildedcdn.com/asset/DefaultUserAvatars/profile_1.png',
    'banner': 'https://images.unsplash.com/photo-1519638399535-1b036603ac77',
}
USER_RESOURCE_MAP = {
    'avatar': 'profilePictureLg',
    'banner': 'profileBannerLg',
}

from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import BotAPI, app, db
from werkzeug.exceptions import Forbidden, NotFound

import requests

images_blueprint = Blueprint('images', __name__)

class ProxyServerImage(MethodView):
    """ Resource for proxying Guilded server-related image resources """
    async def get(self, server_id: str, resource: str):
        if not resource.lower() in VALID_RESOURCES:
            raise Forbidden(f'Expected one of {", ".join(VALID_RESOURCES)}, got {resource}')
        with BotAPI() as bot_api:
            try:
                url = ''

                server_data = await bot_api.get_server(server_id)
                server_data: dict = server_data['server']

                url = server_data.get(resource, DEFAULT_RESOURCES[resource])

                response = requests.get(url, headers={
                'User-Agent': 'Guilded Server Guard/1.0 (Image Proxy)'
                }, stream=True)
                try:
                    response.headers.pop('Transfer-Encoding')
                except:
                    pass
                return (response.raw.read(), response.status_code, response.headers.items())
            except:
                raise NotFound('Server not found or bot not in server')

class ProxyUserImage(MethodView):
    """ Resource for proxying Guilded user-related image resources """
    async def get(self, user_id: str, resource: str):
        if not resource.lower() in VALID_RESOURCES:
            raise Forbidden(f'Expected one of {", ".join(VALID_RESOURCES)}, got {resource}')
        with BotAPI() as bot_api:
            try:
                url = ''

                user_data = await bot_api.get_user(user_id)
                user_data: dict = user_data['user']

                url = user_data.get(USER_RESOURCE_MAP.get(resource, resource), DEFAULT_RESOURCES[resource])

                response = requests.get(url, headers={
                'User-Agent': 'Guilded Server Guard/1.0 (Image Proxy)'
                }, stream=True)
                try:
                    response.headers.pop('Transfer-Encoding')
                except:
                    pass
                return (response.raw.read(), response.status_code, response.headers.items())
            except:
                raise NotFound('User not found or bot not in server')

images_blueprint.add_url_rule('/resources/server/<string:server_id>/<string:resource>', view_func=ProxyServerImage.as_view('proxy_server_image'))
images_blueprint.add_url_rule('/resources/user/<string:user_id>/<string:resource>', view_func=ProxyUserImage.as_view('proxy_user_image'))