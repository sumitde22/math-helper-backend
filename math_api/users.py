from flask import Blueprint, abort, jsonify, request
from psycopg2.extras import RealDictCursor
from flask_jwt_extended import jwt_required, current_user
from .db import get_db_connection

user_info_blueprint = Blueprint('users', __name__, url_prefix='/api/users')

def get_user(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT id, username FROM user_info WHERE id=%s;', (user_id,))
    user = cursor.fetchone()
    cursor.close()
    return user

def remove_user(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('call delete_user(%s);', (user_id,))
    cursor.close()

def reset_user(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    cursor.execute('call reset_user(%s);', (user_id,))
    cursor.close()

def get_user_statistics(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT attempt_date, COUNT(*) filter (where "correct") AS solved, COUNT(*) AS attempts FROM user_attempt_log WHERE user_id=%s '
    'GROUP BY attempt_date ORDER BY attempt_date', (user_id,))
    statistics = cursor.fetchall()
    cursor.close()
    return statistics

@user_info_blueprint.route('/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_info(user_id):
    if current_user['id'] != user_id:
        abort(401, description=f'You do not have access to this user.')

    requested_user = get_user(user_id)
    if requested_user == None:
        abort(404, description=f'User with id {user_id} does not exist')
    else:
        statistics = get_user_statistics(user_id)
        return jsonify(statistics)

@user_info_blueprint.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    if current_user['id'] != user_id:
        abort(401, description=f'You do not have access to this user.')

    requested_user = get_user(user_id)
    if requested_user == None:
        abort(404, description=f'User with id {user_id} does not exist')
    else:
        remove_user(user_id)
        return {"msg": f"User with id {user_id} successfully removed"}

@user_info_blueprint.route('/<int:user_id>', methods=['PUT'])
@jwt_required()
def modify_user(user_id):
    if current_user['id'] != user_id:
        abort(401, description=f'You do not have access to this user.')

    requested_user = get_user(user_id)
    if requested_user == None:
        abort(404, description=f'User with id {user_id} does not exist')
    
    payload = request.get_json()
    should_reset = payload['reset']
    if should_reset:
        reset_user(user_id)
        return {'msg': f'User with id {user_id} reset'}
    else:
        return {'msg': 'No changes made'}

