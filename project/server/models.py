from project import db
from datetime import datetime
from sqlalchemy_json import NestedMutableJson

class Guild(db.Model):
    """ Guild model for storing guild data """
    __tablename__ = 'guilds'

    guild_id = db.Column(db.String(500), primary_key=True)
    premium = db.Column(db.String(500), nullable=True)
    config = db.Column(NestedMutableJson)

    def __init__(self, guild_id: str):
        self.guild_id = guild_id
        self.config = {}
    
    def __repr__(self):
        return f'<Guild {self.guild_id}>'

class GuildUser(db.Model):
    """ Guild User model for storing guild user-related data """
    __tablename__ = 'guildusers'

    internal_id = db.Column(db.String(500), primary_key=True)
    guild_id = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.String(500), nullable=False)

    browser_id = db.Column(db.String(500), nullable=True)
    hashed_ip = db.Column(db.String(500), nullable=True)
    is_banned = db.Column(db.Boolean, default=False)
    using_vpn = db.Column(db.Boolean, default=False)
    bypass_verification = db.Column(db.Boolean, default=False)
    connections = db.Column(db.String(500), nullable=True)

    def __init__(self, guild_id: str, user_id: str, hashed_ip: str=None, browser_id: str=None, using_vpn: bool=False, connections: str=None):
        self.internal_id = f'{guild_id}/{user_id}'
        self.guild_id = guild_id
        self.user_id = user_id
        self.hashed_ip = hashed_ip
        self.browser_id = browser_id
        self.using_vpn = using_vpn
        self.connections = connections
    
    def __repr__(self):
        return f'<GuildUser {self.internal_id}>'