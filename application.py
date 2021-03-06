import os

from flask import Flask

from modules.extensions import db, mail
from modules.mail import mail_bp
from modules.user import user_bp
from modules.attachment import attachment_bp


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        # default config
        SECRET_KEY='dev',
        SQLALCHEMY_DATABASE_URI='sqlite:///' + os.getcwd() +
        '/database.db',  # in prod use ENV instead of cwd
        MAIL_SERVER='localhost',
        MAIL_PORT=25,
        MAIL_USE_TLS=False,
        MAIL_USE_SSL=False,
        MAIL_DEBUG=app.debug,
        MAIL_USERNAME=None,
        MAIL_PASSWORD=None,
        MAIL_DEFAULT_SENDER=None,
        MAIL_MAX_EMAILS=None,
        MAIL_SUPPRESS_SEND=app.testing,
        MAIL_ASCII_ATTACHMENTS=False)

    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:  # update config using test_config
        app.config.from_mapping(test_config)

    db.init_app(app)
    mail.init_app(app)

    with app.app_context():
        db.create_all()  # create database with app context
        app.register_blueprint(mail_bp)
        app.register_blueprint(user_bp)
        app.register_blueprint(attachment_bp)

    return app
