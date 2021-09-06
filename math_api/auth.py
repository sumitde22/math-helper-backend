# request allows you to access data sent in request, current_app is allows you to access config used in global app
from flask import (
    Blueprint, request, abort, current_app
)
from psycopg2 import Error
# allows cursor to return data in dict format instead of tuple
from psycopg2.extras import RealDictCursor
# library for hashing/checking passwords
from werkzeug.security import check_password_hash, generate_password_hash
# library for creating auth tokens, restricting endpoints to authenticated users
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, current_user, jwt_required
from .db import get_db_connection
from .problems import assign_daily_problems

# initialize authentication library for endpoints
jwt = JWTManager()
# initalize blueprint to load authentication route handlers onto
auth_blueprint = Blueprint('auth', __name__, url_prefix='/api/auth')

# add user with given details to database
# throw error if username is taken
def create_user(username, password):
    user = None
    try:
        db_connection = get_db_connection()
        cursor = db_connection.cursor(cursor_factory=RealDictCursor)
        # try insert, raise error if it doesn't work
        cursor.execute('INSERT INTO user_info(username, password_hash) VALUES (%s, %s) RETURNING user_info.id, user_info.username;', (username, generate_password_hash(password)))
        user = cursor.fetchone()
        return user
    except Error:
        raise RuntimeError(f'Username {username} is already taken')
    finally:
        cursor.close()

# retrieve user info for given username, returns None if one doesn't exist
# used more for ensuring a user exists
def get_user(username):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT id, username FROM user_info WHERE username=%s;', (username,))
    user = cursor.fetchone()
    cursor.close()
    return user

# compare password sent to the one stored in the db, called when user confirmed to exist
# returns boolean
def check_password_correct(user_id, request_password):
    db_connection = get_db_connection()
    cursor = db_connection.cursor(cursor_factory=RealDictCursor)
    cursor.execute('SELECT password_hash FROM user_info WHERE id=%s;', (user_id,))
    password_hash = cursor.fetchone()['password_hash']
    cursor.close()
    return check_password_hash(password_hash, request_password)

# part of jwt library, serves to uniquely identify user 
@jwt.user_identity_loader
def user_identity_lookup(user):
    return user['username']

# part of jwt library, loads user retrieved from token into current_user variable used throughout app
@jwt.user_lookup_loader
def user_lookback_callback(_jwt_header, jwt_data):
    identity  = jwt_data['sub']
    user = get_user(identity)
    return user

# endpoint for creating new users
@auth_blueprint.route('/register', methods=['POST'])
def register():
    # expects information to be sent in json format, retrieve info from request object
    try:
        user_data = request.get_json()
        username = user_data['username']
        password = user_data['password']
    except (KeyError, TypeError):
        abort(400, description = 'Request must contain username and password in json format')
    
    # throw errors with descriptive messages if given invalid username or password
    if not username or not password:
        abort(400, description = 'Please submit both username and password')
    elif len(username) < 3:
        abort(400, description = 'Invalid username. Username needs to be at least 3 characters long.')
    elif '/' in username or '?' in username or '&' in username:
        abort(400, description = 'Invalid username. Username cannot contain /, ?, or & character.')
    elif not password or len(password) < 7:
        abort(400, description = 'Invalid password. Password needs to be at least 7 characters long.')

    # add user to database if username doesn't already exist
    try:
        user = create_user(username, password)
        return user 
    except RuntimeError as error:
        abort(409, description = error.args[0])

# endpoint for giving auth token to valid user
@auth_blueprint.route('/login', methods=['POST'])
def login():
    # expects information to be sent in json format, retrieve info from request object
    try:
        user_data = request.get_json()
        request_username = user_data['username']
        request_password = user_data['password']
    except (KeyError, TypeError):
        abort(400, description = 'Request must contain username and password in json format')
    
    # throw error if user doesn't exist
    user = get_user(request_username)
    if user == None:
        abort(400, description = f'User {request_username} does not exist')
    
    # throw error if password given doesn't match hash stored in db
    user_id = user['id']
    username = user['username']
    password_correct = check_password_correct(user_id, request_password)
    if not password_correct:
        abort(401, description = f'Password incorrect for user {username}')
    
    # user is authenticated, so make sure their daily problems are assigned for today
    assign_daily_problems(user_id)

    # create tokens that user need to send to access api information
    access_token = create_access_token(identity=user)
    refresh_token = create_refresh_token(identity=user)

    # return all relevant auth info to user
    return {"id": user_id, "username": username, "access_token": access_token, "refresh_token": refresh_token, "token_expires": current_app.config['TOKEN_EXPIRES_MILLISECONDS']}

# endpoint for refetch token when original expires
@auth_blueprint.route('/refresh', methods=['POST'])
# only processes refresh tokens, throws error otherwise
@jwt_required(refresh=True)
def refresh():
    access_token = create_access_token(identity=current_user)
    refresh_token = create_refresh_token(identity=current_user)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_expires": current_app.config['TOKEN_EXPIRES_MILLISECONDS']}

# generates a function that : catches all errors of given status code and sends error message in consistent format
def generate_error_handler(error_code):
    def error_handler(e):
        return {"msg": str(e)}, error_code
    return error_handler

# to be used to handle DecodeError thrown by werkzeug when token can't be parsed
def token_parse_error(e):
    return "Token was of invalid format and could not be parsed", 401