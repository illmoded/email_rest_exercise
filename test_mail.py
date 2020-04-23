import os

import pytest

from application import create_app
from database import Attachment, Email, EmailUser
from extensions import db as _db
from extensions import mail

TESTDB = 'test_project.db'
TESTDB_PATH = os.path.join(os.getcwd(), TESTDB)
TEST_DATABASE_URI = 'sqlite:///' + TESTDB_PATH


@pytest.fixture(scope='session')
def app(request):
    settings_override = {
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': TEST_DATABASE_URI,
        'MAIL_SUPPRESS_SEND': True
    }
    app = create_app(test_config=settings_override)

    ctx = app.app_context()
    ctx.push()

    def teardown():
        ctx.pop()

    request.addfinalizer(teardown)
    return app


@pytest.fixture(scope='session')
def db(app, request):
    if os.path.exists(TESTDB_PATH):
        os.unlink(TESTDB_PATH)

    def teardown():
        _db.drop_all()
        os.unlink(TESTDB_PATH)

    _db.app = app
    _db.create_all()

    request.addfinalizer(teardown)
    return _db


@pytest.fixture(scope='function')
def session(db, request):
    connection = db.engine.connect()
    transaction = connection.begin()

    options = dict(bind=connection, binds={})
    session = db.create_scoped_session(options=options)

    db.session = session

    def teardown():
        transaction.rollback()
        connection.close()
        session.remove()

    request.addfinalizer(teardown)
    return session


@pytest.fixture(scope='function')
def client(app, session):
    return app.test_client()


# end of fixtures


def test_add_user(session):
    user = EmailUser(email_address='p@p.p')
    session.add(user)
    session.commit()
    assert user.id > 0


def test_get_all_emails_empty(client):
    res = client.get('/emails')
    assert res.json == []


def test_get_all_emails(session, client):
    email1 = Email()
    session.add(email1)
    email2 = Email()
    session.add(email2)
    session.commit()
    assert email1.id == 1
    assert email2.id == 2
    res = client.get('/emails')
    assert len(res.json) == 2


def test_get_email_status(session, client):
    email1 = Email(status='sent')
    session.add(email1)
    session.commit()
    res = client.get('/email/1')
    assert res.json.get('status') == 'sent'


def test_send_email(client):
    res = client.post('/email',
                      json={
                          'message': 'asd',
                          'subject': 'asd',
                          'sender_email': 'asd@asd.pl',
                          'receipents_emails': 'asd@asd.pl',
                          'send_now': True
                      })
    assert res.json.get('status') == 'sent'
    sent_emails = Email.query.filter_by(status='sent').all()
    assert len(sent_emails) == 1


def test_add_pending_mails(client):
    for i in range(5):
        client.post('/email',
                    json={
                        'message': 'asd',
                        'subject': 'asd',
                        'sender_email': 'asd@asd.pl',
                        'receipents_emails': 'asd@asd.pl',
                        'send_now': False
                    })
    res = client.get('/emails')
    assert len(res.json) == 5
    sent_emails = Email.query.filter_by(status='sent').all()
    assert len(sent_emails) == 0
    pending_emails = Email.query.filter_by(status='pending').all()
    assert len(pending_emails) == 5


def test_send_all_pending(client):
    for i in range(5):
        client.post('/email',
                    json={
                        'message': 'asd',
                        'subject': 'asd',
                        'sender_email': 'asd@asd.pl',
                        'receipents_emails': 'asd@asd.pl',
                        'send_now': False
                    })
    res = client.post('/emails')
    assert res.json.get('status') == 'ok'
    sent_emails = Email.query.filter_by(status='sent').all()
    assert len(sent_emails) == 5


def test_send_bad_email(client):
    res = client.post('/email',
                      json={
                          'message': 'asd',
                          'subject': 'asd',
                          'sender_email': 'bad email',
                          'receipents_emails': 'asd@asd.pl',
                          'send_now': True
                      })
    assert res.json['errors']['json']['sender_email'][
        0] == 'Not a valid email address.'
    sent_emails = Email.query.filter_by(status='sent').all()
    assert len(sent_emails) == 0

    # tests for attachments etc