from project import bot_api
from project.helpers.Cache import Cache

import aiohttp

premium_cache = Cache()

async def get_user_premium_status(user_id):
    cached = premium_cache.get(user_id)
    if cached is not None:
        return cached
    roles = await bot_api.get_member_roles('aE9Zg6Kj', user_id)
    if roles is not None:
        roles = roles['roleIds']
    else:
        roles = []

    if 32612283 in roles:
        cached = 3
    elif 32612284 in roles:
        cached = 2
    elif 32612285 in roles:
        cached = 1
    else:
        cached = 0
    
    premium_cache.set(user_id, cached)
    return cached