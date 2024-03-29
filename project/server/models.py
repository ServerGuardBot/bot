from json import JSONDecoder, JSONEncoder
import random
import re
import string
from project import db
from project.helpers.images import *
from datetime import datetime
from sqlalchemy_json import NestedMutableJson

class FFlag(db.Model):
    """ FFlag model for storing feature flags """
    __tablename__ = 'fflags'

    flag = db.Column(db.String(500), primary_key=True)
    type = db.Column(db.Integer, nullable=False, server_default="0")
    value = db.Column(db.String, nullable=False, server_default="")

    def __init__(self, flag: str, type: int, value: str):
        self.flag = flag
        self.type = type
        self.value = value
    
    def __repr__(self):
        return f'<FFlag {self.flag}={self.value}>'

class BotData(db.Model):
    """ Bot Data model for storing persistent bot information """
    __tablename__ = 'botdata'

    key = db.Column(db.String(500), primary_key=True)
    value = db.Column(db.String(500), nullable=False, server_default="")

    def __init__(self, key: str, value: str):
        self.key = str(key)
        self.value = str(value)
    
    def __repr__(self):
        return f'<BotData {self.key}={self.value}>'

class AnalyticsItem(db.Model):
    """ Analytics Item model for storing analytics data """
    __tablename__ = 'analytics'

    id = db.Column(db.String(500), primary_key=True)
    guild_id = db.Column(db.String(500), nullable=False)
    key = db.Column(db.String(500), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    value = db.Column(db.Float, nullable=False, server_default="0")

    @staticmethod
    def get_date(round_to: str='minute'):
        date = datetime.now()

        if round_to == 'day':
            date = datetime(year=date.year, month=date.month, day=date.day)
        elif round_to == 'hour':
            date = datetime(year=date.year, month=date.month, day=date.day, hour=date.hour)
        elif round_to == 'minute':
            date = datetime(year=date.year, month=date.month, day=date.day, hour=date.hour, minute=date.minute)
        else:
            raise Exception('round_to must either be "minute", "day", or "hour"')

        return date

    def __init__(self, guild_id: str, key: str, value: str, date: datetime=None):
        self.id = f'{guild_id}/{key}/{date.timestamp()}'
        self.guild_id = guild_id
        self.key = key
        self.value = value
        self.date = date or datetime.now()
    
    def __repr__(self):
        return f'<AnalyticsItem guild={self.guild_id} key={self.key} value={self.value} date={self.date.timestamp()}>'

class Guild(db.Model):
    """ Guild model for storing guild data """
    __tablename__ = 'guilds'

    guild_id = db.Column(db.String(500), primary_key=True)
    premium = db.Column(db.String(500), nullable=True)
    config = db.Column(NestedMutableJson)
    active = db.Column(db.Boolean, nullable=False, server_default="1")

    name = db.Column(db.String(500), nullable=True)
    bio = db.Column(db.String(500), nullable=True)
    avatar = db.Column(db.String(500), nullable=True)
    members = db.Column(db.Integer, nullable=False, server_default="0")

    def __init__(self, guild_id: str):
        self.guild_id = guild_id
        self.config = {}
    
    def __repr__(self):
        return f'<Guild {self.guild_id}>'

class GuildActivity(db.Model):
    """ Guild Activity model for storing guild activity logs """
    __tablename__ = 'guildactivity'

    internal_id = db.Column(db.String(500), primary_key=True)
    guild_id = db.Column(db.String(500), nullable=False)
    activity_id = db.Column(db.String(500), nullable=False)

    user_id = db.Column(db.String(500), nullable=True)
    logged_at = db.Column(db.DateTime, nullable=False)
    action = db.Column(NestedMutableJson, nullable=False)

    def __init__(self, guild_id: str, user_id: str, action: dict):
        self.activity_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=32))
        self.internal_id = f'{guild_id}/{self.activity_id}'
        self.guild_id = guild_id
        self.user_id = user_id
        self.logged_at = datetime.now()
        self.action = action
    
    def __repr__(self):
        return f'<GuildActivity {self.internal_id}>'

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
    permission_level = db.Column(db.Integer, nullable=False, server_default="0")
    xp = db.Column(db.Integer, nullable=False, server_default="0")
    join_date = db.Column(db.DateTime, nullable=True)

    def __init__(self, guild_id: str, user_id: str, hashed_ip: str=None, browser_id: str=None, using_vpn: bool=False, connections: str=None, permission_level: int=0):
        self.internal_id = f'{guild_id}/{user_id}'
        self.guild_id = guild_id
        self.user_id = user_id
        self.hashed_ip = hashed_ip
        self.browser_id = browser_id
        self.using_vpn = using_vpn
        self.connections = connections
        self.permission_level = permission_level
        self.join_date = datetime.now()
    
    def __repr__(self):
        return f'<GuildUser {self.internal_id}>'

