from guilded.ext import commands
from project import client, app, managers

import threading
import multiprocessing
import asyncio

preload_app = True

def run():
    # Run the bot
    while True:
        try:
            client.run(app.config.get('GUILDED_BOT_TOKEN'))
        except Exception as e:
            print('BOT CRASHED:', e)
            async def runner():
                with client:
                    await client.close()
            try:
                asyncio.run(runner())
            except Exception as e:
                print('FAILED TO STOP BOT:', e)
                break

thread = threading.Thread(target=run)

def on_starting(server):
    print(f'Bot thread alive status: {thread.is_alive()}', flush=True)
    print("Attempting to start bot thread", flush=True)
    thread.start()

def on_exit(server):
    for manager in managers:
        try:
            manager.shutdown()
        except Exception as e:
            print('Failed to shut down manager:', str(e))
    managers.clear()
    loop = client.loop
    print("Attempting to stop bot thread", flush=True)
    loop.stop()
    print(f'Bot thread alive status: {thread.is_alive()}', flush=True)
