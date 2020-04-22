from webargs import ValidationError

from database import Email


def email_must_exist_in_db(email_id):
    if not Email.query.get(email_id):
        raise ValidationError(
            f"Email with given id ({email_id}) does not exist")
