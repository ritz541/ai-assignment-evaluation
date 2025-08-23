# To run this application, you will need to install the following libraries:
# pip install Flask pymongo werkzeug python-dotenv secrets

import os
import secrets
from flask import Flask, request, render_template, redirect, url_for, flash, session, send_from_directory
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# --- Load Environment Variables from .env file ---
load_dotenv()

# --- Flask App Configuration ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'assignments'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'submissions'), exist_ok=True)

# --- MongoDB Configuration ---
MONGO_URI = os.environ.get('MONGO_URI')
DB_NAME = 'user_auth_db'

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    users_collection = db['users']
    classes_collection = db['classes']
    assignments_collection = db['assignments']
    submissions_collection = db['submissions'] # New collection for submissions
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    client = None
    users_collection = None
    classes_collection = None
    assignments_collection = None
    submissions_collection = None

# --- Helper Functions ---
def allowed_file(filename):
    """Checks if a file has an allowed extension."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_class_code():
    """Generates a unique 8-character hex token for a class code."""
    return secrets.token_hex(4).upper()

# --- Routes ---

@app.route('/')
@app.route('/home')
def home():
    """Renders the home page."""
    return render_template("home.html", title="Home")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handles user registration."""
    if request.method == 'POST':
        if users_collection is None or classes_collection is None:
            flash('Database connection error.', 'error')
            return redirect(url_for('signup'))

        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('user_type')
        
        class_code = None

        if users_collection.find_one({'email': email}):
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('signup'))
        
        if user_type == 'teacher':
            teacher_action = request.form.get('teacher_action')
            if teacher_action == 'create':
                class_code = generate_class_code()
                while classes_collection.find_one({'class_code': class_code}):
                    class_code = generate_class_code()
                
                classes_collection.insert_one({'class_code': class_code, 'teacher_ids': [], 'student_ids': []})

            elif teacher_action == 'join':
                class_code = request.form.get('class_code')
                class_doc = classes_collection.find_one({'class_code': class_code})
                if not class_doc:
                    flash('Invalid or non-existent class code. Please try again.', 'error')
                    return redirect(url_for('signup'))
        
        elif user_type == 'student':
            class_code = request.form.get('class_code')
            class_doc = classes_collection.find_one({'class_code': class_code})
            if not class_doc:
                flash('Invalid or non-existent class code. Please try again.', 'error')
                return redirect(url_for('signup'))

        hashed_password = generate_password_hash(password)
        
        user_id = users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password,
            'user_type': user_type,
            'class_code': class_code
        }).inserted_id

        if user_type == 'teacher':
            classes_collection.update_one({'class_code': class_code}, {'$push': {'teacher_ids': str(user_id)}})
        elif user_type == 'student':
            classes_collection.update_one({'class_code': class_code}, {'$push': {'student_ids': str(user_id)}})

        flash('Your account has been created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template("signup.html", title="Sign Up")

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        if users_collection is None:
            flash('Database connection error.', 'error')
            return redirect(url_for('login'))

        email = request.form.get('email')
        password = request.form.get('password')

        user = users_collection.find_one({'email': email})

        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['username'] = user['username']
            session['email'] = user['email']
            session['user_type'] = user['user_type']
            session['class_code'] = user['class_code']
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))

    return render_template("login.html", title="Log In")

@app.route('/dashboard')
def dashboard():
    """A protected page for logged-in users."""
    if not session.get('logged_in'):
        flash('You must be logged in to view this page.', 'error')
        return redirect(url_for('login'))
    
    username = session.get('username')
    user_type = session.get('user_type')
    class_code = session.get('class_code')
    
    if classes_collection is None or assignments_collection is None or users_collection is None:
        flash('Database connection error.', 'error')
        return redirect(url_for('logout'))

    class_doc = classes_collection.find_one({'class_code': class_code})

    if not class_doc:
        flash('Class not found. Please contact support.', 'error')
        return redirect(url_for('logout'))

    teacher_ids = class_doc.get('teacher_ids', [])
    student_ids = class_doc.get('student_ids', [])

    teachers = list(users_collection.find({'_id': {'$in': [ObjectId(uid) for uid in teacher_ids]}}))
    students = list(users_collection.find({'_id': {'$in': [ObjectId(uid) for uid in student_ids]}}))
    
    assignments = list(assignments_collection.find({'class_code': class_code}).sort('due_date'))

    if user_type == 'teacher':
        # For teachers, also fetch submissions for their class
        submissions = list(submissions_collection.find({'class_code': class_code}))
        return render_template("teacher_dashboard.html", title="Teacher Dashboard", username=username, class_code=class_code, students=students, teachers=teachers, assignments=assignments, submissions=submissions)
    elif user_type == 'student':
        # For students, fetch their own submissions
        student_id = str(users_collection.find_one({'email': session.get('email')})['_id'])
        submissions = list(submissions_collection.find({'student_id': student_id}))
        return render_template("student_dashboard.html", title="Student Dashboard", username=username, class_code=class_code, students=students, teachers=teachers, assignments=assignments, submissions=submissions)
    else:
        flash('Unexpected user type.', 'error')
        return redirect(url_for('logout'))

