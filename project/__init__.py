from threading import Thread
from dotenv import load_dotenv
from guilded import MessageEvent, MessageUpdateEvent, MessageDeleteEvent, MemberJoinEvent, MemberRemoveEvent, ForumTopicCreateEvent, ForumTopicDeleteEvent, ForumTopicUpdateEvent, http
from guilded.ext import commands
from nsfw_detector import predict as nsfw_detect
from zipfile import ZipFile

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

bot_api = http.HTTPClient()
bot_api.token = app.config.get('GUILDED_BOT_TOKEN')

nsfw_model = nsfw_detect.load_model(app.config.get('PROJECT_ROOT') + '/project/ml_models/nsfw.h5')

db = SQLAlchemy(app)
migrate = Migrate(app, db)
cors = CORS(app, send_wildcard=True, origins="*")

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

client = BotClient('/', experimental_event_style=True)

malicious_urls = {}

def load_malicious_url_db():
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

async def run_url_db_dl():
    while True:
        await asyncio.sleep(60 * 10)
        load_malicious_url_db()

async def run_bot_loop():
    while True:
        await asyncio.sleep(60)
        requests.post('http://localhost:5000/moderation/expirestatuses', headers={
            'authorization': bot_config.SECRET_KEY
        })

load_malicious_url_db()

@client.event
async def on_ready():
    await client.wait_until_ready()
    print(f'Logged in as {client.user.name}')
    client.loop.create_task(run_bot_loop())
    client.loop.create_task(run_url_db_dl())
    print('Bot ready')

@client.event
async def on_message(event: MessageEvent):
    await client.process_commands(event.message)
    for callback in client.message_listeners:
        try:
            await callback(event.message)
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

app.register_blueprint(verification_blueprint)
app.register_blueprint(moderation_blueprint)

if app_settings == 'DevelopmentConfig':
    import threading
    def run():
        # Run the bot
        client.run(app.config.get('GUILDED_BOT_TOKEN'))
    
    thread = threading.Thread(target=run)

    thread.daemon = True
    thread.start()