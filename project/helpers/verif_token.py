from datetime import datetime

import jwt
import json
import project.helpers.token as token

TOKEN_EXPIRY = 60 * 10 # Tokens should expire after 10 minutes

encoder = json.JSONEncoder()
decoder = json.JSONDecoder()

class VerificationToken:
    guild_id: str
    user_id: str
    connections: dict

    def __init__(self, guild: str, user: str, connections: dict):
        self.guild_id = guild
        self.user_id = user
        self.connections = connections

def generate_token(guild_id: str, user_id: str, connections: dict):
    return token.encodeToken({
        'guild': guild_id,
        'user': user_id,
        'connections': encoder.encode(connections),
        'exp': datetime.now().timestamp() + TOKEN_EXPIRY
    })

def decode_token(t: str):
    try:
        payload = token.decodeToken(t)
        print(payload)
        connections = decoder.decode(payload.get('connections'))

        return VerificationToken(
            payload.get('guild'),
            payload.get('user'),
            connections
        )
    except jwt.ExpiredSignatureError as e:
        raise e
    except jwt.InvalidTokenError as e:
        raise e
    except Exception as e:
        raise e
