import hashlib
import random
import string
from typing import Optional
import jwt
import requests
import base64

from datetime import datetime
from json import JSONDecoder, JSONEncoder
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, BotAPI, db, get_shared_state
from project.helpers import user_evaluator, verif_token
from project.helpers.Cache import Cache
from project.helpers.images import *
from project.helpers.premium import get_user_premium_status
from project.helpers.verify_browseragent import verify_browseragent
from project.server.models import Guild, GuildUser, UserInfo
from project.server.api.guilds import get_user_info
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from guilded import Embed

shared_dict, shared_lock = get_shared_state(port=35792, key=b"verification")
shared_ip_cache, shared_ip_lock = get_shared_state(port=35793, key=b"verification_ip")

encoder = JSONEncoder()
verification_blueprint = Blueprint('verification', __name__)

decoder = JSONDecoder()

verify_cache = Cache(60 * 10, shared_dict)
ip_cache = Cache(300, shared_ip_cache)

tor_exit_nodes = []
last_tor_node_get = 0

def get_tor_exit_nodes():
    global last_tor_node_get
    if abs(last_tor_node_get - datetime.now().timestamp()) > 60 * 30:
        last_tor_node_get = datetime.now().timestamp()
        req = requests.get('https://www.dan.me.uk/torlist/?exit')
        list = req.content
        tor_exit_nodes.clear()
        for line in list.splitlines():
            tor_exit_nodes.append(str(line))
    return tor_exit_nodes

async def send_embed(channel_id, embed: Embed):
    with BotAPI() as bot_api:
        return await bot_api.create_channel_message(channel_id, payload={
            'embeds': [embed.to_dict()]
        })

def validate_turnstile(turnstile_response: str, user_ip: Optional[str]):
    res = requests.post(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        data={
            'secret': app.config.get('TURNSTILE_SECRET'),
            'response': turnstile_response,
            'remoteip': user_ip
        }
    )
    
    return res.status_code == 200

