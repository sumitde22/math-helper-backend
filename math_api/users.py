from flask import Blueprint, abort, jsonify, request
# allows cursor to return data in dict format instead of tuple
from psycopg2.extras import RealDictCursor
# library for creating auth tokens, restricting endpoints to authenticated users
from flask_jwt_extended import jwt_required, current_user
from .db import get_db_connection

user_info_blueprint = Blueprint('users', __name__, url_prefix='/api/users')

# return username for given id
def get_user(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT id, username FROM user_info WHERE id=%s;', (user_id,))
    user = cursor.fetchone()
    cursor.close()
    return user

# delete user with given id
def remove_user(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    # removes references to user across all tables
    # see delete_user in util.sql for more info
    cursor.execute('call delete_user(%s);', (user_id,))
    cursor.close()

# remove all evidence of problem attempts by user
def reset_user(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor()
    # remove all attempts and reset all assignments for problems scheduled in future
    # see reset_user in util.sql
    cursor.execute('call reset_user(%s);', (user_id,))
    cursor.close()

# get day-by-day problems solved and attempted by yser
def get_user_statistics(user_id):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT attempt_date, COUNT(*) filter (where "correct") AS solved, COUNT(*) AS attempts FROM user_attempt_log WHERE user_id=%s '
    'GROUP BY attempt_date ORDER BY attempt_date', (user_id,))
    statistics = cursor.fetchall()
    cursor.close()
    return statistics

# get day-by-day problems solved and attempted for this user
@user_info_blueprint.route('/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user_info(user_id):
    # if token sent is for user not specified in url, return error
    if current_user['id'] != user_id:
        abort(401, description=f'You do not have access to this user.')

    # if requested user doesn't exist, return error
    requested_user = get_user(user_id)
    if requested_user == None:
        abort(404, description=f'User with id {user_id} does not exist')
    # if user exists, send statistics for that user
    else:
        statistics = get_user_statistics(user_id)
        return jsonify(statistics)

# delete user specified in endpoint
@user_info_blueprint.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    # if token sent isn't for user specified in url, return error
    if current_user['id'] != user_id:
        abort(401, description=f'You do not have access to this user.')

    # if requested user doesn't exist, return error
    requested_user = get_user(user_id)
    if requested_user == None:
        abort(404, description=f'User with id {user_id} does not exist')
    # if it does exist, remove all references to user from db and send appropriate confirmation
    else:
        remove_user(user_id)
        return {"msg": f"User with id {user_id} successfully removed"}

# endpoint that allows user to reset statistics/intervals
@user_info_blueprint.route('/<int:user_id>', methods=['PUT'])
@jwt_required()
def modify_user(user_id):
    # if token sent isn't for user specified in url, return error
    if current_user['id'] != user_id:
        abort(401, description=f'You do not have access to this user.')

    # if requested user doesn't exist, return error
    requested_user = get_user(user_id)
    if requested_user == None:
        abort(404, description=f'User with id {user_id} does not exist')
    
    # the only thing that can be modified is "resetting" a user to erase previous attempts
    # this is achieved by sending a reset tag in json
    payload = request.get_json()
    try:
        should_reset = payload['reset']
    except:
        should_reset = False

    # if correct user and payload sent, remove all attempts by user and reschedule all problems with initial intervals
    if should_reset:
        reset_user(user_id)
        return {'msg': f'User with id {user_id} reset'}
    else:
        return {'msg': 'No changes made'}