class GuildUserStatus(db.Model):
    """ Guild User Status model for storing guild user statuses """
    __tablename__ = 'guilduserstatuses'

    internal_id = db.Column(db.String(500), primary_key=True)
    guild_id = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(500), nullable=False)

    created_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    value = db.Column(NestedMutableJson, nullable=False)

    def __init__(self, guild_id: str, user_id: str, type: str, value: dict, ends_at: datetime=None):
        self.internal_id = f'{guild_id}/{user_id}/{type}/{"".join(random.choices(string.ascii_letters, k=15))}'
        self.guild_id = guild_id
        self.user_id = user_id
        self.type = type
        self.value = value
        self.ends_at = ends_at
        self.created_at = datetime.now()

    def __repr__(self):
        return f'<GuildUserStatus {self.internal_id}>'

class GuildChannelConfig(db.Model):
    """ Guild Channel Config model for storing guild channel configurations """
    __tablename__ = 'guildchannelconfigs'
    internal_id = db.Column(db.String(500), primary_key=True)
    unique_id = db.Column(db.String(500), nullable=False)
    guild_id = db.Column(db.String(500), nullable=False)
    channel_id = db.Column(db.String(500), nullable=False)

    type = db.Column(db.String(500), nullable=False)
    value = db.Column(NestedMutableJson, nullable=False)

    def __init__(self, guild_id: str, channel_id: str, type: str, value: dict):
        self.unique_id = "".join(random.choices(string.ascii_letters, k=15))
        self.internal_id = f'{guild_id}/{channel_id}/{type}/{self.unique_id}'
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.type = type
        self.value = value
    
    def __repr__(self):
        return f'<GuildChannelConfig {self.internal_id}>'

class GuildRoleConfig(db.Model):
    """ Guild Role Config model for storing guild role configurations """
    __tablename__ = 'guildroleconfigs'
    internal_id = db.Column(db.String(500), primary_key=True)
    unique_id = db.Column(db.String(500), nullable=False)
    guild_id = db.Column(db.String(500), nullable=False)
    role_id = db.Column(db.String(500), nullable=False)

    type = db.Column(db.String(500), nullable=False)
    value = db.Column(NestedMutableJson, nullable=False)

    def __init__(self, guild_id: str, role_id: str, type: str, value: dict):
        self.unique_id = "".join(random.choices(string.ascii_letters, k=15))
        self.internal_id = f'{guild_id}/{role_id}/{type}/{self.unique_id}'
        self.guild_id = guild_id
        self.role_id = role_id
        self.type = type
        self.value = value

