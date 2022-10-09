from guilded import Member, SocialLink, SocialLinkType
from project import client
from project.helpers.Cache import Cache

import requests

connection_cache = Cache(60 * 5)

async def get_connections(guild_id: str, user_id: str):
    cached = connection_cache.get(user_id)
    if cached:
        return cached

    profile_req = requests.get(f'https://www.guilded.gg/api/users/{user_id}/profilev3')

    connections = {}

    if profile_req.status_code == 200:
        profile: dict = profile_req.json()
        for t in profile.get('socialLinks'):
            connections[t['type']] = {
                'handle': t['handle'],
                'serviceId': t['serviceId']
            }
    else:
        # Fallback to Bot API method if the other method don't work
        user: Member = await client.get_server(guild_id).fetch_member(user_id)
        for t in SocialLinkType:
            if connections.get(t.value): # Skip any aliases that were already handled
                pass
            try:
                link: SocialLink = await user.fetch_social_link(t)
                connections[t.value] = {
                    'handle': link.handle,
                    'service_id': link.service_id
                }
            except Exception:
                pass # Silently error
        
        connection_cache.set(user_id, connections)

    return connections