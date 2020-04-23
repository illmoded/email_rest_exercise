import uuid

from flask import Blueprint, current_app, request
from flask_mail import Message
from flask_restful import Api, Resource
from webargs import fields, validate
from webargs.flaskparser import abort, parser, use_args, use_kwargs

from database import Attachment as AttachmentModel
from database import Email, EmailUser
from extensions import db
from extensions import mail as mailer
from validators import (attachment_must_exist_in_db,
                        attachment_must_not_be_connected_to_email,
                        email_must_exist_in_db)

mail_bp = Blueprint('mail', __name__)
mail_api = Api(mail_bp)


class MailResource(Resource):
    def get_user(self, email):
        return EmailUser.query.filter_by(email_address=email).first()

    def create_user(self, email):
        person = EmailUser(email_address=email)
        db.session.add(person)
        db.session.commit()
        return person

    def get_user_id(self, email):
        sender = self.get_user(email)
        if not sender:
            sender = self.create_user(email=email)
        return sender.id

    def get_users_ids(self, emails):
        recipents_ids = []
        for email in emails:
            recipent = self.get_user(email=email)
            if not recipent:
                recipent = self.create_user(email=email)
            recipents_ids.append(recipent.id)
        return recipents_ids

    def connect_attachments_to_email(self, email, attachments_ids):
        email_id = email.id
        if attachments_ids:
            for attachments_id in attachments_ids:
                attachment = AttachmentModel.query.get(attachments_id)
                if attachment:
                    attachment.email_id = email_id
            db.session.commit()

    def save_message(self, msg: Message):
        subject = msg.subject
        body = msg.body
        status = msg.status
        priority = msg.priority
        sender_id = self.get_user_id(msg.sender)

        message = Email(subject=subject,
                        message=body,
                        status=status,
                        priority=priority,
                        sender_id=sender_id)

        recipents_ids = self.get_users_ids(msg.recipients)
        for recipent_id in recipents_ids:
            recipent = EmailUser.query.get(recipent_id)
            message.recipents.append(recipent)

        db.session.add(message)
        db.session.commit()

        self.connect_attachments_to_email(message, msg.attachments_ids)
        return message.id

    def get_attachments(self, attachment_ids):
        files = []
        for attachment_id in attachment_ids:
            attachment = AttachmentModel.query.get(attachment_id)
            if attachment:
                file = {
                    'filepath': attachment.file_path,
                    'name': attachment.name,
                    'content_type': attachment.content_type
                }
                files.append(file)
        return files

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
        if email:
            return self.serialize_email(email)
        else:
            return None, 404

    mail_args = {
        'receipents_emails':
        fields.DelimitedList(fields.Email(), required=True),
        'sender_email':
        fields.Email(required=True),
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
        fields.Int(required=False)
    }

    @use_kwargs(mail_args, location='json')
    def post(self,
             receipents_emails,
             sender_email,
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
        sender_id = self.get_user_id(sender_email)
        recipent_ids = self.get_users_ids(receipents_emails)

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


class Attachment(MailResource):
    def save_attachment(self, file):
        file_name = str(uuid.uuid4())
        file_path = f'attachments/{file_name}'
        file_path = file.save(file_path)
        attachment = AttachmentModel(file_path=file_path,
                                     name=file_name,
                                     content_type=file.content_type)
        db.session.add(attachment)
        db.session.commit()
        return attachment.id

    @use_kwargs({
        'attachment': fields.Field(required=True),
    },
                location='files')
    def post(self, attachment):
        """ 
        for example send file by httpie:
             http -f POST localhost:8887/file attachment@~/image.jpg
        this can be json if you are willing to send files for example as base64
        returns file id
        """
        # here can validate attachment, resize, scan etc
        file_id = self.save_attachment(attachment)
        return {'file_id': file_id}


@parser.error_handler
def handle_request_parsing_error(err, req, schema, *, error_status_code,
                                 error_headers):
    """
    webargs error handler that uses Flask-RESTful's abort function to return
    a JSON error response to the client.
    """
    abort(error_status_code, errors=err.messages)


mail_api.add_resource(Attachment, '/file')
mail_api.add_resource(MailList, '/emails')
mail_api.add_resource(Mail, '/email/<email_id>', '/email')
