import uuid

from flask import Blueprint, current_app, request
from flask_restful import Api, Resource

from modules.database import Attachment as AttachmentModel
from modules.extensions import db

attachment_bp = Blueprint('attachment', __name__)
attachment_api = Api(attachment_bp)


class AttachmentResource(Resource):
    @staticmethod
    def get_attachment(attachment_id):
        attachment = AttachmentModel.query.get(attachment_id)
        return attachment

    @staticmethod
    def get_attachments(attachment_ids):
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


attachment_api.add_resource(AttachmentResource, '/file')
