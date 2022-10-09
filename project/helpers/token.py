from project import app
import jwt

def encodeToken(payload):
    return jwt.encode(payload, app.config.get('SECRET_KEY'), algorithm='HS256')

def decodeToken(token):
    return jwt.decode(token, app.config.get('SECRET_KEY'), algorithms='HS256')