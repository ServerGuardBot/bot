import binascii
import io
import math
import numpy as np
import scipy
import scipy.misc
import scipy.cluster
import scipy.stats
import requests

from datetime import datetime, timedelta
from json import JSONDecoder, JSONEncoder
from flask import Blueprint, request, jsonify, render_template
from flask.views import MethodView
from project import app, BotAPI, db
from project.server.models import Guild, GuildUser, UserInfo
from project.helpers.premium import get_user_premium_status
from guilded import SocialLinkType, http
from humanfriendly import format_number
from sqlalchemy import func
from PIL import Image

encoder = JSONEncoder()
decoder = JSONDecoder()

guilds_blueprint = Blueprint('guilds', __name__)

def get_dominant_color(image: Image.Image):
    """ Get the dominant color of the image """
    image = image.resize((150, 150))
    ar = np.asarray(image)
    shape = ar.shape
    ar = ar.reshape(scipy.product(shape[:2]), shape[2]).astype(float)
    
    codes, dist = scipy.cluster.vq.kmeans(ar, 5)
    
    vecs, dist = scipy.cluster.vq.vq(ar, codes)
    counts, bins = np.histogram(vecs, len(codes))
    
    index_max = np.argmax(counts)
    peak = codes[index_max]
    colour = binascii.hexlify(bytearray(int(c) for c in peak)).decode('ascii')
    return colour

async def get_user_info(guild_id: str, user_id: str):
    with BotAPI() as bot_api:
        user: UserInfo = UserInfo.query.filter(UserInfo.user_id == user_id).first()
        update_user = False

        if user is None:
            update_user = True
        else:
            if datetime.now() > user.last_updated + timedelta(days=1):
                update_user = True
                user.last_updated = datetime.now()
        
        if update_user:
            connections = {}

            try:
                profile: dict = await bot_api.request(http.Route('GET', f'/users/{user_id}/profilev3', override_base=http.Route.USER_BASE))
                for t in profile.get('socialLinks'):
                    connections[t['type']] = {
                        'handle': t['handle'],
                        'serviceId': t['serviceId']
                    }
            except:
                # Fallback to Bot API method if the other method don't work
                for t in SocialLinkType:
                    if connections.get(t.value): # Skip any aliases that were already handled
                        pass
                    try:
                        link: dict = (await bot_api.get_member_social_links(guild_id, user_id, t.value))['socialLink']
                        connections[t.value] = {
                            'handle': link.get('handle'),
                            'serviceId': link.get('service_id', link.get('serviceId'))
                        }
                    except Exception as e:
                        pass # Silently error
            
            guild_user: dict = (await bot_api.get_user(user_id)).get('user')

            try:
                guild_members = GuildUser.query.filter_by(user_id = user_id).all()
                guilds: list = []
                for member in guild_members:
                    member: GuildUser
                    guild: Guild = Guild.query.filter(Guild.guild_id == member.guild_id).first()
                    if guild and member.permission_level > 2 and guild.active:
                        guilds.append({
                            'id': guild.guild_id,
                            'name': guild.name,
                            'profilePicture': guild.avatar,
                        })
                # guilds: list = (await bot_api.request(http.Route('GET', f'/users/{user_id}/teams', override_base=http.Route.USER_BASE))).get('teams', [])
            except Exception as e:
                print(e)
                print('Failed to get guilds')
                # Fallback to an empty dict if not possible, or to None if we are updating
                if user is None:
                    guilds: list = {}
                else:
                    guilds = None

            premium = await get_user_premium_status(user_id)

            if user is None:
                user = UserInfo(user_id, guild_user, connections, guilds, premium)
            else:
                UserInfo.update_user_data(user, guild_user)
                UserInfo.update_connections(user, connections)
                if guilds is not None:
                    UserInfo.update_guilds(user, guilds)
                user.premium = str(premium)
            db.session.add(user)
            db.session.commit()
        return user

