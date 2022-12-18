import os
from guilded.ext import commands
from project import client, app, managers

import threading
import multiprocessing
import asyncio

preload_app = True
proc_name = 'serverguard'

def run():
    # Run the bot
    did_crash = False
    try:
        client.run(app.config.get('GUILDED_BOT_TOKEN'))
    except Exception as e:
        did_crash = True
        print('BOT CRASHED:', e)
    if did_crash is False:
        print('Bot was disconnected, restarting...')
    os.system('killall -KILL gunicorn')

thread = threading.Thread(target=run)

def on_starting(server):
    print(f'Bot thread alive status: {thread.is_alive()}', flush=True)
    print("Attempting to start bot thread", flush=True)
    thread.start()

def on_exit(server):
    loop = client.loop
    print("Attempting to stop bot thread", flush=True)
    loop.stop()
    print(f'Bot thread alive status: {thread.is_alive()}', flush=True)
