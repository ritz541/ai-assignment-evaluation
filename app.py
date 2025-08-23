import os
from flask import Flask
from flask_login import LoginManager
from pymongo import MongoClient
from routes import register_routes
from models import User
from bson.objectid import ObjectId
from dotenv import load_dotenv

# We will need the `tika` library to extract text from PDFs and DOCX files.
from tika import parser

# --- Flask App Configuration ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'default_secret_key')

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads'
os.makedirs(os.path.join(UPLOAD_FOLDER, 'assignments'), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_FOLDER, 'submissions'), exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'docx', 'doc'}

# --- MongoDB Configuration ---
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
DB_NAME = 'user_auth_db'

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    app.db = db
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    app.db = None

# --- Flask-Login Configuration ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    if app.db is not None:
        try:
            user_doc = app.db.users.find_one({'_id': ObjectId(user_id)})
            if user_doc:
                return User(user_doc)
        except Exception as e:
            print(f"Error loading user with ID {user_id}: {e}")
            return None
    return None

# --- Register Routes ---
register_routes(app)

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()
    app.run(host='0.0.0.0', port=5000, debug=True)
