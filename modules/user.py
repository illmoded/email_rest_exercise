from flask import Blueprint, current_app, request
from flask_restful import Api, Resource
from webargs import fields, validate
from webargs.flaskparser import abort, parser, use_args, use_kwargs

from modules.database import EmailUser
from modules.extensions import db
from modules.validators import user_must_exist_in_db, user_must_not_exist_in_db

user_bp = Blueprint('user', __name__)
user_api = Api(user_bp)


class UserResource(Resource):
    @staticmethod
    def get_user(user_id):
        return EmailUser.query.get(user_id)

    def create_user(self, email):
        person = EmailUser(email_address=email)
        db.session.add(person)
        db.session.commit()
        return person

    def serialize_user(self, user):
        return user.email_address

    @use_kwargs(
        {'user_id': fields.Int(required=True, validate=user_must_exist_in_db)},
        location='view_args')
    def get(self, user_id):
        user = EmailUser.query.get(user_id)
        return self.serialize_user(user)

    @use_kwargs({
        'email':
        fields.Email(required=True, validate=user_must_not_exist_in_db)
    })
    def post(self, email):
        user = EmailUser(email_address=email)
        db.session.add(user)
        db.session.commit()
        return user.id

    @staticmethod
    def get_user(user_id):
        return EmailUser.query.get(user_id)


class UserListResource(UserResource):
    def get(self):
        users = EmailUser.query.all()
        return [self.serialize_user(user) for user in users]

    def post(self):
        raise NotImplementedError


@parser.error_handler
def handle_request_parsing_error(err, req, schema, *, error_status_code,
                                 error_headers):
    """
    webargs error handler that uses Flask-RESTful's abort function to return
    a JSON error response to the client.
    """
    abort(error_status_code, errors=err.messages)


user_api.add_resource(UserResource, '/user', '/user/<user_id>')
user_api.add_resource(UserListResource, '/users')
