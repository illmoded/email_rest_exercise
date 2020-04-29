from datetime import datetime

from modules.extensions import db

recipents_rels = db.Table(
    'recipents',
    db.Column('email_id',
              db.Integer,
              db.ForeignKey('email.id'),
              primary_key=True),
    db.Column('recipent_id',
              db.Integer,
              db.ForeignKey('email_user.id'),
              primary_key=True))


class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pub_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    subject = db.Column(db.String)
    message = db.Column(db.String)
    status = db.Column(db.String)
    priority = db.Column(db.Integer)

    # one sender can have multiple emails
    sender = db.relationship("EmailUser", backref='sender_emails')
    sender_id = db.Column(db.Integer, db.ForeignKey('email_user.id'))

    # each mail can have multiple recipents
    recipents = db.relationship("EmailUser",
                                secondary=recipents_rels,
                                lazy='subquery',
                                backref=db.backref('recipent_emails',
                                                   lazy=True))

    # one email can have multiple attachments
    attachments = db.relationship("Attachment", backref='attachment_in_email')

    def __repr__(self):
        return f"Email {self.id}"


class EmailUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_address = db.Column(db.String)


class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_path = db.Column(db.String)
    name = db.Column(db.String)
    content_type = db.Column(db.String)
    email_id = db.Column(db.Integer, db.ForeignKey('email.id'), nullable=True)
