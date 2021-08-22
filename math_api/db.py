import psycopg2
import click
from flask import g, current_app
from flask.cli import with_appcontext

def get_db_connection():
    if 'db' not in g:
        connection = psycopg2.connect(host="localhost", database="math_app_database", user="math_app_user", password="CR7madridjayriehayford18")
        connection.set_session(autocommit=True)
        g.db = connection
    return g.db

def close_db_connection(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    connection = get_db_connection()
    #cursor = connection.cursor()
    #with current_app.open_resource('initialize_db_state.sql') as f:
    #    cursor.execute(f.read())
    #cursor.close()

@click.command('init-db')
@with_appcontext
def init_db_command():
    init_db()
    click.echo('Initialized database state.')

def init_app(app):
    app.teardown_appcontext(close_db_connection)
    app.cli.add_command(init_db_command)



