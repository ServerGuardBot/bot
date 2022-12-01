import aiohttp

from datetime import datetime, timedelta
from json import JSONDecoder, JSONEncoder
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, bot_api, db
from project.server.models import Guild, GuildUser, UserInfo
from project.helpers.premium import get_user_premium_status
from guilded import SocialLinkType, http

encoder = JSONEncoder()
decoder = JSONDecoder()

guilds_blueprint = Blueprint('guilds', __name__)

async def get_user_info(guild_id: str, user_id: str):
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
            guilds: list = (await bot_api.request(http.Route('GET', f'/users/{user_id}/teams', override_base=http.Route.USER_BASE))).get('teams', [])
        except:
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

class UserInfoResource(MethodView):
    """ User Info Resource """
    async def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        bot_api.session = aiohttp.ClientSession()

        user_info: UserInfo = await get_user_info(guild_id, user_id)

        await bot_api.session.close()

        return jsonify({
            'id': user_info.user_id,
            'name': user_info.name,
            'avatar': user_info.avatar,
            'guilded_data': user_info.guilded_data,
            'created_at': user_info.created_at,
            'connections': encoder.encode(user_info.connections or {}),
            
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
        
        bot_api.session = aiohttp.ClientSession()

        user_info: UserInfo = await get_user_info(guild_id, user_id)

        await bot_api.session.close()

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
guilds_blueprint.add_url_rule('/guilddata/<guild_id>', view_func=GuildData.as_view('guilddata'))
guilds_blueprint.add_url_rule('/guilddata/<guild_id>/cfg/<item>', view_func=GuildConfig.as_view('guildconfig'))