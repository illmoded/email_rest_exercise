import uuid

from flask import Blueprint, current_app, request
from flask_mail import Message
from flask_restful import Api, Resource
from webargs import fields, validate
from webargs.flaskparser import abort, parser, use_args, use_kwargs

from modules.attachment import AttachmentResource
from modules.database import Email
from modules.extensions import db
from modules.extensions import mail as mailer
from modules.user import UserResource
from modules.validators import (attachment_must_exist_in_db,
                                attachment_must_not_be_connected_to_email,
                                email_must_exist_in_db, user_must_exist_in_db)

mail_bp = Blueprint('mail', __name__)
mail_api = Api(mail_bp)


class MailResource(Resource):
    def connect_attachments_to_email(self, email, attachments_ids):
        email_id = email.id
        if attachments_ids:
            for attachments_id in attachments_ids:
                attachment = AttachmentResource.get_attachment(attachments_id)
                if attachment:
                    attachment.email_id = email_id
            db.session.commit()

    def save_message(self, msg: Message):
        subject = msg.subject
        body = msg.body
        status = msg.status
        priority = msg.priority
        sender_id = msg.sender_id

        message = Email(subject=subject,
                        message=body,
                        status=status,
                        priority=priority,
                        sender_id=sender_id)

        recipents_ids = msg.recipents_ids
        for recipent_id in recipents_ids:
            recipent = UserResource.get_user(recipent_id)
            message.recipents.append(recipent)

        db.session.add(message)
        db.session.commit()

        self.connect_attachments_to_email(message, msg.attachments_ids)
        return message.id

    def send_message(self, msg: Message, extra_headers, attachment_ids):
        try:
            if attachment_ids:
                files = self.get_attachments(attachment_ids)
                if files:
                    for file in files:
                        with current_app.open_resource(file['filepath']) as fp:
                            msg.attach(filename=file['name'],
                                       content_type=file['content_type'],
                                       data=fp.read)

            msg.extra_headers = extra_headers
            mailer.send(msg)
        except ConnectionRefusedError:
            print('Could not connect to SMTP server')
            status = 'failed'
        except Exception as e:
            print(f'Send error: {e}')
            status = 'failed'
        else:
            status = 'sent'
        finally:
            return status

    def get_headers(self, priority=None):
        headers = {}
        if priority:
            headers['X-Priority'] = priority
        return headers

    def send_saved_email(self, email):
        # create msg instance from db data
        attachments_ids = email.attachments
        subject = email.subject
        body = email.message
        priority = email.priority

        sender = email.sender.email_address
        recipents = [recipent.email_address for recipent in email.recipents]

        msg = Message(subject=subject,
                      recipients=recipents,
                      body=body,
                      sender=sender)

        headers = self.get_headers(priority=priority)
        status = self.send_message(msg=msg,
                                   extra_headers=headers,
                                   attachment_ids=attachments_ids)
        email.status = status
        db.session.commit()
        return status

    def serialize_email(self, email):
        # this can be done with marshammlow in production environment
        d = {}
        d['id'] = email.id
        d['date'] = email.pub_date.strftime("%m/%d/%Y, %H:%M:%S")
        d['subject'] = email.subject
        d['message'] = email.message
        d['status'] = email.status
        return d


class Mail(MailResource):
    @use_kwargs(
        {
            'email_id': fields.Int(required=True,
                                   validate=email_must_exist_in_db)
        },
        location='view_args')
    def get(self, email_id):
        # get email details
        email = Email.query.get(email_id)
        return self.serialize_email(email)

    mail_args = {
        'receipents':
        fields.DelimitedList(fields.Integer(validate=user_must_exist_in_db),
                             required=True),
        'sender':
        fields.Integer(validate=user_must_exist_in_db, required=True),
        'subject':
        fields.String(required=True),
        'message':
        fields.String(required=True),
        'attachments':
        fields.DelimitedList(fields.Int(validate=[
            attachment_must_exist_in_db,
            attachment_must_not_be_connected_to_email
        ]),
                             required=False),
        'send_now':
        fields.Boolean(required=False),
        'priority':
        fields.Int(required=False,
                   validate=validate.Range(1, 5))  # 1 is highest, 5 is lowest
    }

    @use_kwargs(mail_args, location='json')
    def post(self,
             receipents,
             sender,
             subject,
             message,
             attachments=None,
             send_now=False,
             priority=None):
        """
        http POST localhost:8887/email message='asd' subject='asd' sender_email='sendermail@a.pl'\
             receipents_emails='firstmail@a.pl,secondmail@a.pl' send_now=true
        create new email
        """
        sender_email = UserResource.get_user(sender).email_address
        receipents_emails = [
            UserResource.get_user(receipent).email_address
            for receipent in receipents
        ]

        msg = Message(subject=subject,
                      recipients=receipents_emails,
                      body=message,
                      sender=sender_email)

        if send_now:
            headers = self.get_headers(priority=priority)
            status = self.send_message(msg=msg,
                                       extra_headers=headers,
                                       attachment_ids=attachments)
        else:
            status = 'pending'

        msg.attachments_ids = attachments
        msg.priority = priority
        msg.status = status
        msg.sender_id = sender
        msg.recipents_ids = receipents

        message_id = self.save_message(msg)
        return {'id': message_id, 'status': status}


class MailList(MailResource):
    def get(self):
        """
        get list of all emails in the system
        http localhost:8887/emails
        """
        # possibly add pagination/limits
        return [self.serialize_email(email) for email in Email.query.all()]

    def post(self):
        """
        send all pending
        http POST localhost:8887/emails
        """
        pending_emails = Email.query.filter_by(status='pending').all()
        # as I am not sending any emails I do not care about failed emails
        # otherwise query 'failed' here as well
        if not pending_emails:
            return {'status': 'no pending mails'}
        for email in pending_emails:
            # this could be sent to queue / async code (not in flask)
            status = self.send_saved_email(email)
        return {'status': 'ok'}


@parser.error_handler
def handle_request_parsing_error(err, req, schema, *, error_status_code,
                                 error_headers):
    """
    webargs error handler that uses Flask-RESTful's abort function to return
    a JSON error response to the client.
    """
    abort(error_status_code, errors=err.messages)


mail_api.add_resource(MailList, '/emails')
mail_api.add_resource(Mail, '/email/<email_id>', '/email')
