import os
from guilded import Server, Member, User, http
from guilded.ext import commands
from guilded.ext.commands import Context, CommandError
from project.helpers.Cache import Cache
from project.helpers.embeds import *

import requests
import re

guild_data_cache = Cache(60)
guild_info_cache = Cache(20)
premium_cache = Cache()

MEMBER_REGEX = r'<@(.+)>'
ROLE_REGEX = r'<@&(.+)>'
CHANNEL_REGEX = r'<#(.+)>'

class Module:
    bot: commands.Bot
    name = None
    bot_api: http.HTTPClient

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.bot_api = http.HTTPClient()
        self.bot_api.token = os.getenv('BOT_KEY')
    
    async def _update_guild_data(self, guild_id: str):
        from project import bot_config
        server = await self.bot.getch_server(guild_id)
        await server.fill_members()

        guild_data_req = requests.patch(f'http://localhost:5000/guilddata/{guild_id}', headers={
            'authorization': bot_config.SECRET_KEY
        }, json={
            'name': server.name,
            'bio': server.about,
            'avatar': server.avatar is not None and server.avatar.aws_url or IMAGE_DEFAULT_AVATAR,
            'members': server.member_count
        })

    def get_guild_data(self, guild_id: str):
        from project import bot_config
        cached = guild_data_cache.get(guild_id)

        if cached:
            return cached
        else:
            guild_data_req = requests.get(f'http://localhost:5000/guilddata/{guild_id}', headers={
                'authorization': bot_config.SECRET_KEY
            })
            cached: dict = guild_data_req.json()
            guild_data_cache.set(guild_id, cached)
            return cached

    async def get_guild_info(self, guild_id: str):
        cached = guild_info_cache.get(guild_id)

        if cached:
            if cached == 'PRIVATE':
                return None
            return cached
        else:
            try:
                cached = await self.bot.fetch_public_server(guild_id)
                guild_info_cache.set(guild_id, cached)
                return cached
            except:
                # The guild is likely private, indicate as such and return none
                guild_info_cache.set(guild_id, 'PRIVATE')
                return None

    async def get_ctx_members(self, ctx: commands.Context):
        return await ctx.server.members

    async def get_ctx_roles(self, ctx: commands.Context):
        guild_id = ctx.server.id
        guild = await self.get_guild_info(guild_id)

        if guild is not None:
            return guild.roles
        return []

    async def get_ctx_channels(self, ctx: commands.Context):
        guild_id = ctx.server.id
        group_id = ctx.channel.group_id

        return ctx.server.channels

    async def convert_member(self, ctx: commands.Context, member: str, accept_user: bool=False):
        match: re.Match = re.search(MEMBER_REGEX, member)
        member_id = match is not None and match.group(1) or member

        if member_id is not None:
            member = member_id
        try:
            res = await ctx.server.getch_member(member)
            return res
        except:
            pass
        if accept_user:
            try:
                user = await self.bot.getch_user(member)
                return user
            except:
                return None
    
    async def convert_channel(self, ctx: commands.Context, channel: str):
        match: re.Match = re.search(CHANNEL_REGEX, channel)
        channel_id = match is not None and match.group(1) or channel

        if channel_id is not None:
            channel = channel_id
        try:
            res = await self.bot.getch_channel(channel)
            return res
        except Exception:
            return None
    
    async def convert_role(self, ctx: commands.Context, role: str):
        match: re.Match = re.search(ROLE_REGEX, role)
        role_id = match is not None and match.group(1) or role

        if role_id is not None:
            role = role_id
        role_int = 0
        try:
            role_int = int(role)
        except Exception:
            pass
        role_list = await self.get_ctx_roles(ctx)
        for item in role_list:
            if item.id == role_int or item.name == role:
                return item
        if role_int:
            return role
    
    async def user_can_manage_server(self, member: Member):
        guild_id = member.guild.id
        guild = await self.get_guild_info(guild_id)

        if guild is None:
            return False

        roles = guild.roles
        user_role_ids: list = await member.fetch_role_ids()
        for role in roles:
            if role.id in user_role_ids:
                if role.permissions.manage_server:
                    return True
        return False
    
    async def user_can_manage_xp(self, member: Member):
        guild_id = member.guild.id
        guild = await self.get_guild_info(guild_id)

        if guild is None:
            return False

        roles = guild.roles
        user_role_ids: list = await member.fetch_role_ids()
        for role in roles:
            if role.id in user_role_ids:
                if role.permissions.manage_server_xp:
                    return True
        return False

    async def get_user_premium_status(self, user_id):
        cached = premium_cache.get(user_id)
        if cached is not None:
            return cached
        try:
            support_server = await self.bot.getch_server('aE9Zg6Kj')
            member = await support_server.getch_member(user_id)
            roles = await member.fetch_role_ids()
        except Exception:
            roles = None

        if roles is None:
            roles = []

        if 32612283 in roles:
            cached = 3
        elif 32612284 in roles:
            cached = 2
        elif 32612285 in roles:
            cached = 1
        else:
            cached = 0
        
        premium_cache.set(user_id, cached)
        return cached
    
    def reset_user_premium_cache(self, user_id):
        premium_cache.remove(user_id)

    async def validate_permission_level(self, level: int, ctx: Context):
        allowed = True
        member = await ctx.guild.getch_member(ctx.author.id)
        if level == 0:
            pass
        elif level == 1:
            if not await self.is_moderator(member):
                allowed = False
                await ctx.reply(embed=EMBED_COMMAND_ERROR('You need to be a Moderator to use this command!'))
                raise CommandError('You need to be a Moderator to use this command!')
        elif level == 2:
            if not await self.is_admin(member):
                allowed = False
                await ctx.reply(embed=EMBED_COMMAND_ERROR('You need to be an Admin to use this command!'))
                raise CommandError('You need to be an Admin to use this command!')
        return allowed
    
    async def get_member_from_user(self, guild: Server, user: User):
        return await guild.getch_member(user.id)
    
    async def is_trusted(self, user: Member):
        from project import bot_config
        guild = await self.bot.getch_server(user.server.id)
        if user.id == guild.owner.id:
            return True # We know the owner of the guild is trusted, bypass any unnecessary calls and checks
        if await self.user_can_manage_server(user):
            return True
        
        role_config_req = requests.get(f'http://localhost:5000/guilddata/{user.guild.id}/cfg/trusted_roles', headers={
            'authorization': bot_config.SECRET_KEY
        })
        role_config_json: dict = role_config_req.json()
        if role_config_req.status_code == 200:
            role_set: list[dict] = role_config_json['result']
            role_ids: list[int] = await user.fetch_role_ids()
            for role in role_set:
                try:
                    i = role_ids.index(int(role))
                    return True
                except Exception as e:
                    pass

        return False

    async def is_moderator(self, user: Member):
        from project import bot_config
        guild = await self.bot.getch_server(user.server.id)
        if user.id == guild.owner.id:
            return True # We know the owner of the guild is a moderator, bypass any unnecessary calls and checks
        if await self.user_can_manage_server(user):
            return True

        role_config_req = requests.get(f'http://localhost:5000/guilddata/{user.guild.id}/cfg/roles', headers={
            'authorization': bot_config.SECRET_KEY
        })
        role_config_json: dict = role_config_req.json()
        if role_config_req.status_code == 200:
            role_set: list[dict] = role_config_json['result']
            role_ids: list[int] = await user.fetch_role_ids()
            for cfg in role_set:
                try:
                    i = role_ids.index(int(cfg.get('id')))
                    return True
                except Exception as e:
                    pass

        return False
    
    async def is_admin(self, user: Member):
        from project import bot_config
        guild = await self.bot.getch_server(user.server.id)
        if user.id == guild.owner.id:
            return True # We know the owner of the guild is an admin, bypass any unnecessary calls and checks
        if await self.user_can_manage_server(user):
            return True

        role_config_req = requests.get(f'http://localhost:5000/guilddata/{user.guild.id}/cfg/roles', headers={
            'authorization': bot_config.SECRET_KEY
        })
        role_config_json: dict = role_config_req.json()
        if role_config_req.status_code == 200:
            role_set: list[dict] = role_config_json['result']
            role_ids: list[int] = await user.fetch_role_ids()
            for cfg in role_set:
                if cfg.get('level') == 1: # 0 = Moderator, 1 = Administrator
                    try:
                        i = role_ids.index(int(cfg.get('id')))
                        return True
                    except Exception:
                        pass

        return False
    
    def setup_self(self):
        pass
    
    def initialize(self):
        pass
    
    def post_setup(self):
        pass