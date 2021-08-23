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

def create_app():
    app = Flask(__name__, static_folder='../build', static_url_path='/', instance_relative_config=True)
    CORS(app)

    load_dotenv()
    
    app.config["SECRET_KEY"] = os.environ['SECRET']
    app.config["JWT_SECRET_KEY"] = os.environ['SECRET']
    app.config["DATABASE_URL"] = os.environ['DATABASE_URL']
    app.config["FLASK_ENV"] = os.environ['FLASK_ENV']
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
    app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

    initialize_db_for_app(app)
    jwt.init_app(app)

    @app.route('/')
    def index():
        return app.send_static_file('index.html')
    
    @app.errorhandler(404)
    def not_found(e):
        return app.send_static_file('index.html')

    app.register_blueprint(auth_blueprint)
    app.register_blueprint(problems_blueprint)
    app.register_blueprint(user_info_blueprint)

    app.register_error_handler(400, generate_error_handler(400))
    app.register_error_handler(401, generate_error_handler(401))
    app.register_error_handler(405, generate_error_handler(405))
    app.register_error_handler(409, generate_error_handler(409))
    app.register_error_handler(DecodeError, token_parse_error)
    
    return app
