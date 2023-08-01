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

import io
import random
import string
import requests

from flask import Blueprint, request, send_file, jsonify
from flask.views import MethodView
from project import BotAPI, app, get_shared_state
from werkzeug.exceptions import Forbidden, NotFound
from project.helpers.Cache import Cache

images_blueprint = Blueprint('images', __name__)

shared_serving, shared_serving_lock = get_shared_state(port=35796, key=b"serving")
serving_cache = Cache(60 * 5, shared_serving) # Cache images to be served to guilded for 5 minutes

def serve_file(file: str):
    # generate an ID
    id = "".join(random.choices(string.ascii_letters, k=15))

    serving_cache.set(id, file)
    return id

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
                if url == None:
                    # For some dumb reason Guilded's API returns null, which translates to None in python
                    # So we have to check if it's none and apply default because .get considers None
                    # to be a valid value for some dumb reason.
                    url = DEFAULT_RESOURCES[resource]

                if request.args.get('blur', 'false').lower() == 'true':
                    if resource == 'banner':
                        url = url.replace('-Hero.png', '-SmallBlurred.jpg')
                        # Only banners to my knowledge have blurred versions so ignore other resources

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

                try:
                    user_data = await bot_api.get_user(user_id)
                    user_data: dict = user_data['user']

                    url = user_data.get(
                        USER_RESOURCE_MAP.get(resource, resource),
                        DEFAULT_RESOURCES[resource]
                    )
                    if url == None:
                        # For some dumb reason Guilded's API returns null, which translates to None in python
                        # So we have to check if it's none and apply default because .get considers None
                        # to be a valid value for some dumb reason.
                        url = DEFAULT_RESOURCES[resource]
                except:
                    url = DEFAULT_RESOURCES[resource]

                if request.args.get('blur', 'false').lower() == 'true':
                    if resource == 'banner':
                        url = url.replace('-Hero.png', '-SmallBlurred.jpg')
                        # Only banners to my knowledge have blurred versions so ignore other resources

                response = requests.get(url, headers={
                'User-Agent': 'Guilded Server Guard/1.0 (Image Proxy)'
                }, stream=True)
                try:
                    response.headers.pop('Transfer-Encoding')
                except:
                    pass
                return (response.raw.read(), response.status_code, response.headers.items())
            except NotFound:
                raise NotFound('User not found or bot not in server')
            except Exception as e:
                return f"An unknown error occurred: {e}", 500

class ServeImage(MethodView):
    """ Resource for serving images from the cache """
    async def get(self, image_id: str):
        cache_item: str = serving_cache.get(image_id)
        if cache_item is not None:
            cache_item = bytes.fromhex(cache_item)
            mem = io.BytesIO(cache_item)
            mem.seek(0)
            return send_file(mem, mimetype='image/png', as_attachment=True, download_name=f'{image_id}.png')
        else:
            raise NotFound('Image not found')
    async def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        id = serve_file(request.get_json()['file'])
        print(f'Serving image with ID {id}')
        return jsonify({'id': id}), 200

images_blueprint.add_url_rule('/resources/server/<string:server_id>/<string:resource>', view_func=ProxyServerImage.as_view('proxy_server_image'))
images_blueprint.add_url_rule('/resources/user/<string:user_id>/<string:resource>', view_func=ProxyUserImage.as_view('proxy_user_image'))
images_blueprint.add_url_rule('/serve/<string:image_id>', view_func=ServeImage.as_view('serve_image'))
images_blueprint.add_url_rule('/serve', view_func=ServeImage.as_view('add_serve_image'))