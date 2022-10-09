import hashlib
import random
import string
import jwt
import requests

from json import JSONEncoder
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, client, db
from project.helpers import user_evaluator, verif_token
from project.helpers.Cache import Cache
from project.server.models import Guild, GuildUser
from sqlalchemy_json import TrackedDict

encoder = JSONEncoder()
verification_blueprint = Blueprint('verification', __name__)
verify_cache = Cache(60 * 10) # The cache lasts about as long as a token does

class Role():
    """Fake role class because for some ungodly reason the role functions expect a god damn object with an id"""

    id: int

    def __init__(self, id: int):
        self.id = id

class VerifyUser(MethodView):
    """ User Verification Resource """
    def get(self, t):
        t = verify_cache.get(t)
        if t == None:
            return 'Bad request', 403

        try:
            token = verif_token.decode_token(t)

            guild = client.get_server(token.guild_id)
            user = client.get_user(token.user_id)

            return jsonify({
                'guild_id': token.guild_id,
                'guild_name': guild.name,
                'guild_avatar': guild.avatar.aws_url,
                'user_id': user.id,
                'user_name': user.name,
                'user_avatar': user.avatar.aws_url,
            }), 200
        except jwt.ExpiredSignatureError:
            return jsonify({
                'message': 'Verification code expired, please generate a new one using /verify'
            }), 400
        except jwt.InvalidTokenError:
            return jsonify({
                'message': 'Invalid verification code, please generate one using /verify'
            }), 400

    async def post(self, t):
        link = t
        t = verify_cache.get(t)
        if t == None:
            return 'Bad request', 403
        verify_cache.remove(link)
        post_data = request.get_json()
        browser_id = post_data.get('bi') or request.cookies.get('a')
        using_vpn = (post_data.get('v') or request.cookies.get('b')) != '0'

        try:
            token = verif_token.decode_token(t)
            hashed_ip = hashlib.sha512(request.environ.get('HTTP_X_REAL_IP', request.remote_addr).encode('utf-8')).hexdigest()

            guild: Guild | None = Guild.query.filter_by(guild_id = token.guild_id).first()

            verification_channel = guild.config.get('verification_channel')
            logs_channel = guild.config.get('logs_channel')

            verified_role = guild.config.get('verified_role')
            unverified_role = guild.config.get('unverified_role')

            user: GuildUser | None = GuildUser.query.filter_by(guild_id = token.guild_id, user_id = token.user_id).first()
            if user is None:
                # Create a user profile
                user = GuildUser(token.guild_id, token.user_id, hashed_ip, browser_id, using_vpn, jsonify(token.connections))

                db.session.add(user)
                db.session.commit()
            else:
                # Update all of the currently stored ids and statuses
                cur_bid = user.browser_id
                cur_vpn = user.using_vpn
                cur_ip = user.hashed_ip
                cur_con = user.connections

                user.browser_id = browser_id
                user.using_vpn = using_vpn
                user.hashed_ip = hashed_ip
                user.connections = jsonify(token.connections)

                # Only update the database if there was a change
                if cur_bid != browser_id or cur_vpn != using_vpn or cur_ip != hashed_ip or cur_con != user.connections:
                    db.session.add(user)
                    db.session.commit()
                
                if user.bypass_verification:
                    # Bot-related process
                    try:
                        guilded_user = await client.fetch_user(token.user_id)
                        await guilded_user.send(f'Welcome to {client.get_server(token.guild_id).name}, {guilded_user.name}!')
                    except Exception:
                        print('Could not DM user about successful verification.')
                    if logs_channel is not None:
                        channel = await client.fetch_channel(logs_channel)
                        try:
                            channel.send(
                                embed=user_evaluator.generate_embed(
                                    await user_evaluator.evaluate_user(token.guild_id, token.user_id, encoder.encode(token.connections)),
                                    True
                                )
                            )
                        except Exception as e:
                            print(f'Logs channel exists for server {token.guild_id} but failed to send: {str(e)}')
                    member = client.get_server(token.guild_id).get_member(token.user_id)
                    if verified_role is not None:
                        try:
                            requests.put(f'https://www.guilded.gg/api/v1/servers/{token.guild_id}/members/{token.user_id}/roles/{verified_role}',
                            headers={
                                'Authorization': f'Bearer {app.config.get("GUILDED_BOT_TOKEN")}'
                            })
                        except Exception as e:
                            print(f'Verified role exists for server {token.guild_id} but failed to give: {str(e)}')
                    if unverified_role is not None:
                        try:
                            requests.delete(f'https://www.guilded.gg/api/v1/servers/{token.guild_id}/members/{token.user_id}/roles/{unverified_role}',
                            headers={
                                'Authorization': f'Bearer {app.config.get("GUILDED_BOT_TOKEN")}'
                            })
                        except Exception as e:
                            print(f'Unverified role exists for server {token.guild_id} but failed to remove: {str(e)}')
                    # End of bot-related process

                    return jsonify({
                        'message': 'Verification success!'
                    }), 200
            
            # Compare IP hash against database of banned users in this guild that aren't the user being verified
            matching_hashes = db.session.query(GuildUser).filter(
                GuildUser.hashed_ip == hashed_ip,
                GuildUser.guild_id == token.guild_id,
                GuildUser.user_id != token.user_id,
                GuildUser.is_banned == True
            ).all()

            if len(matching_hashes) > 0: # We found another user who was banned with a matching IP, reject them
                if logs_channel is not None:
                    channel = await client.fetch_channel(logs_channel)
                    try:
                        channel.send(
                            embed=user_evaluator.generate_embed(
                                await user_evaluator.evaluate_user(token.guild_id, token.user_id, encoder.encode(token.connections)),
                                False
                            )
                        )
                    except Exception as e:
                        print(f'Logs channel exists for server {token.guild_id} but failed to send: {str(e)}')
                return jsonify({
                    'message': 'You are forbidden from entering this server'
                }), 403
            
            # Compare browser id against database of banned users in this guild that aren't the user being verified
            # If the browser id is not empty
            if browser_id != '' and browser_id != None:
                matching_bids = db.session.query(GuildUser).filter(
                    GuildUser.browser_id == browser_id,
                    GuildUser.guild_id == token.guild_id,
                    GuildUser.user_id != token.user_id,
                    GuildUser.is_banned == True
                ).all()

                if len(matching_bids) > 0: # We found another user who was banned with a matching browser id, reject them
                    if logs_channel is not None:
                        channel = await client.fetch_channel(logs_channel)
                        try:
                            channel.send(
                                embed=user_evaluator.generate_embed(
                                    await user_evaluator.evaluate_user(token.guild_id, token.user_id, encoder.encode(token.connections)),
                                    False
                                )
                            )
                        except Exception as e:
                            print(f'Logs channel exists for server {token.guild_id} but failed to send: {str(e)}')
                    return jsonify({
                        'message': 'You are forbidden from entering this server' # No need to reveal how they were identified
                    }), 403
            
            # Bot-related process
            try:
                guilded_user = await client.fetch_user(token.user_id)
                await guilded_user.send(f'Welcome to {client.get_server(token.guild_id).name}, {guilded_user.name}!')
            except Exception:
                print('Could not DM user about successful verification.')
            if logs_channel is not None:
                channel = await client.fetch_channel(logs_channel)
                try:
                    channel.send(
                        embed=user_evaluator.generate_embed(
                            await user_evaluator.evaluate_user(token.guild_id, token.user_id, encoder.encode(token.connections)),
                            True
                        )
                    )
                except Exception as e:
                    print(f'Logs channel exists for server {token.guild_id} but failed to send: {str(e)}')
            member = client.get_server(token.guild_id).get_member(token.user_id)
            if verified_role is not None:
                try:
                    requests.put(f'https://www.guilded.gg/api/v1/servers/{token.guild_id}/members/{token.user_id}/roles/{verified_role}',
                    headers={
                        'Authorization': f'Bearer {app.config.get("GUILDED_BOT_TOKEN")}'
                    })
                except Exception as e:
                    print(f'Verified role exists for server {token.guild_id} but failed to give: {str(e)}')
            if unverified_role is not None:
                try:
                    requests.delete(f'https://www.guilded.gg/api/v1/servers/{token.guild_id}/members/{token.user_id}/roles/{unverified_role}',
                    headers={
                        'Authorization': f'Bearer {app.config.get("GUILDED_BOT_TOKEN")}'
                    })
                except Exception as e:
                    print(f'Unverified role exists for server {token.guild_id} but failed to remove: {str(e)}')
            # End of bot-related process

            return jsonify({
                'message': 'Verification success!'
            }), 200
        except jwt.ExpiredSignatureError:
            return jsonify({
                'message': 'Verification code expired, please generate a new one using /verify'
            }), 400
        except jwt.InvalidTokenError:
            return jsonify({
                'message': 'Invalid verification code, please generate one using /verify'
            }), 400

