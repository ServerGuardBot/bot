import os
import importlib.resources as resources

basedir = os.path.abspath(os.path.dirname(__file__))
mysql_prod_base = 'mysql+pymysql://%s:%s@%s/'
database_name = 'serverguard'

with resources.path(
        'project', 'database.db'
    ) as sqlite_filepath:
        DB_URI = f'sqlite:///{sqlite_filepath}?check_same_thread=False'

with resources.path(
        'project', 'database_test.db'
    ) as sqlite_filepath:
        DB_TESTURI = f'sqlite:///{sqlite_filepath}?check_same_thread=False'

class BaseConfig:
    """Base configuration."""
    GUILDED_BOT_TOKEN = os.getenv('BOT_KEY', 'this_is_bot_key')
    STEAM_KEY = os.getenv('STEAM_KEY', 'steam_key')
    YOUTUBE_KEY = os.getenv('YOUTUBE_KEY', 'youtube_key')
    TWITTER_KEY = os.getenv('TWITTER_KEY', 'twitter_key')
    TWITTER_SECRET = os.getenv('TWITTER_SECRET', 'twitter_secret')
    TWITTER_BEARER = os.getenv('TWITTER_BEARER', 'twitter_bearer')
    PROXYCHECK_KEY = os.getenv('PROXYCHECK_KEY', 'proxycheck')
    TURNSTILE_SECRET = os.getenv('TURNSTILE_SECRET', '1x0000000000000000000000000000000AA')
    
    ENFORCE_TURNSTILE = os.getenv('ENFORCE_TURNSTILE', False) # Flag to turn on turnstile once the website is ready for it
    PROJECT_ROOT = os.getenv('PROJECT_ROOT', '/root/serverguard')
    SECRET_KEY = os.getenv('SECRET_KEY', 'is_this_secret')
    DB_PASS = os.getenv('DB_PASS', 'is_this_db_pass')
    DB_USER = os.getenv('DB_USER', 'origin')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    SITE_ENCRYPTION = os.getenv('SITE_ENCRYPTION', 'idk')
    DEBUG = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024 # 10MB

class DevelopmentConfig(BaseConfig):
    """Development configuration."""
    SQLALCHEMY_DATABASE_URI = DB_URI #(mysql_prod_base % (BaseConfig.DB_USER, BaseConfig.DB_PASS, BaseConfig.DB_HOST)) + database_name
    DEBUG = True


class TestingConfig(BaseConfig):
    """Testing configuration."""
    SQLALCHEMY_DATABASE_URI = DB_TESTURI #(mysql_prod_base % (BaseConfig.DB_USER, BaseConfig.DB_PASS, BaseConfig.DB_HOST)) + database_name + '_test'
    DEBUG = True
    TESTING = True
    PRESERVE_CONTEXT_ON_EXCEPTION = False


class ProductionConfig(BaseConfig):
    """Production configuration."""
    SQLALCHEMY_DATABASE_URI = DB_URI #(mysql_prod_base % (BaseConfig.DB_USER, BaseConfig.DB_PASS, BaseConfig.DB_HOST)) + database_name
    DEBUG = False