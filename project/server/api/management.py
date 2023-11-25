from werkzeug.exceptions import Forbidden, BadRequest
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, db
from project.server.api.auth import get_user_auth

from project.server.models import UserInfo, Guild, GuildUser

management_blueprint = Blueprint('management', __name__)

# TODO: Guild searching
# TODO: User searching
# TODO: User data altering
# TODO: Guild data altering