def human_format(num):
    num = float('{:.3g}'.format(num))
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '{}{}'.format('{:f}'.format(num).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

def getLevel(xp: int):
    return (xp < 0 and -math.ceil(math.sqrt(abs(xp))) or math.floor(math.sqrt(abs(xp)))) + 1

def getXP(level: int):
    return level < 0 and -math.pow(level - 1, 2) or math.pow(level - 1, 2)

class RankCardAPI(MethodView):
    """ Rank Card Resource """
    
    async def get(self, guild_id: int, user_id: int):
        user = await get_user_info(guild_id, user_id)
        guild_user = requests.get(f'http://localhost:5000/getguilduser/{guild_id}/{user_id}/xp', headers={
            'authorization': app.config.get('SECRET_KEY')
        }).json()
        banner = f'https://api.serverguard.xyz/resources/user/{user_id}/banner'
        image = Image.open(
            io.BytesIO( ( requests.get(banner, stream=True) ).content )
        )
        dominant_color = f'#{get_dominant_color(image)}'
        
        status = '#747f8d'
        
        level = getLevel(guild_user['xp'])
        cur_level_xp = getXP(level)
        next_level_xp = getXP(level + 1)
        
        formatted_exp, formatted_total_exp = human_format(int(guild_user['xp'])), human_format(next_level_xp)
        exp_percent = int(((guild_user['xp'] - cur_level_xp) / (next_level_xp - cur_level_xp)) * 100)
        
        return render_template('rank_card.html', username=user.name, levelup=request.args.get('levelup', 'hide'), profile_picture=user.avatar, rank=guild_user['rank'], status=status, experience=formatted_exp, exp_to_level=formatted_total_exp, exp_percent=exp_percent, background=banner, level=level, exp=formatted_exp, dominant_color=dominant_color)

class UserInfoResource(MethodView):
    """ User Info Resource """
    async def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        user_info: UserInfo = await get_user_info(guild_id, user_id)

        return jsonify({
            'id': user_info.user_id,
            'name': user_info.name,
            'avatar': user_info.avatar,
            'guilded_data': user_info.guilded_data,
            'created_at': user_info.created_at,
            'connections': user_info.connections,
            'language': user_info.language,
            
            'roblox': user_info.roblox,
            'steam': user_info.steam,
            'youtube': user_info.youtube,
            'twitter': user_info.twitter,

            'guilds': encoder.encode(user_info.guilds),
            'premium': int(user_info.premium)
        }), 200
    async def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        with BotAPI() as bot_api:
            user_info: UserInfo = await get_user_info(guild_id, user_id)

            post_data = request.get_json()

            for key in post_data.keys():
                try:
                    setattr(user_info, key, post_data.get(key))
                except Exception as e:
                    print(f'[WARNING]: "{key}" is not a valid member of the UserInfo model! <{e}>')
                    # Make sure that a failure doesn't lead to a 500 error and notifies the logs
            db.session.add(user_info)
            db.session.commit()
            
            return 'Success', 200

class GetGuildUser(MethodView):
    def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        db_user: GuildUser = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        if db_user:
            return jsonify({
                'guild_id': db_user.guild_id,
                'user_id': db_user.user_id,
                'browser_id': db_user.browser_id,
                'hashed_ip': db_user.hashed_ip,
                'is_banned': db_user.is_banned,
                'using_vpn': db_user.using_vpn,
                'bypass_verification': db_user.bypass_verification,
                'connections': db_user.connections,
                'permission_level': db_user.permission_level
            }), 200
        else:
            return 'Not found', 404
    def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        db_user: GuildUser = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        post_data: dict = request.get_json()
        if db_user:
            db_user.permission_level = int(post_data.get('permission_level'))
        else:
            db_user = GuildUser(guild_id, user_id, permission_level=int(post_data.get('permission_level')))
        db.session.add(db_user)
        db.session.commit()
        return 'Success', 200

class UpdateGuildUserXP(MethodView):
    def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        db_user: GuildUser = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        post_data: dict = request.get_json()
        if db_user:
            db_user.xp = int(post_data.get('xp'))
        else:
            db_user = GuildUser(guild_id, user_id)
            db_user.xp = int(post_data.get('xp'))
        db.session.add(db_user)
        db.session.commit()
        return 'Success', 200
    def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        query = db.session.query(GuildUser,
            func.rank() \
                .over(
                    order_by=GuildUser.xp.desc(),
                    partition_by=GuildUser.guild_id
                ) \
                .label('rank')
            ) \
            .filter(GuildUser.guild_id == guild_id) \
            .subquery()
        db_user = db.session.query(query) \
            .filter(query.c.user_id == user_id) \
            .first()
        
        if db_user == None:
            return 'Not found', 404

        return jsonify({
            'xp': db_user.xp,
            'rank': db_user.rank
        }), 200
        

class GuildData(MethodView):
    def get(self, guild_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild:
            return jsonify({
                'guild_id': guild.guild_id,
                'premium': guild.premium,
                'config': guild.config
            }), 200
        else:
            guild = Guild(guild_id)

            db.session.add(guild)
            db.session.commit()

            return jsonify({
                'guild_id': guild.guild_id,
                'premium': guild.premium,
                'config': guild.config
            }), 201
    def patch(self, guild_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data: dict = request.get_json()
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
        
        for key in post_data.keys():
            try:
                setattr(guild, key, post_data.get(key))
            except Exception as e:
                print(f'[WARNING]: "{key}" is not a valid member of the Guild model! <{e}>')
                # Make sure that a failure doesn't lead to a 500 error and notifies the logs

        db.session.add(guild)
        db.session.commit()

        return jsonify({
            'guild_id': guild.guild_id,
            'premium': guild.premium,
            'config': guild.config
        }), 200
    def delete(self, guild_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild:
            db.session.delete(guild)
            db.session.commit()

            return jsonify({'message': 'Deleted', 'original_guild': jsonify(guild)}), 204

class GuildConfig(MethodView):
    def get(self, guild_id, item):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
            guild.config = {}

            db.session.add(guild)
            db.session.commit()
        
        if guild.config == None:
            guild.config = {}

            db.session.add(guild)
            db.session.commit()
        
        value = guild.config.get(item)
        return jsonify({'result': value}), value == None and 404 or 200
    def post(self, guild_id, item):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
        
        post_data: dict = request.get_json()
        value = post_data.get('value')

        curr: list = guild.config.get(item)
        
        if curr == None:
            curr = []
            guild.config[item] = curr
        exists = False
        jval = encoder.encode(value)
        for i in curr:
            if type(value) is dict:
                if encoder.encode(i) == jval:
                    exists = True
                    break
            else:
                if i == value:
                    exists = True
                    break
        if exists:
            return jsonify({'message': 'Value already exists in key'}), 400
        else:
            curr.append(value)

        guild.config[item] = curr

        db.session.add(guild)
        db.session.commit()
        return jsonify({'message': 'Value added'}), 201
    def delete(self, guild_id, item):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
        
        post_data: dict = request.get_json()
        value = post_data.get('value')

        curr: list = guild.config.get(item)
        
        if curr == None:
            curr = []
            guild.config[item] = curr
        removed = False
        jval = encoder.encode(value)
        for i in curr:
            if type(value) is dict:
                if encoder.encode(i) == jval:
                    removed = True
                    curr.remove(i)
                    break
            else:
                if i == value:
                    removed = True
                    curr.remove(i)
                    break
        if not removed:
            return jsonify({'message': 'Not found'}), 404

        guild.config[item] = curr

        db.session.add(guild)
        db.session.commit()
        return jsonify({'message': 'Value removed'}), 204
    def patch(self, guild_id, item):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
        
        post_data: dict = request.get_json()
        value = post_data.get('value')
        
        guild.config[item] = value

        db.session.add(guild)
        db.session.commit()
        return jsonify({'message': 'Success'}), 200

guilds_blueprint.add_url_rule('/userinfo/<guild_id>/<user_id>', view_func=UserInfoResource.as_view('userinfo_guildscope'))
guilds_blueprint.add_url_rule('/getguilduser/<guild_id>/<user_id>', view_func=GetGuildUser.as_view('getguilduser'))
guilds_blueprint.add_url_rule('/getguilduser/<guild_id>/<user_id>/xp', view_func=UpdateGuildUserXP.as_view('updateguilduserxp'))
guilds_blueprint.add_url_rule('/guilddata/<guild_id>', view_func=GuildData.as_view('guilddata'))
guilds_blueprint.add_url_rule('/guilddata/<guild_id>/cfg/<item>', view_func=GuildConfig.as_view('guildconfig'))
guilds_blueprint.add_url_rule('/rankcard/<guild_id>/<user_id>', view_func=RankCardAPI.as_view('rankcard'))