class VerifyUser(MethodView):
    """ User Verification Resource """
    async def get(self, t):
        t = verify_cache.get(t)
        if t == None:
            return jsonify({
                    'message': 'Bad request.'
                }), 403
        
        with BotAPI() as bot_api:
            try:
                token = verif_token.decode_token(t)

                guild = (await bot_api.get_server(token.guild_id)).get('server')
                user = (await bot_api.get_member(token.guild_id, token.user_id)).get('member')
                db_guild: Guild = Guild.query.filter_by(guild_id = token.guild_id).first()

                return jsonify({
                    'guild_id': token.guild_id,
                    'guild_name': guild.get('name'),
                    'guild_avatar': guild.get('avatar') or IMAGE_DEFAULT_AVATAR,
                    'user_id': token.user_id,
                    'user_name': user.get('user').get('name'),
                    'user_avatar': user.get('user').get('avatar') or IMAGE_DEFAULT_AVATAR,
                    'admin_contact': db_guild.config.get('admin_contact')
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
            return jsonify({
                    'message': 'Bad request.'
                }), 403
        verify_cache.remove(link)
        if request.content_type == 'text/plain':
            body = request.get_data(as_text=True)
            enc = base64.b64decode(body)
            cipher = AES.new(app.config.get('SITE_ENCRYPTION', 'idk').encode('utf-8'), AES.MODE_ECB)
            try:
                post_data = decoder.decode(unpad(cipher.decrypt(enc), 16).decode('utf-8'))
            except Exception as e:
                return jsonify({
                    'message': 'Bad request.'
                }), 403
        else:
            return jsonify({
                'message': 'Your client is using an outdated version of the verification page, please Press Control + Shift + R and try verifying again.'
            }), 403
        browser_id = post_data.get('bi')
        using_vpn = post_data.get('v') != '0'
        turnstile = post_data.get('cf')

        with BotAPI() as bot_api:
            try:
                token = verif_token.decode_token(t)
                user_ip = request.headers.get('cf-connecting-ip', request.environ.get('HTTP_X_REAL_IP', request.remote_addr))
                hashed_ip = hashlib.sha512(user_ip.encode('utf-8')).hexdigest()

                db_guild: dict = (await bot_api.get_server(token.guild_id)).get('server')
                guild: Guild = Guild.query.filter_by(guild_id = token.guild_id).first()

                premium_status = await get_user_premium_status(db_guild.get('ownerId'))

                block_tor = guild.config.get('block_tor')
                logs_channel = guild.config.get('verify_logs_channel', guild.config.get('logs_channel'))

                verified_role = guild.config.get('verified_role')
                unverified_role = guild.config.get('unverified_role')

                user: GuildUser = GuildUser.query.filter_by(guild_id = token.guild_id, user_id = token.user_id).first()
                if user is None:
                    # Create a user profile
                    user = GuildUser(token.guild_id, token.user_id, hashed_ip or "", browser_id or "", using_vpn or False, encoder.encode(token.connections))

                    db.session.add(user)
                    db.session.commit()
                else:
                    # Update all of the currently stored ids and statuses
                    cur_bid = user.browser_id
                    cur_vpn = user.using_vpn
                    cur_ip = user.hashed_ip
                    cur_con = user.connections

                    user.browser_id = browser_id or ""
                    user.using_vpn = using_vpn or False
                    user.hashed_ip = hashed_ip or ""
                    user.connections = encoder.encode(token.connections)

                    # Only update the database if there was a change
                    if cur_bid != browser_id or cur_vpn != using_vpn or cur_ip != hashed_ip or cur_con != user.connections:
                        db.session.add(user)
                        db.session.commit()
                
                user_info: UserInfo = await get_user_info(token.guild_id, token.user_id)

                if turnstile is not None:
                    is_turnstile_valid = validate_turnstile(turnstile, user_ip)

                    if is_turnstile_valid is False:
                        # Failed cloudflare turnstile, reject and log it
                        if logs_channel is not None:
                            await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                                await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                                False,
                                "Turnstile Challenge Failed"
                            ))
                        return jsonify({
                            'message': 'Failed turnstile challenge.'
                        }), 403
                else:
                    if app.config.get('ENFORCE_TURNSTILE', False):
                        # Missing cloudflare turnstile response, reject and log it
                        if logs_channel is not None:
                            await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                                await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                                False,
                                "Missing Turnstile Response"
                            ))
                        return jsonify({
                            'message': 'Missing turnstile response.'
                        }), 403

                if user.bypass_verification:
                    # Bot-related process
                    if logs_channel is not None:
                        await send_embed(logs_channel, user_evaluator.generate_embed(
                            await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                            True
                        ))
                    if verified_role is not None:
                        try:
                            await bot_api.assign_role_to_member(token.guild_id, token.user_id, verified_role)
                        except Exception as e:
                            print(f'Verified role exists for server {token.guild_id} but failed to give: {str(e)}')
                    if unverified_role is not None:
                        try:
                            await bot_api.remove_role_from_member(token.guild_id, token.user_id, unverified_role)
                        except Exception as e:
                            print(f'Unverified role exists for server {token.guild_id} but failed to remove: {str(e)}')
                    # End of bot-related process

                    return jsonify({
                        'message': 'Verification success!'
                    }), 200
                
                if not verify_browseragent(request.user_agent.string):
                    # Possibly not a browser, reject it
                    if logs_channel is not None:
                        await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                            await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                            False,
                            "None-Browser Attempt"
                        ))
                    return jsonify({
                        'message': 'Please use a browser to verify with us!'
                    }), 403

                ip = request.headers.get('cf-connecting-ip', request.environ.get('HTTP_X_REAL_IP', request.remote_addr))
                cached_ip = ip_cache.get(f'{token.guild_id}/{ip}')
                if cached_ip is None:
                    cached_ip = 1
                ip_cache.set(f'{token.guild_id}/{ip}', cached_ip + 1)

                if block_tor is 1:
                    exit_nodes = get_tor_exit_nodes()
                    if ip in exit_nodes:
                        # Reject due to tor detected
                        if logs_channel is not None:
                            await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                                await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                                False,
                                "Tor Block"
                            ))

                        return jsonify({
                            'message': 'This server blocks verification from tor exit nodes'
                        }), 403

                if cached_ip >= 3:
                    # Reject due to too many verification requests
                    if logs_channel is not None:
                        await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                            await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                            False,
                            "Rate Limited"
                        ))
                    return jsonify({
                        'message': 'You are verifying too often in this server.'
                    }), 403

                if premium_status > 0:
                    # Do an advanced proxy check
                    proxy_request = requests.get(f'https://proxycheck.io/v2/{ip}?key={app.config.get("PROXYCHECK_KEY")}&vpn=1&risk=1')
                    if proxy_request.status_code == 200:
                        data = proxy_request.json().get(ip, {
                            'proxy': 'no',
                            'risk': 0
                        })
                        using_vpn = data.get('proxy') == 'yes'
                        risk = data.get('risk') or 0
                        if risk >= 75:
                            # Block the verification
                            if logs_channel is not None:
                                await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                                    await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                                    False,
                                    "[APC] Dangerous IP"
                                ))
                            return jsonify({
                                'message': 'Dangerous IP address identified by Advanced Proxy Check'
                            }), 403
                
                # Compare their socials against database of banned users in this guild that aren't the user being verified
                socials = decoder.decode(user_info.connections)
                if socials.get('roblox') or socials.get('twitter') or socials.get('youtube') or socials.get('steam'):
                    banned_users = db.session.query(GuildUser.user_id) \
                        .filter(GuildUser.guild_id == token.guild_id) \
                        .filter(GuildUser.user_id != token.user_id) \
                        .filter(GuildUser.is_banned == True)

                    matching_socials = db.session.query(UserInfo)
                    
                    if user_info.roblox != None:
                        matching_socials = matching_socials.filter(UserInfo.roblox == user_info.roblox)
                    if user_info.steam != None:
                        matching_socials = matching_socials.filter(UserInfo.steam == user_info.steam)
                    if user_info.twitter != None:
                        matching_socials = matching_socials.filter(UserInfo.twitter == user_info.twitter)
                    if user_info.youtube != None:
                        matching_socials = matching_socials.filter(UserInfo.youtube == user_info.youtube)

                    matching_socials = matching_socials.filter(UserInfo.user_id.in_(banned_users))

                    if len(matching_socials.all()) > 0:
                        if logs_channel is not None:
                            await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                                await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                                False,
                                "Account Check"
                            ))
                        return jsonify({
                            'message': 'Your account is linked to a previously banned member of this server'
                        }), 403

                # Compare IP hash against database of banned users in this guild that aren't the user being verified
                matching_hashes = db.session.query(GuildUser).filter(
                    GuildUser.hashed_ip == hashed_ip,
                    GuildUser.guild_id == token.guild_id,
                    GuildUser.user_id != token.user_id,
                    GuildUser.is_banned == True
                ).all()

                if len(matching_hashes) > 0: # We found another user who was banned with a matching IP, reject them
                    if logs_channel is not None:
                        await send_embed(logs_channel, user_evaluator.generate_embed(
                            await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                            False,
                            "IP Check"
                        ))
                    return jsonify({
                        'message': 'Your IP is linked to a previously banned member of this server'
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
                            await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                                await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                                False,
                                "IP Check"
                            ))
                        return jsonify({
                            'message': 'Your IP is linked to a previously banned member of this server'
                        }), 403

                # Bot-related process
                if logs_channel is not None:
                    await send_embed(logs_channel, embed=user_evaluator.generate_embed(
                        await user_evaluator.evaluate_user(token.guild_id, token.user_id, user_info.connections),
                        True
                    ))
                if verified_role is not None:
                    try:
                        await bot_api.assign_role_to_member(token.guild_id, token.user_id, verified_role)
                    except Exception as e:
                        print(f'Verified role exists for server {token.guild_id} but failed to give: {str(e)}')
                if unverified_role is not None:
                    try:
                        await bot_api.remove_role_from_member(token.guild_id, token.user_id, unverified_role)
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

