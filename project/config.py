import os

basedir = os.path.abspath(os.path.dirname(__file__))
mysql_prod_base = 'mysql+pymysql://%s:%s@%s/'
database_name = 'serverguard'

class BaseConfig:
    """Base configuration."""
    GUILDED_BOT_TOKEN = os.getenv('BOT_KEY', 'this_is_bot_key')
    STEAM_KEY = os.getenv('STEAM_KEY', 'steam_key')
    YOUTUBE_KEY = os.getenv('YOUTUBE_KEY', 'youtube_key')
    TWITTER_KEY = os.getenv('TWITTER_KEY', 'twitter_key')
    TWITTER_SECRET = os.getenv('TWITTER_SECRET', 'twitter_secret')
    TWITTER_BEARER = os.getenv('TWITTER_BEARER', 'twitter_bearer')
    
    SECRET_KEY = os.getenv('SECRET_KEY', 'is_this_secret')
    DB_PASS = os.getenv('DB_PASS', 'is_this_db_pass')
    DB_USER = os.getenv('DB_USER', 'origin')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DEBUG = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024 # 10MB

class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    SQLALCHEMY_DATABASE_URI = (mysql_prod_base % (BaseConfig.DB_USER, BaseConfig.DB_PASS, BaseConfig.DB_HOST)) + database_name
    DEBUG = True


class TestingConfig(BaseConfig):
    """Testing configuration."""
    SQLALCHEMY_DATABASE_URI = (mysql_prod_base % (BaseConfig.DB_USER, BaseConfig.DB_PASS, BaseConfig.DB_HOST)) + database_name + '_test'
    DEBUG = True
    TESTING = True
    PRESERVE_CONTEXT_ON_EXCEPTION = False


class ProductionConfig(BaseConfig):
    """Production configuration."""
    SQLALCHEMY_DATABASE_URI = (mysql_prod_base % (BaseConfig.DB_USER, BaseConfig.DB_PASS, BaseConfig.DB_HOST)) + database_name
    DEBUG = False