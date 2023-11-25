from werkzeug.exceptions import Forbidden, BadRequest
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, db
from project.server.api.auth import get_user_auth

from project.server.models import FFlag

BOOLEAN_FLAGS = {
    'false': False,
    'true': True,
    '0': False,
    '1': True,
    'no': False,
    'yes': True,
    'off': False,
    'on': True,
}

fflag_blueprint = Blueprint('fflags', __name__)

class ListFFlags(MethodView):
    def get(self):
        auth = request.cookies.get('auth')

        if auth is None:
            raise Forbidden('Please provide a valid auth token')
        if auth != app.config.get('SECRET_KEY'):
            user = get_user_auth()
            if user != 'm6YxwpQd':
                raise Forbidden()

        fflags = FFlag.query.all()
        if request.args.get('minimal', '0') == '1':
            flags = {}
        else:
            flags = []

        for flag in fflags:
            flag: FFlag
            t = flag.type
            value = flag.value
            if t == 0: # String
                value = flag.value
            elif t == 1: # Integer
                value = int(flag.value)
            elif t == 2: # Boolean
                value = BOOLEAN_FLAGS.get(flag.value.lower(), False)
            elif t == 3: # String list
                value = flag.value.split(',')
            elif t == 4: # Int list
                value = [int(i) for i in flag.value.split(',')]
            if request.args.get('minimal', '0') == '1':
                flags[flag.flag] = value
            else:
                flags.append({
                    'flag': flag.flag,
                    'value': value,
                    'type': t,
                })
        
        return jsonify(flags), 200

class AlterFFLag(MethodView):
    def post(self, key):
        user = get_user_auth()
        if user != 'm6YxwpQd':
            raise Forbidden()
        
        post_data: dict = request.get_json()
        value = post_data.get('value')
        type = post_data.get('type')

        flag: FFlag = FFlag.query.filter(FFlag.flag == key).first()
        if flag is None:
            flag = FFlag(key, type, value)
            db.session.add(flag)
            db.session.commit()

            return jsonify({
                'flag': flag.flag,
                'value': flag.value,
                'type': flag.type,
            }), 201
        else:
            raise BadRequest
    def patch(self, key):
        user = get_user_auth()
        if user != 'm6YxwpQd':
            raise Forbidden()
        
        post_data: dict = request.get_json()
        value = post_data.get('value')

        flag: FFlag = FFlag.query.filter(FFlag.flag == key).first()
        if flag is None:
            raise BadRequest
        else:
            flag.value = value
            db.session.commit()

            return jsonify({
                'flag': flag.flag,
                'value': flag.value,
                'type': flag.type,
            }), 200
    def delete(self, key):
        user = get_user_auth()
        if user != 'm6YxwpQd':
            raise Forbidden()
        
        flag: FFlag = FFlag.query.filter(FFlag.flag == key).first()
        if flag is None:
            raise BadRequest
        else:
            db.session.delete(flag)
            db.session.commit()
            return '', 204

fflag_blueprint.add_url_rule('/fflags', view_func=ListFFlags.as_view('list_fflags'))
fflag_blueprint.add_url_rule('/fflags/<key>', view_func=AlterFFLag.as_view('alter_fflag'))