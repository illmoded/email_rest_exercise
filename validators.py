from webargs import ValidationError

from database import Email, Attachment


def email_must_exist_in_db(email_id):
    if not Email.query.get(email_id):
        raise ValidationError(
            f"Email with given id ({email_id}) does not exist")


def attachment_must_exist_in_db(attachment_id):
    if not Attachment.query.get(attachment_id):
        raise ValidationError(
            f"Attachment with given id ({attachment_id}) does not exist")


def attachment_must_not_be_connected_to_email(attachment_id):
    attachment = Attachment.query.get(attachment_id)
    if attachment and attachment.email_id:
        raise ValidationError(f"Attachment can be only attached to one email")
