from datetime import datetime
from threading import Thread
from dotenv import load_dotenv
from guilded import MessageEvent, MessageUpdateEvent, MessageDeleteEvent, MessageReactionAddEvent, MessageReactionRemoveEvent, MemberJoinEvent, \
    MemberRemoveEvent, BanCreateEvent, BanDeleteEvent, BulkMemberRolesUpdateEvent, ForumTopicCreateEvent, ForumTopicDeleteEvent, \
    ForumTopicUpdateEvent, ServerChannelCreateEvent, ServerChannelDeleteEvent, ServerChannelUpdateEvent, ForumTopicLockEvent, \
    ForumTopicUnlockEvent, ForumTopicPinEvent, ForumTopicUnpinEvent, ForumTopicReplyCreateEvent, ForumTopicReplyDeleteEvent, \
    ForumTopicReplyUpdateEvent, AnnouncementReplyCreateEvent, AnnouncementReplyUpdateEvent, AnnouncementReplyDeleteEvent, \
    RoleCreateEvent, RoleDeleteEvent, RoleUpdateEvent, http
from guilded.ext import commands
from guilded.http import Route
from nsfw_detector import predict as nsfw_detect
from zipfile import ZipFile
from project.helpers.Cache import Cache
from project.helpers.embeds import *
from bs4 import BeautifulSoup
from project.helpers.translator import translate

from project.modules.base import Module

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

from multiprocessing import Lock
from multiprocessing.managers import AcquirerProxy, BaseManager, DictProxy

load_dotenv()

import project.server
import project.modules
import project.config

import asyncio
import io
import importlib
import logging
import inspect
import os
import sys
import ssl
import requests
import csv
import aiohttp
import threading

ssl_context = ssl.create_default_context()
# Sets up old and insecure TLSv1.
ssl_context.options &= (
    ~getattr(ssl, "OP_NO_TLSv1_3", 0)
    & ~ssl.OP_NO_TLSv1_2
    & ~ssl.OP_NO_TLSv1_1
)
ssl_context.minimum_version = ssl.TLSVersion.TLSv1

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

managers = []

def get_shared_state(host="127.0.0.1", port=35791, key=b"totally_secret"):
    shared_dict = {}
    shared_lock = Lock()
    manager = BaseManager((host, port), key)
    manager.register("get_dict", lambda: shared_dict, DictProxy)
    manager.register("get_lock", lambda: shared_lock, AcquirerProxy)
    managers.append(manager)
    try:
        manager.get_server()
        manager.start()
    except OSError:  # Address already in use
        manager.connect()
    return manager.get_dict(), manager.get_lock()

def get_py_files():
    py_files = [py_file for py_file in os.listdir(os.path.join(__location__, 'modules')) if os.path.splitext(py_file)[1] == '.py']
    
    return py_files

app = Flask(__name__.split('.')[0])

app_settings = os.getenv(
	'CURR_ENV',
	'DevelopmentConfig'
)
configs = {
    'DevelopmentConfig': project.config.DevelopmentConfig,
    'TestingConfig': project.config.TestingConfig,
    'ProductionConfig': project.config.ProductionConfig
}
app.config.from_object(configs[app_settings])

bot_config: project.config.BaseConfig = configs[app_settings] # A custom copy of the config for the bot side of things to access

class BotAPI():
    api = None
    def __init__(self):
        pass

    def __enter__(self):
        api = http.HTTPClient()
        api.token = app.config.get('GUILDED_BOT_TOKEN')
        api.session = aiohttp.ClientSession()
        self.api = api
        return api
    
    def __exit__(self, type, value, traceback):
        loop = asyncio.get_running_loop()
        loop.create_task(self.api.session.close())
        del self.api

nsfw_model = None
nsfw_loaded = False
def load_nsfw():
    print('Loading NSFW Model')
    global nsfw_model
    nsfw_model = nsfw_detect.load_model(app.config.get('PROJECT_ROOT') + '/project/ml_models/nsfw.h5')
    global nsfw_loaded
    nsfw_loaded = True
    print('NSFW Model Has Been Loaded')

async def get_nsfw_model():
    while nsfw_loaded is False:
        await asyncio.sleep(.1)
    return nsfw_model

if not os.getenv('MIGRATING_DB', '0') == '1':
    nsfw_thread = Thread(target=load_nsfw)
    nsfw_thread.start()

db = SQLAlchemy(app)
migrate = Migrate(app, db)
cors = CORS(app, send_wildcard=True, origins=["https://serverguard.xyz", "http://localhost:8001"], supports_credentials=True)

guild_cache = Cache()

