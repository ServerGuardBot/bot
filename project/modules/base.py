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
        if server.member_count == 0:
            # Only call fill members if the member count is 0
            await server.fill_members()

        guild_data_req = requests.patch(f'http://localhost:5000/guilddata/{guild_id}', headers={
            'authorization': bot_config.SECRET_KEY
        }, json={
            'name': server.name,
            'bio': server.about,
            'avatar': server.avatar is not None and server.avatar.aws_url or IMAGE_DEFAULT_AVATAR,
            'members': server.member_count
        })
    
    async def get_user_permission_level(self, guild_id: str, user_id: str):
        from project import bot_config

        user_data_req = requests.get(f'http://localhost:5000/getguilduser/{guild_id}/{user_id}', headers={
            'authorization': bot_config.SECRET_KEY
        })

        update_data = False
        if user_data_req.status_code == 200:
            permission_level = int(user_data_req.json().get('permission_level', 0))

            if permission_level == 0:
                update_data = True
        else:
            update_data = True
        
        if update_data:
            guild = await self.bot.getch_server(guild_id)
            user = await guild.getch_member(user_id)
            if user_id == guild.owner.id:
                permission_level = 4 # We know the owner of the guild is a moderator, bypass any unnecessary calls and checks
            elif await self.user_can_manage_server(user):
                permission_level = 3
            else:
                _lvl = 0
                role_config_req = requests.get(f'http://localhost:5000/guilddata/{guild_id}/cfg/roles', headers={
                    'authorization': bot_config.SECRET_KEY
                })
                role_config_json: dict = role_config_req.json()
                if role_config_req.status_code == 200:
                    role_set: list[dict] = role_config_json['result']
                    role_ids: list[int] = await user.fetch_role_ids()
                    for cfg in role_set:
                        try:
                            i = role_ids.index(int(cfg.get('id')))
                            lvl = int(cfg.get('level'))
                            if lvl + 1 > _lvl:
                                _lvl = lvl + 1
                        except Exception as e:
                            pass
                permission_level = _lvl
            user_data_set_req = requests.patch(f'http://localhost:5000/getguilduser/{guild_id}/{user_id}', json={
                'permission_level': permission_level
                }, headers={
                'authorization': bot_config.SECRET_KEY
            })
        return permission_level


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

    async def get_ctx_members(self, ctx: commands.Context):
        return await ctx.server.members

    async def get_ctx_roles(self, ctx: commands.Context):
        guild = ctx.server

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
        roles = await self.get_ctx_roles(ctx)
        for item in roles:
            if item.id == role_int or item.name == role:
                return item
        if role_int:
            return role
    
    async def user_can_manage_server(self, member: Member):
        ids = member._role_ids
        for role_id in ids:
            role = await member.server.getch_role(role_id)
            if role.permissions.update_server: return True
    
    async def user_can_manage_xp(self, member: Member):
        ids = member._role_ids
        for role_id in ids:
            role = await member.server.getch_role(role_id)
            print(f'[{role.name}]: {role.permissions.manage_server_xp}')
            if role.permissions.manage_server_xp: return True

    async def get_user_premium_status(self, user_id):
        from project import bot_config
        user_data_req = requests.get(f'http://localhost:5000/userinfo/aE9Zg6Kj/{user_id}', headers={
            'authorization': bot_config.SECRET_KEY
        })

        return int(user_data_req.json().get('premium'))
    
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
        # TODO: Move this into the db so that it does not use unnecessary API calls
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
        permission_level = await self.get_user_permission_level(user.server.id, user.id)

        return permission_level > 0
    
    async def is_admin(self, user: Member):
        permission_level = await self.get_user_permission_level(user.server.id, user.id)

        return permission_level > 1
    
    def setup_self(self):
        pass
    
    def initialize(self):
        pass
    
    def post_setup(self):
        pass