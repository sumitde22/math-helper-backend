from flask import (
    Blueprint, request, abort
)
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, current_user, jwt_required
from .db import get_db_connection
from .problems import assign_daily_problems
import psycopg2

jwt = JWTManager()
auth_blueprint = Blueprint('auth', __name__, url_prefix='/api/auth')

def create_user(username, password):
    user = None
    try:
        db_connection = get_db_connection()
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute('SELECT * FROM create_user( %s , %s );', (username, generate_password_hash(password)))
        user = cursor.fetchone()
        return user
    except psycopg2.Error:
        raise RuntimeError(f'Username {username} is already taken')
    finally:
        cursor.close()

def get_user(username):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT id, username FROM user_info WHERE username=%s;', (username,))
    user = cursor.fetchone()
    cursor.close()
    return user

def check_password_correct(user_id, request_password):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT password_hash FROM user_info WHERE id=%s;', (user_id,))
    password_hash = cursor.fetchone()['password_hash']
    cursor.close()
    return check_password_hash(password_hash, request_password)

@jwt.user_identity_loader
def user_identity_lookup(user):
    return user['username']

@jwt.user_lookup_loader
def user_lookback_callback(_jwt_header, jwt_data):
    identity  = jwt_data['sub']
    user = get_user(identity)
    return user

@auth_blueprint.route('/register', methods=['POST'])
def register():
    try:
        user_data = request.get_json()
        username = user_data['username']
        password = user_data['password']
    except (KeyError, TypeError):
        abort(400, description = 'Request must contain username and password in json format')
    
    if not username or not password:
        abort(400, description = 'Please submit both username and password')
    elif len(username) < 3:
        abort(400, description = 'Invalid username. Username needs to be at least 3 characters long.')
    elif '/' in username or '?' in username or '&' in username:
        abort(400, description = 'Invalid username. Username cannot contain /, ?, or & character.')
    elif not password or len(password) < 7:
        abort(400, description = 'Invalid password. Password needs to be at least 7 characters long.')

    try:
        user = create_user(username, password)
        return user 
    except RuntimeError as error:
        abort(409, description = error.args[0])

@auth_blueprint.route('/login', methods=['POST'])
def login():
    try:
        user_data = request.get_json()
        request_username = user_data['username']
        request_password = user_data['password']
    except (KeyError, TypeError):
        abort(400, description = 'Request must contain username and password in json format')
    
    user = get_user(request_username)
    if user == None:
        abort(404, description = f'User {request_username} does not exist')
    user_id = user['id']
    username = user['username']
    password_correct = check_password_correct(user_id, request_password)
    if not password_correct:
        abort(401, description = f'Password incorrect for user {username}')
    
    assign_daily_problems(user_id)

    access_token = create_access_token(identity=user)
    refresh_token = create_refresh_token(identity=user)
    return {"id": user_id, "username": username, "access_token": access_token, "refresh_token": refresh_token, "token_expires": 3600000}

@auth_blueprint.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    access_token = create_access_token(identity=current_user)
    refresh_token = create_refresh_token(identity=current_user)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_expires": 3600000}

def generate_error_handler(error_code):
    def error_handler(e):
        return {"msg": str(e)}, error_code
    return error_handler

def token_parse_error(e):
    return "Token was of invalid format and could not be parsed", 401