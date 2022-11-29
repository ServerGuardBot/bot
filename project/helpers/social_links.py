from project import bot_config
from project.helpers.Cache import Cache

import requests

connection_cache = Cache(60 * 5)

async def get_connections(guild_id: str, user_id: str):
    cached = connection_cache.get(user_id)
    if cached:
        return cached

    user_info_req = requests.get(f'http://localhost:5000/userinfo/{guild_id}/{user_id}', headers={
        'authorization': bot_config.SECRET_KEY
    })
    user_info = user_info_req.json()

    connections = user_info.get('connections')
    connection_cache.set(user_id, connections)

    return connections