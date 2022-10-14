from guilded import Server, Member, User
from guilded.ext import commands
from guilded.ext.commands import Context, CommandError

import requests

class Module:
    bot: commands.Bot
    name = None

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def validate_permission_level(self, level: int, ctx: Context):
        allowed = True
        member = await ctx.guild.fetch_member(ctx.author.id)
        if level == 0:
            pass
        elif level == 1:
            if not await self.is_moderator(member):
                allowed = False
                await ctx.reply('You need to be a Moderator to use this command!')
                raise CommandError('You need to be a Moderator to use this command!')
        elif level == 2:
            if not await self.is_admin(member):
                allowed = False
                await ctx.reply('You need to be an Admin to use this command!')
                raise CommandError('You need to be an Admin to use this command!')
        return allowed
    
    async def get_member_from_user(self, guild: Server, user: User):
        return await guild.fetch_member(user.id)
    
    async def is_moderator(self, user: Member):
        from project import bot_config
        if user.id == user.guild.owner.id:
            return True # We know the owner of the guild is a moderator, bypass any unnecessary calls and checks

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
        if user.id == user.guild.owner.id:
            return True # We know the owner of the guild is an admin, bypass any unnecessary calls and checks

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