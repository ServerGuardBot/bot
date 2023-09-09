from datetime import datetime
from json import JSONDecoder, JSONEncoder
from flask import Blueprint, request, jsonify
from flask.views import MethodView
from project import app, BotAPI, db
from project.server.models import Guild, GuildRoleConfig, GuildUser
from project.server.api.auth import get_user_auth

roles_blueprint = Blueprint('roles', __name__)

class AutoRoleConfig(MethodView):
    async def get(self, guild_id: str, unique_id: str=None):
        bot_auth = request.headers.get('authorization') == app.config.get("SECRET_KEY")
        if not bot_auth:
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == guild_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
        else:
            guild_user = None
        
        if guild_user is not None and guild_user.permission_level > 2 or bot_auth:
            if unique_id:
                role_config: GuildRoleConfig = GuildRoleConfig.query \
                    .filter(GuildRoleConfig.type == 'autorole') \
                    .filter(GuildRoleConfig.guild_id == guild_id) \
                    .filter(GuildRoleConfig.unique_id == unique_id) \
                    .first()
                
                if role_config:
                    return jsonify({
                        'id': role_config.unique_id,
                        'role': int(role_config.role_id),
                        'data': role_config.value,
                    }), 200
                else:
                    return 'Not Found', 404
            else:
                role_configs: list = GuildRoleConfig.query \
                    .filter(GuildRoleConfig.type == 'autorole') \
                    .filter(GuildRoleConfig.guild_id == guild_id)
                
                return jsonify({
                    'roles': [
                        {
                            'id': role_config.unique_id,
                            'role': int(role_config.role_id),
                            'data': role_config.value,
                        } for role_config in role_configs
                    ]
                }), 200
        else:
            return 'Forbidden', 403
    async def post(self, guild_id: str):
        bot_auth = request.headers.get('authorization') == app.config.get("SECRET_KEY")
        if not bot_auth:
            auth = get_user_auth()

            guild_user: GuildUser = GuildUser.query \
                .filter(GuildUser.guild_id == guild_id) \
                .filter(GuildUser.user_id == auth) \
                .first()
        else:
            guild_user = None
        
        if guild_user is not None and guild_user.permission_level > 2 or bot_auth:
            post_data: dict = request.get_json()
            role_id: int = post_data.get('role')
            has_roles: list = post_data.get('has_roles', []) # Roles that the user must have to be given this role
            has_all: bool = post_data.get('has_all', False) # If true, the user must have all of the roles in has_roles to be given this role
            not_has_roles: list = post_data.get('not_has_roles', []) # Roles that the user must not have to be given this role
            not_has_all: bool = post_data.get('not_has_all', False) # If true, the user must not have all of the roles in not_has_roles to be given this role

            if role_id is None:
                return 'Must include a role', 400
            if len(has_roles) == 0 and len(not_has_roles) == 0:
                # At least one of these must have role ids in them
                return 'Must include at least one role in the whitelist or blacklist', 400
            
            role_config: GuildRoleConfig = GuildRoleConfig(guild_id, role_id, 'autorole', {
                'has_roles': has_roles,
                'has_all': has_all,
                'not_has_roles': not_has_roles,
                'not_has_all': not_has_all,
            })

            db.session.add(role_config)
            db.session.commit()

            return jsonify({
                'autorole': {
                    'id': role_config.unique_id,
                    'role': role_config.role_id,
                    'data': role_config.value,
                }
            }), 201
        else:
            return 'Forbidden', 403
    async def patch(self, guild_id: str, unique_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            role_config: GuildRoleConfig = GuildRoleConfig.query \
                .filter(GuildRoleConfig.type == 'autorole') \
                .filter(GuildRoleConfig.guild_id == guild_id) \
                .filter(GuildRoleConfig.unique_id == unique_id) \
                .first()
            
            if role_config is None:
                return 'Not Found', 404

            post_data: dict = request.get_json()
            role_id: int = post_data.get('role')
            has_roles: list = post_data.get('has_roles') # Roles that the user must have to be given this role
            has_all: bool = post_data.get('has_all') # If true, the user must have all of the roles in has_roles to be given this role
            not_has_roles: list = post_data.get('not_has_roles') # Roles that the user must not have to be given this role
            not_has_all: bool = post_data.get('not_has_all') # If true, the user must not have all of the roles in not_has_roles to be given this role

            if role_id is not None:
                role_config.role_id = role_id
            if has_roles is not None:
                role_config.value['has_roles'] = has_roles
            if has_all is not None:
                role_config.value['has_all'] = has_all
            if not_has_roles is not None:
                role_config.value['not_has_roles'] = not_has_roles
            if not_has_all is not None:
                role_config.value['not_has_all'] = not_has_all
            
            if role_id is not None or has_roles is not None or has_all is not None or not_has_roles is not None or not_has_all is not None:
                db.session.add(role_config)
                db.session.commit()

                return jsonify({
                    'autorole': {
                        'id': role_config.unique_id,
                        'role': role_config.role_id,
                        'data': role_config.value,
                    }
                }), 200
            return 'No changes made', 400
        else:
            return 'Forbidden', 403
    async def delete(self, guild_id: str, unique_id: str):
        auth = get_user_auth()

        guild_user: GuildUser = GuildUser.query \
            .filter(GuildUser.guild_id == guild_id) \
            .filter(GuildUser.user_id == auth) \
            .first()
        
        if guild_user is not None and guild_user.permission_level > 2:
            role_config: GuildRoleConfig = GuildRoleConfig.query \
                .filter(GuildRoleConfig.type == 'autorole') \
                .filter(GuildRoleConfig.guild_id == guild_id) \
                .filter(GuildRoleConfig.unique_id == unique_id) \
                .first()
            
            if role_config is None:
                return 'Not Found', 404

            db.session.delete(role_config)
            db.session.commit()

            return '', 204
        else:
            return 'Forbidden', 403

roles_blueprint.add_url_rule('/autoroles/<string:guild_id>', view_func=AutoRoleConfig.as_view('autoroles'))
roles_blueprint.add_url_rule('/autoroles/<string:guild_id>/<string:unique_id>', view_func=AutoRoleConfig.as_view('autoroles_role'))