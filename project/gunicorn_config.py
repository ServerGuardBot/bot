from guilded.ext import commands
from project import client, app

import threading
import multiprocessing
import asyncio

preload_app = True

def run():
    # Run the bot
    client.run(app.config.get('GUILDED_BOT_TOKEN'))

thread = threading.Thread(target=run)

def on_starting(server):
    print(f'Bot thread alive status: {thread.is_alive()}', flush=True)
    print("Attempting to start bot thread", flush=True)
    thread.start()

def on_exit(server):
    loop = client.loop
    print("Attempting to stop bot thread", flush=True)
    loop.run_until_complete(client.close())
    print(f'Bot thread alive status: {thread.is_alive()}', flush=True)