class GetGuildUser(MethodView):
    def get(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        db_user: GuildUser | None = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        if db_user:
            return jsonify({
                'guild_id': db_user.guild_id,
                'user_id': db_user.user_id,
                'browser_id': db_user.browser_id,
                'hashed_ip': db_user.hashed_ip,
                'is_banned': db_user.is_banned,
                'using_vpn': db_user.using_vpn,
                'bypass_verification': db_user.bypass_verification,
                'connections': db_user.connections
            }), 200
        else:
            return 'Not found', 404

class GuildData(MethodView):
    def get(self, guild_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

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
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
        
        for key in post_data.keys():
            try:
                guild[key] = post_data.get(key)
            except Exception:
                print(f'[WARNING]: "{key}" is not a valid member of the Guild model!')
                # Make sure that a failure doesn't lead to a 500 error and notifies the logs

        db.session.add(guild)
        db.session.commit()

        return jsonify(guild), 200
    def delete(self, guild_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

        if guild:
            db.session.delete(guild)
            db.session.commit()

            return jsonify({'message': 'Deleted', 'original_guild': jsonify(guild)}), 204

class ShortVerifyLink(MethodView):
    def post(self):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data = request.get_json()
        token = post_data.get('token')

        link = ''.join(random.choices(string.ascii_letters + '_-' + string.digits, k=32))
        verify_cache.set(link, token)

        return jsonify({'result': link}), 201

class GuildConfig(MethodView):
    def get(self, guild_id, item):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

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
        
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

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
        
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

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
        print(jval)
        for i in curr:
            if type(value) is dict:
                print(encoder.encode(i))
                if encoder.encode(i) == jval:
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
        
        guild: Guild | None = Guild.query.filter_by(guild_id = guild_id).first()

        if guild == None:
            guild = Guild(guild_id)
        
        post_data: dict = request.get_json()
        value = post_data.get('value')
        
        guild.config[item] = value

        db.session.add(guild)
        db.session.commit()
        return jsonify({'message': 'Success'}), 200

class VerifyBypass(MethodView):
    def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data: dict = request.get_json()
        value = post_data.get('value')

        db_user: GuildUser | None = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        if db_user:
            db_user.bypass_verification = value is True

            db.session.add(db_user)
            db.session.commit()

            return jsonify({'message': 'Success'}), 200
        return jsonify({'message': 'Not found'}), 404

verification_blueprint.add_url_rule('/verify/<t>', view_func=VerifyUser.as_view('verify'))
verification_blueprint.add_url_rule('/getguilduser/<guild_id>/<user_id>', view_func=GetGuildUser.as_view('getguilduser'))
verification_blueprint.add_url_rule('/verify/shorten', view_func=ShortVerifyLink.as_view('shorten_verify_link'))
verification_blueprint.add_url_rule('/guilddata/<guild_id>', view_func=GuildData.as_view('guilddata'))
verification_blueprint.add_url_rule('/guilddata/<guild_id>/cfg/<item>', view_func=GuildConfig.as_view('guildconfig'))
verification_blueprint.add_url_rule('/verify/bypass/<guild_id>/<user_id>', view_func=VerifyBypass.as_view('verifybypass'))