class FeedData(db.Model):
    """ Feed Data model for storing RSS feeds and their information """
    __tablename__ = 'feeddata'
    id = db.Column(db.String(500), primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    name = db.Column(db.String(500), nullable=False)
    blur_hash = db.Column(db.String(40), nullable=False)

    def __init__(self, name: str, url: str, blur_hash: str):
        formatted_name = re.sub(r'[\W]+', '-', name.lower().strip().replace(' ', '-'))
        self.id = f'{formatted_name[0:min(len(formatted_name), 10)]}-{"".join(random.choices(string.ascii_letters, k=15))}'
        self.name = name
        self.url = url
        self.blur_hash = blur_hash
    
    def __repr__(self):
        return f'<FeedData {self.id}>'

class Giveaway(db.Model):
    """ Giveaway model for storing a giveaway in a guild """
    __tablename__ = 'giveaways'
    internal_id = db.Column(db.String(500), primary_key=True)
    id = db.Column(db.String(100), nullable=False)
    guild_id = db.Column(db.String(500), nullable=False)
    channel_id = db.Column(db.String(500), nullable=False)
    original_message_id = db.Column(db.String(500), nullable=False)

    ended = db.Column(db.Boolean, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    prize = db.Column(db.String(500), nullable=False)
    hosted_by = db.Column(db.String(500), nullable=False)
    winner_amount = db.Column(db.Integer, nullable=False)
    winners = db.Column(NestedMutableJson, nullable=False)
    entries = db.Column(NestedMutableJson, nullable=False)

    def __init__(self, guild_id: str, channel_id: str, message_id: str, winners: int, ends_at: datetime, prize: str, hosted_by: str):
        self.id = "".join(random.choices(string.ascii_letters, k=30))
        self.internal_id = f'{guild_id}/{channel_id}/{self.id}'
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.original_message_id = message_id
        self.winner_amount = winners
        self.ends_at = ends_at
        self.prize = prize
        self.ended = False
        self.hosted_by = hosted_by

        self.entries = []
        self.winners = []
    
    def __repr__(self):
        return f'<Giveaway {self.internal_id}>'

class UserInfo(db.Model):
    """ User Info model for storing user information to be shared across guilds """
    __tablename__ = 'userinfo'

    user_id = db.Column(db.String(500), nullable=False, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    avatar = db.Column(db.String(500), nullable=False)
    guilded_data = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, nullable=True)

    connections = db.Column(db.String(500), nullable=True)
    last_updated = db.Column(db.DateTime, nullable=False)

    roblox = db.Column(db.String(500), nullable=True)
    steam = db.Column(db.String(500), nullable=True)
    youtube = db.Column(db.String(500), nullable=True)
    twitter = db.Column(db.String(500), nullable=True)

    guilds = db.Column(db.String(500), nullable=False)
    premium = db.Column(db.String(500), nullable=False, server_default="0")
    language = db.Column(db.String(10), nullable=False, server_default="en")

    @staticmethod
    def update_connections(self, data: dict):
        self.connections = JSONEncoder().encode(data)

        if data.get('roblox'):
            roblox: dict = data['roblox']
            self.roblox = roblox.get('service_id', roblox.get('serviceId', None))
        if data.get('steam'):
            steam: dict = data['steam']
            self.steam = steam.get('service_id', steam.get('serviceId', None))
        if data.get('youtube'):
            youtube: dict = data['youtube']
            self.youtube = youtube.get('handle', None)
        if data.get('twitter'):
            twitter: dict = data['twitter']
            self.twitter = twitter.get('handle', None)
    
    @staticmethod
    def update_user_data(self, guilded_data: dict):
        self.name = guilded_data.get('name', '')
        self.avatar = guilded_data.get('profilePictureLg', IMAGE_DEFAULT_AVATAR) or IMAGE_DEFAULT_AVATAR
        self.guilded_data = JSONEncoder().encode(guilded_data)
    
    @staticmethod
    def update_guilds(self, guilds: dict):
        self.guilds = JSONEncoder().encode([
            {
                'id': guild['id'],
                'name': guild['name'],
                'avatar': guild['profilePicture']
            } for guild in guilds
        ])

    def __init__(self, user_id: str, guilded_data: dict={}, connections: dict={}, guilds: dict={}, premium: int=0):
        self.user_id = user_id
        self.created_at = datetime.now()
        self.premium = str(premium)
        self.last_updated = datetime.now()

        UserInfo.update_connections(self, connections)
        UserInfo.update_user_data(self, guilded_data)
        UserInfo.update_guilds(self, guilds)

    def __repr__(self):
        return f'<UserInfo {self.user_id}>'

class BlacklistedRefreshToken(db.Model):
    """ Blacklisted Refresh Token model for storing non-expired blacklisted tokens """
    __tablename__ = 'refresh_token_blacklist'

    token = db.Column(db.String(500), nullable=False, primary_key=True)
    expires = db.Column(db.DateTime, nullable=False)

    def __init__(self, token: str, expires: datetime):
        self.token = token
        self.expires = expires
    
    def __repr__(self):
        return f'<BlacklistedRefreshToken {self.token} expires={self.expires.timestamp()}>'