class BotClient(commands.Bot):
    config = app.config
    message_listeners: list = []
    join_listeners: list = []
    leave_listeners: list = []
    message_update_listeners: list = []
    message_delete_listeners: list = []
    topic_create_listeners: list = []
    topic_update_listeners: list = []
    topic_delete_listeners: list = []
    topic_pin_listeners: list = []
    topic_unpin_listeners: list = []
    topic_lock_listeners: list = []
    topic_unlock_listeners: list = []
    topic_reply_create_listeners: list = []
    topic_reply_update_listeners: list = []
    topic_reply_delete_listeners: list = []
    member_role_update_listeners: list = []
    ban_create_listeners: list = []
    ban_delete_listeners: list = []
    reaction_add_listeners: list = []
    reaction_remove_listeners: list = []
    channel_create_listeners: list = []
    channel_update_listeners: list = []
    channel_delete_listeners: list = []
    announcement_reply_create_listeners: list = []
    announcement_reply_update_listeners: list = []
    announcement_reply_delete_listeners: list = []
    role_create_listeners: list = []
    role_update_listeners: list = []
    role_delete_listeners: list = []

client = BotClient('/', experimental_event_style=True)

malicious_urls = {}
guilded_paths = []
current_status = -1
server_count = 0

def load_malicious_url_db():
    global malicious_urls
    try:
        req = requests.get('https://urlhaus.abuse.ch/downloads/csv/')
        zip = ZipFile(io.BytesIO(req.content))
        item = zip.open('csv.txt')
        reader = csv.reader(io.TextIOWrapper(item, 'utf-8'))
        malicious_urls.clear()
        for row in reader:
            if len(row) < 2 or ('id' in row[0]):
                continue
            url = row[2]
            threat = row[5]
            malicious_urls[url] = threat
    except Exception as e:
        print('WARNING: urlhaus API down, malicious URLs not being reloaded.')

async def alternate_status():
    global current_status
    global server_count
    current_status += 1
    payload = None
    if current_status > 1:
        current_status = 0
    if current_status == 0:
        payload = {
            'content': '/help • serverguard.xyz',
            'emoteId': 1487999,
        }
    elif current_status == 1:
        payload = {
            'content': f'Protecting {"{:,}".format(server_count)} Servers',
            'emoteId': 1904514,
        }
    if payload is not None:
        await client.http.request(Route('PUT', '/users/@me/status'), json=payload)

def post_thread(*args, **kwargs):
    def run():
        requests.post(*args, **kwargs)
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

async def run_hourly_loop():
    while True:
        print('Running hourly loop')
        post_thread('http://localhost:5000/analytics/servers', headers={
            'authorization': bot_config.SECRET_KEY
        })
        post_thread('http://localhost:5000/analytics/users', headers={
            'authorization': bot_config.SECRET_KEY
        })
        try:
            global guilded_paths
            guilded_paths.clear()
            req = requests.get('https://www.guilded.gg/sitemap_landing.xml')
            soup = BeautifulSoup(req.text, "xml")
            for tag in soup.find_all('url'):
                loc = tag.loc
                if loc is not None:
                    guilded_paths.append(loc.string[23:].lower())
        except Exception as e:
            print(f'WARNING: failed to get Guilded official paths because "{e}"')
        await asyncio.sleep(60 * 60) # Only runs once an hour

async def run_url_db_dl():
    while True:
        await asyncio.sleep(60 * 10)
        print('Running Malicious URL DB Download')
        load_malicious_url_db()

async def run_bot_loop():
    global server_count
    while True:
        await asyncio.sleep(60)
        print('Running Bot Loop')
        post_thread('http://localhost:5000/moderation/expirestatuses', headers={
            'authorization': bot_config.SECRET_KEY
        })
        post_thread('http://localhost:5000/giveaways/check', headers={
            'authorization': bot_config.SECRET_KEY
        })
        try:
            server_request = requests.get('http://localhost:5000/analytics/servers/count', headers={
                'authorization': bot_config.SECRET_KEY
            })
            if server_request.ok:
                server_count = server_request.json().get('value', server_count)
            await alternate_status()
        except Exception as e:
            print(f'WARNING: failed to alternate status because "{e}"')

async def run_feed_loop():
    while True:
        print('Running Feed Loop')
        post_thread('http://localhost:5000/feeds/check', headers={
            'authorization': bot_config.SECRET_KEY
        })
        await asyncio.sleep(60 * 30)

async def run_cleanup_loop():
    while True:
        print('Running Cleanup Loop')
        post_thread('http://localhost:5000/db/cleanup', headers={
            'authorization': bot_config.SECRET_KEY
        })
        # Try to remove bot from unconfigured servers that are older than 1 week
        # NOTE: Maybe send an automated notice to unconfigured servers a day before removing itself?
        if os.getenv('CLEANUP_SERVERS', 'false').lower() == 'true':
            for server in client.servers:
                print(f'Checking "{server.id}"')
                await asyncio.sleep(0)
                try:
                    guild_data_req = requests.get(f'http://localhost:5000/guilddata/{server.id}', headers={
                        'authorization': bot_config.SECRET_KEY
                    })
                    guild_data: dict = guild_data_req.json()
                    config = guild_data.get('config', {})
                    if len(config) == 0 or (len(config) == 1 and config.get('__cache') != None):
                        me = await server.fetch_member(client.user_id)
                        joined: datetime = me.joined_at
                        diff = datetime.now() - joined
                        if diff.days >= 7:
                            await server.kick(me)
                            del client.servers[server]
                except Exception as e:
                    print(f'Failed to check "{server.id}" for being unconfigured: {e}')
        await asyncio.sleep(60 * 30)

