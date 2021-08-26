import psycopg2
import click
from flask import g, current_app
from flask.cli import with_appcontext

# returns connection to postgres db
# on app startup, create connection and store in global variable
def get_db_connection():
    if 'db' not in g:
        # connect not using ssl in development, using ssl in production
        if current_app.config["FLASK_ENV"] == "development":
            connection = psycopg2.connect(current_app.config["DATABASE_URL"])
        else:
            connection = psycopg2.connect(current_app.config["DATABASE_URL"], sslmode='require')
        connection.set_session(autocommit=True)
        # only creates connection once and saves it globally
        g.db = connection
    return g.db

# close db connection when app shut down
def close_db_connection(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# create db connection on app startup
def init_db():
    get_db_connection()

@click.command('init-db')
@with_appcontext
def init_db_command():
    init_db()
    click.echo('Initialized database state.')

def init_app(app):
    app.teardown_appcontext(close_db_connection)
    app.cli.add_command(init_db_command)