class VerifyBypass(MethodView):
    def patch(self, guild_id, user_id):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data: dict = request.get_json()
        value = post_data.get('value')

        db_user: GuildUser = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        if db_user:
            db_user.bypass_verification = value is True

            db.session.add(db_user)
            db.session.commit()

            return jsonify({'message': 'Success'}), 200
        return jsonify({'message': 'Not found'}), 404

class VerifySetUserBanned(MethodView):
    def patch(self, guild_id: str, user_id: str):
        auth = request.headers.get('authorization')

        if auth != app.config.get('SECRET_KEY'):
            return 'Forbidden.', 403
        
        post_data: dict = request.get_json()
        value = post_data.get('value')

        db_user: GuildUser = GuildUser.query.filter_by(guild_id = guild_id, user_id = user_id).first()

        if db_user is None:
            db_user = GuildUser(guild_id, user_id)

        db_user.is_banned = value is True

        db.session.add(db_user)
        db.session.commit()

        return jsonify({'message': 'Success'}), 200

verification_blueprint.add_url_rule('/verify/<t>', view_func=VerifyUser.as_view('verify'))
verification_blueprint.add_url_rule('/verify/shorten', view_func=ShortVerifyLink.as_view('shorten_verify_link'))
verification_blueprint.add_url_rule('/verify/bypass/<guild_id>/<user_id>', view_func=VerifyBypass.as_view('verifybypass'))
verification_blueprint.add_url_rule('/verify/setbanned/<guild_id>/<user_id>', view_func=VerifySetUserBanned.as_view('verifysetbanned'))