if not os.getenv('MIGRATING_DB', '0') == '1':
    load_malicious_url_db()

tasks_made = False
@client.event
async def on_ready():
    global tasks_made
    await client.wait_until_ready()
    print(f'Logged in as {client.user.name}')
    if not tasks_made:
        print('Created tasks for loops')
        client.loop.create_task(run_bot_loop())
        client.loop.create_task(run_url_db_dl())
        client.loop.create_task(run_feed_loop())
        client.loop.create_task(run_hourly_loop())
        client.loop.create_task(run_cleanup_loop())
        tasks_made = True
    print('Bot ready')

@client.event
async def on_message(event: MessageEvent):
    message = event.message
    server = event.server
    # Replace all mentions that it can in the message with properly parseable formats
    for member in message.user_mentions:
        message.content = message.content.replace(f'@{member.name}', f'<@{member.id}>')
        if member.nick:
            message.content = message.content.replace(f'@{member.nick}', f'<@{member.id}>')
    if server is not None:
        for role_id in message.raw_role_mentions:
            role = await server.getch_role(role_id)
            message.content = message.content.replace(f'@{role.name}', f'<@&{role.id}>')
    for channel_id in message.raw_channel_mentions:
        channel = await message.server.getch_channel(channel_id)
        message.content = message.content.replace(f'#{channel.name}', f'<#{channel.id}>')
    
    user_data_req = requests.get(f'http://localhost:5000/userinfo/{message.server_id}/{message.author_id}', headers={
        'authorization': bot_config.SECRET_KEY
    })

    if user_data_req.status_code == 200:
        message.language = user_data_req.json().get('language', 'en')
    else:
        message.language = 'en'
    
    if message.content.strip() == f'<@{client.user_id}>':
        await message.reply(
            embed=Embed(
                title=await translate(message.language, 'link.support'),
                description=await translate(message.language, "bot.prefix_response", {
                    'member_id': message.author_id,
                    'prefix': '/'
                })
            ) \
                .set_footer(text='Server Guard') \
                .set_thumbnail(url='https://img.guildedcdn.com/UserAvatar/6dc417befe51bbca91b902984f113f89-Small.webp?w=80&h=80')
        )
    
    await client.process_commands(message)
    for callback in client.message_listeners:
        try:
            await callback(message)
        except Exception as e:
            print('Failed to run message listener:', e)

@client.event
async def on_member_join(event: MemberJoinEvent):
    for callback in client.join_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run join listener:', e)

@client.event
async def on_member_remove(event: MemberRemoveEvent):
    for callback in client.leave_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run leave listener:', e)

@client.event
async def on_ban_create(event: BanCreateEvent):
    for callback in client.ban_create_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run ban create listener:', e)

@client.event
async def on_ban_delete(event: BanDeleteEvent):
    for callback in client.ban_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run ban delete listener:', e)

@client.event
async def on_message_update(event: MessageUpdateEvent):
    for callback in client.message_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run message update listener:', e)

@client.event
async def on_message_delete(event: MessageDeleteEvent):
    for callback in client.message_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run message delete listener:', e)

@client.event
async def on_forum_topic_create(event: ForumTopicCreateEvent):
    for callback in client.topic_create_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic delete listener:', e)

@client.event
async def on_forum_topic_update(event: ForumTopicUpdateEvent):
    for callback in client.topic_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic delete listener:', e)

@client.event
async def on_forum_topic_delete(event: ForumTopicDeleteEvent):
    for callback in client.topic_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic delete listener:', e)

@client.event
async def on_forum_topic_pin(event: ForumTopicPinEvent):
    for callback in client.topic_pin_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic pin listener:', e)

@client.event
async def on_forum_topic_unpin(event: ForumTopicUnpinEvent):
    for callback in client.topic_unpin_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic unpin listener:', e)

@client.event
async def on_forum_topic_lock(event: ForumTopicLockEvent):
    for callback in client.topic_lock_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic lock listener:', e)

@client.event
async def on_forum_topic_unlock(event: ForumTopicUnlockEvent):
    for callback in client.topic_unlock_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic unlock listener:', e)

@client.event
async def on_forum_topic_reply_create(event: ForumTopicReplyCreateEvent):
    for callback in client.topic_reply_create_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic reply create listener:', e)

