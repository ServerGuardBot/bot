from datetime import datetime
from dateutil import parser
from json import JSONDecoder
from project import bot_config
from project.helpers.images import *
from guilded import Embed
from humanfriendly import format_timespan
import requests, guilded

decoder = JSONDecoder()

ACCOUNT_AGE_THRESHOLD = 60 * 60 * 24 * 7

async def evaluate_user(guild_id: str, user_id: str, connections: str):
    socials: dict = decoder.decode(connections)
    user_req = requests.get(f'https://www.guilded.gg/api/v1/servers/{guild_id}/members/{user_id}', headers={
        'Authorization': f'Bearer {bot_config.GUILDED_BOT_TOKEN}'
    })

    if not user_req.status_code == 200:
        raise Exception
    
    user = user_req.json().get('member')

    db_user_req = requests.get(f'http://localhost:5000/getguilduser/{guild_id}/{user_id}', headers={
        'authorization': bot_config.SECRET_KEY
    })
    if db_user_req.status_code == 200:
        db_user = db_user_req.json()
    else:
        db_user = None

    scores = {
        'roblox': eval_roblox(socials.get('roblox', {}).get('service_id') or socials.get('roblox', {}).get('serviceId')),
        'steam': eval_steam(socials.get('steam', {}).get('service_id') or socials.get('steam', {}).get('serviceId')),
        'youtube': eval_youtube(socials.get('youtube', {}).get('handle')),
        'twitter': eval_twitter(socials.get('twitter', {}).get('handle'))
    }

    using_vpn = db_user != None and db_user.get('using_vpn') or False

    created_at = parser.parse(user.get('user').get('createdAt')).replace(tzinfo=None)
    age = (datetime.now().replace(tzinfo=None) - created_at).total_seconds()
    age_score = round((1 - (abs(min(age, ACCOUNT_AGE_THRESHOLD)) / ACCOUNT_AGE_THRESHOLD)) * 100)
    avatar_score = user.get('user').get('avatar') == None and 10 or 0 # Default avatar makes them more likely to be a troll or ban evader

    total_score = age_score + avatar_score
    total_evaled = 130 # Upper limits of the score

    if scores.get('roblox'):
        total_evaled += 100
        total_score += scores['roblox']
    if scores.get('steam'):
        total_evaled += 100
        total_score += scores['steam']
    if scores.get('youtube'):
        total_evaled += 100
        total_score += scores['youtube']
    if scores.get('twitter'):
        total_evaled += 100
        total_score += scores['twitter']

    return {
        'Name': user.get('user').get('name'),
        'User_Id': user_id,
        'User_Avatar': user.get('user').get('avatar') or IMAGE_DEFAULT_AVATAR,
        'Connection_Scores': scores,
        'Connections': socials,
        'VPN': using_vpn,
        'Age': (datetime.now() - created_at),
        'Score': round((total_score / total_evaled) * 100)
    }

def generate_embed(evaluation: dict, passed_check: bool=None, fail_reason: str=""):
    em: Embed = Embed(
        title=f'{evaluation["Name"]}\'s Evaluation',
        url=f'https://guilded.gg/profile/{evaluation["User_Id"]}',
        timestamp=datetime.now(),
        colour = passed_check is not None and (passed_check and guilded.Colour.blue() or guilded.Colour.red()) or passed_check is None and guilded.Colour.blue()
    ).set_thumbnail(url=evaluation['User_Avatar'])

    social_scores: dict = evaluation['Connection_Scores']
    if social_scores.get('roblox') != None:
        em.add_field(name='Roblox', value=f'{social_scores["roblox"]}%', inline=True)
    if social_scores.get('steam') != None:
        em.add_field(name='Steam', value=f'{social_scores["steam"]}%', inline=True)
    if social_scores.get('youtube') != None:
        em.add_field(name='Youtube', value=f'{social_scores["youtube"]}%', inline=True)
    if social_scores.get('twitter') != None:
        em.add_field(name='Twitter', value=f'{social_scores["twitter"]}%', inline=True)
    em.add_field(name='Account Age', value=format_timespan(evaluation['Age']), inline=True)
    em.add_field(name='VPN', value=evaluation['VPN'] and 'Yes' or 'No', inline=True)
    em.add_field(name='Suspicion Score', value=f'{evaluation["Score"]}%', inline=False)

    if passed_check is not None:
        em.add_field(name='Passed Check', value=passed_check and 'Yes' or 'No', inline=False)
        if passed_check is False:
            em.add_field(name='Failure Reason', value=fail_reason, inline=False)

    return em

def eval_roblox(id: str):
    if id == None:
        return None
    try:
        result = requests.get(f'https://users.roblox.com/v1/users/{id}')

        if result.status_code == 200:
            contents = result.json()
            if contents['isBanned'] == True:
                return 95

            created_at = parser.parse(contents['created']).replace(tzinfo=None)
            age = (datetime.now().replace(tzinfo=None) - created_at).total_seconds()
            age_score = round((1 - (abs(min(age, ACCOUNT_AGE_THRESHOLD)) / ACCOUNT_AGE_THRESHOLD)) * 100)

            return max(age_score - (contents['hasVerifiedBadge'] and 15 or 0), 0)
        else:
            return None
    except:
        return None

def eval_steam(id: int):
    if id == None:
        return None
    try:
        result = requests.get(f'http://api.steampowered.com/IPlayerService/GetSteamLevel/v1/?key={bot_config.STEAM_KEY}&steamid={id}')

        if result.status_code == 200:
            contents = result.json()

            return min((max(10 - contents['response'].get('player_level', 0), 0) / 10) * 100, 100)
        else:
            return None
    except:
        return None

def eval_youtube(id: str):
    if id == None:
        return None
    try:
        result = requests.get(f'https://www.googleapis.com/youtube/v3/channels?part=snippet&id={id}&key={bot_config.YOUTUBE_KEY}')

        if result.status_code == 200:
            contents = result.json()

            created_at = parser.parse(contents['items'][0]['snippet']['publishedAt']).replace(tzinfo=None)
            age = (datetime.now().replace(tzinfo=None) - created_at).total_seconds()
            age_score = round((1 - (abs(min(age, ACCOUNT_AGE_THRESHOLD)) / ACCOUNT_AGE_THRESHOLD)) * 100)

            return max(age_score, 0)
        else:
            return None
    except:
        return None

def eval_twitter(id: str):
    if id == None:
        return None
    try:
        result = requests.get(f'https://api.twitter.com/2/users/by/username/{id}?user.fields=created_at,verified,public_metrics', headers={
            'Authorization': f'Bearer {bot_config.TWITTER_BEARER}'
        })

        if result.status_code == 200:
            contents = result.json()

            if contents['data']['verified']:
                return 0

            created_at = parser.parse(contents['data']['created_at']).replace(tzinfo=None)
            age = (datetime.now().replace(tzinfo=None) - created_at).total_seconds()
            age_score = round((1 - (abs(min(age, ACCOUNT_AGE_THRESHOLD)) / ACCOUNT_AGE_THRESHOLD)) * 70)
            tweets_score = round(1 - (contents['data']['public_metrics']['tweet_count']/15) * 30)

            return max(age_score + tweets_score, 0)
        else:
            return None
    except:
        return None
