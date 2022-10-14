from datetime import datetime
import string
from project.modules.base import Module
from project.helpers.Cache import Cache
from project import bot_config, nsfw_model, nsfw_detect
from guilded.ext import commands
from guilded import Embed, ChatMessage, Colour, MemberJoinEvent
from os import remove

import random
import requests

settings_cache = Cache(60)

class NSFWModule(Module):
    name = 'NSFW'

    def get_logs_channel(self, guild):
        cached = settings_cache.get(guild)

        if cached:
            return cached
        else:
            res = requests.get(f'http://localhost:5000/guilddata/{guild}/cfg/nsfw_logs_channel', headers={
                'authorization': bot_config.SECRET_KEY
            })
            cached = res.json().get('result')
            settings_cache.set(guild, cached)
            return cached
    
    def reset_cache(self, guild):
        settings_cache.remove(guild)

    def check_model_results(self, results):
        if max(results['hentai'], results['porn']) >= 0.5:
            classification = 'NSFW'
            certainty = round(max(results['hentai'], results['porn']) * 100)
        elif results['sexy'] >= 1:
            classification = 'Suggestive'
            certainty = round(results['sexy'] * 100)
        else:
            classification = 'Normal'
            certainty = round(results['neutral'] * 100)
        
        return classification, certainty

    def scan_image(self, url):
        path = f'/tmp/guilded-{"".join(random.choices(string.ascii_letters, k=15))}-{datetime.now().timestamp()}'
        with open(path, mode='wb+') as file:
            img = requests.get(url).content
            file.write(img)
            results = nsfw_detect.classify(nsfw_model, path).get(path)
            remove(path)
            return self.check_model_results(results)

    def initialize(self):
        bot = self.bot

        async def on_member_join(event: MemberJoinEvent):
            member = event.member
            if member.avatar is not None:
                logs_channel_id = self.get_logs_channel(event.server_id)
                if logs_channel_id and logs_channel_id != '':
                    classification, certainty = self.scan_image(member.avatar.aws_url)

                    if classification == 'NSFW':
                        em = Embed(
                            title = 'NSFW profile picture detection',
                            description=f'From user "{member.name}"',
                            url=member.profile_url,
                            timestamp = datetime.now(),
                            colour = certainty >= 80 and Colour.red() or Colour.orange()
                        ) \
                        .set_image(url=member.avatar.aws_url) \
                        .set_footer(text=f'Certainty: {certainty}%')
                        channel = await bot.getch_channel(logs_channel_id)
                        await channel.send(embed=em)
                    elif classification == 'Suggestive':
                        em = Embed(
                            title = 'Suggestive profile picture detection',
                            description=f'From user "{member.name}"',
                            url=member.profile_url,
                            timestamp = datetime.now(),
                            colour = certainty >= 80 and Colour.red() or Colour.orange()
                        ) \
                        .set_image(member.avatar.aws_url) \
                        .set_footer(f'Certainty: {certainty}%')
                        channel = await bot.getch_channel(logs_channel_id)

        async def on_message(message: ChatMessage):
            logs_channel_id = self.get_logs_channel(message.guild.id)
            if logs_channel_id and logs_channel_id != '':
                for item in message.attachments:
                    if any(f'.{ele}' in item.url for ele in ['jpeg', 'jpg', 'tif', 'tiff', 'gif', 'jif', 'png', 'webp', 'bmp', 'apng']):
                        classification, certainty = self.scan_image(item.url)
                        
                        if classification == 'NSFW':
                            em = Embed(
                                title = 'NSFW detection',
                                description=f'Sent by {message.author.name} in {message.channel.id}',
                                url=message.share_url,
                                timestamp = message.created_at,
                                colour = certainty >= 80 and Colour.red() or Colour.orange()
                            ) \
                            .set_image(url=item.url) \
                            .set_footer(text=f'Certainty: {certainty}%')
                            channel = await bot.getch_channel(logs_channel_id)
                            await channel.send(embed=em)
                            if certainty >= 80:
                                await message.delete()
                        elif classification == 'Suggestive':
                            em = Embed(
                                title = 'Suggestive image detection',
                                description=f'Sent by {message.author.name} in {message.channel.id}',
                                url=message.share_url,
                                timestamp = message.created_at,
                                colour = certainty >= 80 and Colour.red() or Colour.orange()
                            ) \
                            .set_image(item.url) \
                            .set_footer(f'Certainty: {certainty}%')
                            channel = await bot.getch_channel(logs_channel_id)
        
        bot.message_listeners.append(on_message)
        bot.join_listeners.append(on_member_join)