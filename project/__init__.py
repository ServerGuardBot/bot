from threading import Thread
from dotenv import load_dotenv
from guilded import Embed, MessageEvent
from guilded.ext import commands

from project.modules.base import Module

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

load_dotenv()

import project.server
import project.modules
import project.config

import importlib
import logging
import inspect
import os
import sys

__location__ = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))

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

db = SQLAlchemy(app)
migrate = Migrate(app, db)
cors = CORS(app)

class BotClient(commands.Bot):
    config = app.config
    message_listeners: list = []

client = BotClient('/', experimental_event_style=True)

@client.event
async def on_ready():
    print(f'Logged in as {client.user.name}')
    print('Bot ready')

@client.event
async def on_message(event: MessageEvent):
    await client.process_commands(event.message)
    for callback in client.message_listeners:
        try:
            await callback(event.message)
        except Exception as e:
            print('Failed to run message listener:', e)

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
handler = logging.FileHandler(filename='guilded.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

def run():
    # Register the flask apis
    from project.server.api.verification import verification_blueprint

    app.register_blueprint(verification_blueprint)

    # Register help command
    @client.command(name='commands')
    async def commands_(ctx: commands.Context):
        await ctx.reply(embed=Embed(
            title='Commands',
            description=
'''/verify - start the verification process
/evaluate `<user>` - Moderator+, shows an evaluation of a user
/config - Administrator, configure the bot's settings. Use /config help for more information
/bypass `<user>` - Moderator+, allows a user to bypass verification
/unbypass `<user>` - Moderator+, revokes a user's verification bypass
/commands - brings up this help text
'''
        ))

    # Run the bot
    client.run(app.config.get('GUILDED_BOT_TOKEN'))

thread = Thread(target=run)
thread.daemon = True
thread.start()