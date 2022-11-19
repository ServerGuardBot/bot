import os
from guilded import Server, Member, User, http
from guilded.ext import commands
from guilded.ext.commands import Context, CommandError
from project.helpers.Cache import Cache
from project.helpers.embeds import *

import requests
import aiohttp
import re

guild_data_cache = Cache(60)
guild_info_cache = Cache(20)
premium_cache = Cache()

MEMBER_REGEX = r'@(.+)'
CHANNEL_REGEX = r'#(.+)'

class Module:
    bot: commands.Bot
    name = None
    bot_api: http.HTTPClient

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.bot_api = http.HTTPClient()
        self.bot_api.token = os.getenv('BOT_KEY')

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
            return cached
        else:
            try:
                self.bot_api.session = aiohttp.ClientSession()
                cached = (await self.bot_api.request(http.Route('GET', f'/teams/{guild_id}/info', override_base=http.Route.USER_BASE))).get('team')
                await self.bot_api.session.close()
            except Exception:
                cached = {}
            guild_info_cache.set(guild_id, cached)
            return cached

    async def get_ctx_members(self, ctx: commands.Context):
        guild_id = ctx.server.id

        return await ctx.server.fetch_members()

    async def get_ctx_roles(self, ctx: commands.Context):
        guild_id = ctx.server.id
        guild = await self.get_guild_info(guild_id)

        roleList = []
        roles: dict = guild.get('rolesById', {})

        for key in roles.keys():
            roleList.append(roles.get(key))
        
        return roleList

    async def get_ctx_channels(self, ctx: commands.Context):
        guild_id = ctx.server.id
        group_id = ctx.channel.group_id

        return ctx.server.channels

    async def convert_member(self, ctx: commands.Context, member: str, accept_user: bool=False):
        match: re.Match = re.search(MEMBER_REGEX, member)
        member_id = match is not None and match.group(1) or member

        if member_id is not None:
            member = member_id
        member_list = await self.get_ctx_members(ctx)
        for item in member_list:
            if item.id == member or item.name == member:
                return item
        if accept_user:
            try:
                user = await self.bot.getch_user(member)
                return user
            except:
                pass
    
    async def convert_channel(self, ctx: commands.Context, channel: str):
        match: re.Match = re.search(CHANNEL_REGEX, channel)
        channel_id = match is not None and match.group(1) or channel

        if channel_id is not None:
            channel = channel_id
        channel_list = await self.get_ctx_channels(ctx)
        print(channel_list)
        for item in channel_list:
            if item.id == channel or item.name == channel:
                return {
                    'id': item.id
                } #await self.bot.getch_channel(item.id)
        try:
            res = await self.bot.getch_channel(channel)
            return {
                'id': res.id
            }
        except Exception:
            return None
    
    async def convert_role(self, ctx: commands.Context, role: str):
        match: re.Match = re.search(MEMBER_REGEX, role)
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
            if item['id'] == role_int or item['name'] == role:
                return item
        if role_int:
            return {
                'id': role
            }
    
    async def user_can_manage_server(self, member: Member):
        guild_id = member.guild.id
        guild = await self.get_guild_info(guild_id)

        roles: dict = guild.get('rolesById', {})
        user_role_ids: list = await member.fetch_role_ids()
        for id in roles:
            role: dict = roles[id]
            if role['id'] in user_role_ids:
                perms: dict = role.get('permissions')
                if perms is not None:
                    MANAGE_SERVER_HEX = 4
                    if (perms.get('general', 0) & MANAGE_SERVER_HEX) == MANAGE_SERVER_HEX:
                        return True
        return False
    
    async def user_can_manage_xp(self, member: Member):
        guild_id = member.guild.id
        guild = await self.get_guild_info(guild_id)

        roles: dict = guild.get('rolesById', {})
        user_role_ids: list = await member.fetch_role_ids()
        for id in roles:
            role: dict = roles[id]
            if role['id'] in user_role_ids:
                perms: dict = role.get('permissions')
                if perms is not None:
                    MANAGE_XP_HEX = 1
                    if (perms.get('xp', 0) & MANAGE_XP_HEX) == MANAGE_XP_HEX:
                        return True
        return False

    async def get_user_premium_status(self, user_id):
        cached = premium_cache.get(user_id)
        if cached is not None:
            return cached
        self.bot_api.session = aiohttp.ClientSession()
        try:
            roles = await self.bot_api.get_member_roles('aE9Zg6Kj', user_id)
        except Exception:
            roles = None
        if roles is not None:
            roles = roles['roleIds']
        else:
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
        await self.bot_api.session.close()
        return cached
    
    def reset_user_premium_cache(self, user_id):
        premium_cache.remove(user_id)

    async def validate_permission_level(self, level: int, ctx: Context):
        allowed = True
        member = await ctx.guild.fetch_member(ctx.author.id)
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
        return await guild.fetch_member(user.id)
    
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