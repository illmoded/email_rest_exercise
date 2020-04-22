from flask import Blueprint, current_app, request
from flask_mail import Message
from flask_restful import Api, Resource
from webargs import fields, validate
from webargs.flaskparser import abort, parser, use_args, use_kwargs

from database import Email, EmailUser, Attachment
from extensions import db
from extensions import mail as mailer
from validators import email_must_exist_in_db

mail_bp = Blueprint('mail', __name__)
mail_api = Api(mail_bp)


class MailResource(Resource):
    def get_user(self, email):
        return EmailUser.query.get(email_address=email)

    def create_user(self, email, session):
        person = EmailUser(email_address=email)
        session.add(person)
        session.commit()
        return person

    def get_user_id(self, sender_email, session):
        sender = self.get_user(sender_email)
        if not sender:
            sender = self.create_user(email=sender_email, session=session)
        return sender.id

    def get_users_ids(self, receipents_emails, session):
        recipents_ids = []
        for recipent_email in receipents_emails:
            recipent = self.get_user(email=recipent_email, session=session)
            if not recipent:
                recipent = self.create_user(email=recipent_email,
                                            session=session)
            recipents_ids.append(recipent.id)
        return recipents_ids

    def save_message(self, msg: Message, session):
        # here exteact data from Message instance
        message = Email()
        # TODO: add m2m
        session.add(message)
        session.commit()

    def send_message(self, msg: Message, extra_headers):
        try:
            msg.extra_headers = extra_headers
            msg.send()
        except:
            status = 'failed'
        else:
            status = 'sent'
        finally:
            return status

    def send_saved_email(self, email, session):
        # create msg instance from db data
        msg = Message()
        new_status = self.send_message(msg)
        email.status = new_status
        session.commit()


class Mail(MailResource):
    @use_kwargs(
        {
            'email_id': fields.Int(required=True,
                                   validate=email_must_exist_in_db)
        },
        location='view_args')
    def get(self, email_id):
        # get email details
        print(email_id)
        email = Email.query.get(email_id)
        return email

    @use_kwargs({
        'receipents_emails': fields.DelimitedList(fields.Email()),
        'sender_email': fields.Email(),
        'subject': fields.String(),
        'message': fields.String(),
        'attachments': fields.Field(location="files"),
        'send_now': fields.Boolean(required=False),
        'priority': fields.Int(required=False)
    })
    def post(
        self,
        receipents_emails,
        sender_email,
        subject,
        message,
        #  attachments=None,
        send_now=False,
        priority=None):  # TODO: check priority value meanings
        # create new email

        # if attachments - save to filesystem and save paths in the database
        with db.session as session:
            sender_id = self.get_user_id(sender_email, session)
            recipent_ids = self.get_users_ids(receipents_emails, session)
            msg = Message()

            if send_now:
                if priority:
                    headers = {'X-Priority': priority}
                else:
                    headers = None
                status = self.send_message(msg=msg, extra_headers=headers)
            else:
                status = 'pending'

            self.save_message(msg, session)


class MailList(MailResource):
    def get(self):
        # get list of all emails in the system
        # possibly add pagination
        emails = Email.query.all()
        return emails

    def post(self):
        # send all pending
        with db.session as session:
            pending_emails = Email.query.filter_by(status='pending').all()
            for email in pending_emails:
                # this could be sent to queue / async code (not in flask)
                self.send_saved_email(email, session)
        return 'ok'


@parser.error_handler
def handle_request_parsing_error(err, req, schema, *, error_status_code,
                                 error_headers):
    """
    webargs error handler that uses Flask-RESTful's abort function to return
    a JSON error response to the client.
    """
    abort(error_status_code, errors=err.messages)


mail_api.add_resource(MailList, '/emails')
mail_api.add_resource(Mail, '/email/<email_id>')
