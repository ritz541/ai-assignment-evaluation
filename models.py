from flask_login import UserMixin
from bson.objectid import ObjectId

class User(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data
        self.id = str(user_data['_id'])
        self.username = user_data.get('username')
        self.email = user_data.get('email')
        self.user_type = user_data.get('user_type')
        self.class_name = user_data.get('class_name') # Now using class_name
        self.subject = user_data.get('subject') # Teachers have a subject

    def get_id(self):
        return self.id

class Assignment:
    def __init__(self, assignment_data):
        self.assignment_data = assignment_data
        self.id = str(assignment_data['_id'])
        self.title = assignment_data.get('title')
        self.description = assignment_data.get('description')
        self.due_date = assignment_data.get('due_date')
        self.class_name = assignment_data.get('class_name') # Now using class_name
        self.subject = assignment_data.get('subject') # Assignments are linked to a subject
        self.teacher_id = assignment_data.get('teacher_id')
        self.filename = assignment_data.get('filename')
        self.file_path = assignment_data.get('file_path')

class Submission:
    def __init__(self, submission_data):
        self.submission_data = submission_data
        self.id = str(submission_data['_id'])
        self.assignment_id = submission_data.get('assignment_id')
        self.student_id = submission_data.get('student_id')
        self.filename = submission_data.get('filename')
        self.file_path = submission_data.get('file_path')
        self.upload_date = submission_data.get('upload_date')