@client.event
async def on_forum_topic_reply_update(event: ForumTopicReplyUpdateEvent):
    for callback in client.topic_reply_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic reply update listener:', e)

@client.event
async def on_forum_topic_reply_delete(event: ForumTopicReplyDeleteEvent):
    for callback in client.topic_reply_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run forum topic reply delete listener:', e)

@client.event
async def on_announcement_reply_create(event: AnnouncementReplyCreateEvent):
    for callback in client.announcement_reply_create_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run announcement reply create listener:', e)

@client.event
async def on_announcement_reply_update(event: AnnouncementReplyUpdateEvent):
    for callback in client.announcement_reply_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run announcement reply update listener:', e)

@client.event
async def on_announcement_reply_delete(event: AnnouncementReplyDeleteEvent):
    for callback in client.announcement_reply_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run announcement reply delete listener:', e)

@client.event
async def on_bulk_member_roles_update(event: BulkMemberRolesUpdateEvent):
    for callback in client.member_role_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run member role update listener:', e)

@client.event
async def on_message_reaction_add(event: MessageReactionAddEvent):
    for callback in client.reaction_add_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run reaction add listener:', e)

@client.event
async def on_message_reaction_remove(event: MessageReactionRemoveEvent):
    for callback in client.reaction_remove_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run reaction remove listener:', e)

@client.event
async def on_server_channel_create(event: ServerChannelCreateEvent):
    for callback in client.channel_create_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run channel create listener:', e)

@client.event
async def on_server_channel_update(event: ServerChannelUpdateEvent):
    for callback in client.channel_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run channel update listener:', e)

@client.event
async def on_server_channel_delete(event: ServerChannelDeleteEvent):
    for callback in client.channel_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run channel delete listener:', e)

@client.event
async def on_role_create(event: RoleCreateEvent):
    for callback in client.role_create_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run role create listener:', e)

@client.event
async def on_role_update(event: RoleUpdateEvent):
    for callback in client.role_update_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run role update listener:', e)

@client.event
async def on_role_delete(event: RoleDeleteEvent):
    for callback in client.role_delete_listeners:
        try:
            await callback(event)
        except Exception as e:
            print('Failed to run role delete listener:', e)

if not os.getenv('MIGRATING_DB', '0') == '1':
    print('Registering Modules')
    modules = [str(m) for m in sys.modules if m.startswith('modules.')]
    for module in modules:
        del sys.modules[module]

    for module_file in get_py_files():
        fname = os.path.splitext(module_file)[0]
        # Ignore the base module file
        if fname == 'base':
            continue
        loaded_module = importlib.import_module(f'project.modules.{fname}')
        classes = inspect.getmembers(loaded_module, inspect.isclass)
        for class_info in classes:
            if issubclass(class_info[1], Module) == False:
                continue
            clazz = class_info[1](client)
            # Make sure the module class is an instance of the base module
            if issubclass(class_info[1], Module):
                # Skip loading the base module
                if clazz.name == None:
                    continue
                clazz.bot = client
                clazz.initialize()
                clazz.setup_self()
                clazz.post_setup()
                print(f'Loaded module {clazz.name}')
                del clazz
else:
    print('DB migration detected, Skipping module load')

logger = logging.getLogger('guilded')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename=app.config.get('PROJECT_ROOT') + '/guilded.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

# Register the flask apis
from project.server.api.verification import verification_blueprint
from project.server.api.moderation import moderation_blueprint
from project.server.api.guilds import guilds_blueprint
from project.server.api.data import data_blueprint
from project.server.api.auth import auth_blueprint
from project.server.api.feeds import feeds_blueprint
from project.server.api.giveaways import giveaways_blueprint
from project.server.api.images import images_blueprint
from project.server.api.reminders import reminders_blueprint
from project.server.api.roles import roles_blueprint
from project.server.api.fflags import fflag_blueprint

app.register_blueprint(verification_blueprint)
app.register_blueprint(moderation_blueprint)
app.register_blueprint(guilds_blueprint)
app.register_blueprint(data_blueprint)
app.register_blueprint(auth_blueprint)
app.register_blueprint(feeds_blueprint)
app.register_blueprint(giveaways_blueprint)
app.register_blueprint(images_blueprint)
app.register_blueprint(reminders_blueprint)
app.register_blueprint(roles_blueprint)
app.register_blueprint(fflag_blueprint)

if app_settings == 'DevelopmentConfig' and not os.getenv('MIGRATING_DB', '0') == '1':
    import threading
    def run():
        # Run the bot
        try:
            client.run(app.config.get('GUILDED_BOT_TOKEN'))
        except Exception as e:
            print(f'Failed to run in dev env: {str(e)}')
    
    thread = threading.Thread(target=run)

    thread.daemon = True
    thread.start()