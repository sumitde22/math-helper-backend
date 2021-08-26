import os

from flask import Flask
from flask_cors import CORS
from dotenv import load_dotenv
from .db import init_app as initialize_db_for_app
from .auth import jwt, auth_blueprint, token_parse_error, generate_error_handler
from .problems import problems_blueprint
from .users import user_info_blueprint
from jwt.exceptions import DecodeError
from datetime import timedelta

# application factory for app that loads libraries and url handlers
def create_app():
    # initialize Flask app and point app to front end build
    app = Flask(__name__, static_folder='../build', static_url_path='/')

    # load environment variables into os.environ 
    # read from .env in development, heroku config vars in productions
    load_dotenv()
    
    # initialize config variables for app that can be referenced throughout project
    # secret to be used when creating auth tokens
    app.config["JWT_SECRET_KEY"] = os.environ['SECRET']
    # postgres connection url
    app.config["DATABASE_URL"] = os.environ['DATABASE_URL']
    # development or production mode
    # main differences are a) CORS allowed in dev but not prod and b) ssl database connection in prod but not dev
    app.config["FLASK_ENV"] = os.environ['FLASK_ENV']
    # authentication given to user is valid for 1 hour before needed to be refreshed
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)
    app.config["TOKEN_EXPIRES_MILLISECONDS"] = 3600000

    # cross-origin requests allowed in development for testing purposes
    if app.config["FLASK_ENV"] == "development":
        CORS(app)

    # load db connection into global variable to be used throughout app
    initialize_db_for_app(app)

    # load authentication library to only allow requests with valid tokens
    jwt.init_app(app)

    # point base url to point to frontend homepage
    @app.route('/')
    def index():
        return app.send_static_file('index.html')
    
    # endpoints that aren't matched to api are sent frontend
    # allows non-homepage links in frontend to be displayed
    @app.errorhandler(404)
    def not_found(e):
        return app.send_static_file('index.html')
    
    # load authentication routes onto app
    app.register_blueprint(auth_blueprint)

    # load problem handling routes onto app
    app.register_blueprint(problems_blueprint)
    
    # load user handling routes onto app
    app.register_blueprint(user_info_blueprint)

    # catch errors thrown by endpoints and send consistant error message format in json
    app.register_error_handler(400, generate_error_handler(400))
    app.register_error_handler(401, generate_error_handler(401))
    app.register_error_handler(405, generate_error_handler(405))
    app.register_error_handler(409, generate_error_handler(409))
    app.register_error_handler(DecodeError, token_parse_error)
    
    return app