@app.route('/create_assignment', methods=['GET', 'POST'])
def create_assignment():
    """Handles the creation of a new assignment with file upload."""
    if not session.get('logged_in') or session.get('user_type') != 'teacher':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        if assignments_collection is None:
            flash('Database connection error.', 'error')
            return redirect(url_for('dashboard'))

        title = request.form.get('title')
        description = request.form.get('description')
        due_date = request.form.get('due_date')
        file = request.files['file']

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            assignment_id = assignments_collection.insert_one({
                'title': title,
                'description': description,
                'due_date': due_date,
                'class_code': session.get('class_code'),
                'teacher_id': str(users_collection.find_one({'email': session.get('email')})['_id'])
            }).inserted_id
            
            # Create a unique directory for each assignment's file
            assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'assignments', str(assignment_id))
            os.makedirs(assignment_path, exist_ok=True)
            file_path = os.path.join(assignment_path, filename)
            file.save(file_path)

            # Update the assignment document with the file path and filename
            assignments_collection.update_one(
                {'_id': ObjectId(assignment_id)},
                {'$set': {'file_path': file_path, 'filename': filename}}
            )

            flash('Assignment created successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid file type. Please upload a PDF or Word document.', 'error')
            return redirect(url_for('create_assignment'))

    return render_template('create_assignment.html', title="Create Assignment")

@app.route('/assignment/<assignment_id>', methods=['GET'])
def assignment_detail(assignment_id):
    """Displays the detail page for a specific assignment."""
    if not session.get('logged_in'):
        flash('You must be logged in to view this page.', 'error')
        return redirect(url_for('login'))
    
    if assignments_collection is None:
        flash('Database connection error.', 'error')
        return redirect(url_for('dashboard'))

    assignment = assignments_collection.find_one({'_id': ObjectId(assignment_id), 'class_code': session.get('class_code')})
    if not assignment:
        flash('Assignment not found or you do not have access.', 'error')
        return redirect(url_for('dashboard'))

    student_id = str(users_collection.find_one({'email': session.get('email')})['_id'])
    submission = submissions_collection.find_one({'assignment_id': assignment_id, 'student_id': student_id})

    return render_template('assignment_detail.html', title=assignment['title'], assignment=assignment, submission=submission)

@app.route('/download/<assignment_id>')
def download_assignment(assignment_id):
    """Allows students to download the assignment file."""
    if not session.get('logged_in') or session.get('user_type') != 'student':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    assignment = assignments_collection.find_one({'_id': ObjectId(assignment_id)})
    if not assignment or not assignment.get('file_path'):
        flash('File not found.', 'error')
        return redirect(url_for('dashboard'))
    
    directory = os.path.dirname(assignment['file_path'])
    filename = os.path.basename(assignment['file_path'])

    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/upload_submission/<assignment_id>', methods=['POST'])
def upload_submission(assignment_id):
    """Handles the upload of a student's submission."""
    if not session.get('logged_in') or session.get('user_type') != 'student':
        flash('Unauthorized access.', 'error')
        return redirect(url_for('login'))

    if 'file' not in request.files:
        flash('No file part in the request.', 'error')
        return redirect(url_for('assignment_detail', assignment_id=assignment_id))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file.', 'error')
        return redirect(url_for('assignment_detail', assignment_id=assignment_id))

    if file and allowed_file(file.filename):
        student_id = str(users_collection.find_one({'email': session.get('email')})['_id'])
        filename = secure_filename(file.filename)
        
        # Check if a submission for this assignment already exists for this student
        existing_submission = submissions_collection.find_one({'assignment_id': assignment_id, 'student_id': student_id})
        
        # Define a unique submission path
        submission_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'submissions', assignment_id)
        os.makedirs(submission_dir, exist_ok=True)
        file_path = os.path.join(submission_dir, f"{student_id}_{filename}")

        if existing_submission:
            # If exists, update the record and overwrite the file
            submissions_collection.update_one(
                {'assignment_id': assignment_id, 'student_id': student_id},
                {'$set': {'filename': filename, 'file_path': file_path, 'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}
            )
            flash('Your submission has been updated successfully!', 'success')
        else:
            # If new, insert a new record
            submissions_collection.insert_one({
                'assignment_id': assignment_id,
                'student_id': student_id,
                'class_code': session.get('class_code'),
                'filename': filename,
                'file_path': file_path,
                'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            flash('Your assignment has been submitted successfully!', 'success')

        file.save(file_path)
        return redirect(url_for('assignment_detail', assignment_id=assignment_id))
    else:
        flash('Invalid file type. Please upload a PDF or Word document.', 'error')
        return redirect(url_for('assignment_detail', assignment_id=assignment_id))

@app.route('/logout')
def logout():
    """Logs the user out."""
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('user_type', None)
    session.pop('class_code', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

# --- Run the App ---
if __name__ == '__main__':
    from datetime import datetime
    app.run(host='0.0.0.0', port=5000, debug=True)
