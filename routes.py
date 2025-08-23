import os
import secrets
from flask import render_template, request, redirect, url_for, flash, session, send_from_directory
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from datetime import datetime
from models import User, Assignment, Submission

def register_routes(app):
    @app.route('/')
    @app.route('/home')
    def home():
        return render_template("home.html", title="Home")

    @app.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            if app.db is None:
                flash('Database connection error.', 'danger')
                return redirect(url_for('signup'))

            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            user_type = request.form.get('user_type')
            
            if app.db.users.find_one({'email': email}):
                flash('An account with this email already exists.', 'warning')
                return redirect(url_for('signup'))
            
            # All users select their class from the dropdown
            class_name = request.form.get('class_name')
            
            user_data = {
                'username': username,
                'email': email,
                'password': generate_password_hash(password),
                'user_type': user_type,
                'class_name': class_name
            }

            if user_type == 'teacher':
                subject = request.form.get('subject')
                user_data['subject'] = subject
            
            app.db.users.insert_one(user_data)

            flash('Your account has been created successfully! Please log in.', 'success')
            return redirect(url_for('login'))

        return render_template("signup.html", title="Sign Up")

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            if app.db is None:
                flash('Database connection error.', 'danger')
                return redirect(url_for('login'))

            email = request.form.get('email')
            password = request.form.get('password')
            remember = request.form.get('remember')

            user_doc = app.db.users.find_one({'email': email})

            if user_doc and check_password_hash(user_doc['password'], password):
                user = User(user_doc)
                login_user(user, remember=remember)
                flash('Logged in successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid email or password.', 'danger')
                return redirect(url_for('login'))

        return render_template("login.html", title="Log In")

    @app.route('/dashboard')
    @login_required
    def dashboard():
        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('logout'))
        
        user_type = current_user.user_type
        class_name = current_user.class_name
        
        # Fetch users and assignments based on class_name
        teachers_docs = list(app.db.users.find({'user_type': 'teacher', 'class_name': class_name}))
        students_docs = list(app.db.users.find({'user_type': 'student', 'class_name': class_name}))
        
        teachers = [User(doc) for doc in teachers_docs]
        students = [User(doc) for doc in students_docs]
        
        assignments_docs = list(app.db.assignments.find({'class_name': class_name}).sort('due_date'))
        assignments = [Assignment(doc) for doc in assignments_docs]
        
        if user_type == 'teacher':
            submissions_docs = list(app.db.submissions.find({'class_name': class_name}))
            submissions = [Submission(doc) for doc in submissions_docs]
            return render_template("teacher_dashboard.html", title="Teacher Dashboard", class_name=class_name, students=students, teachers=teachers, assignments=assignments, submissions=submissions)
        
        elif user_type == 'student':
            student_id = current_user.get_id()
            submissions_docs = list(app.db.submissions.find({'student_id': student_id}))
            submissions = [Submission(doc) for doc in submissions_docs]
            return render_template("student_dashboard.html", title="Student Dashboard", class_name=class_name, students=students, teachers=teachers, assignments=assignments, submissions=submissions)
        
        else:
            flash('Unexpected user type.', 'danger')
            return redirect(url_for('logout'))

    @app.route('/create_assignment', methods=['GET', 'POST'])
    @login_required
    def create_assignment():
        if current_user.user_type != 'teacher':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            if app.db is None:
                flash('Database connection error.', 'danger')
                return redirect(url_for('dashboard'))
            
            title = request.form.get('title')
            description = request.form.get('description')
            due_date = request.form.get('due_date')
            file = request.files['file']

            if file and app.config['ALLOWED_EXTENSIONS'] and file.filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']:
                filename = secure_filename(file.filename)
                
                assignment_id = app.db.assignments.insert_one({
                    'title': title,
                    'description': description,
                    'due_date': due_date,
                    'class_name': current_user.class_name,
                    'subject': current_user.subject, # Link to the teacher's subject
                    'teacher_id': current_user.get_id(),
                    'filename': filename,
                    'file_path': ''
                }).inserted_id
                
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'assignments', str(assignment_id))
                os.makedirs(assignment_path, exist_ok=True)
                file_path = os.path.join(assignment_path, filename)
                file.save(file_path)

                app.db.assignments.update_one(
                    {'_id': ObjectId(assignment_id)},
                    {'$set': {'file_path': file_path}}
                )

                flash('Assignment created successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid file type. Please upload a PDF or Word document.', 'warning')
                return redirect(url_for('create_assignment'))
        
        return render_template('create_assignment.html', title="Create Assignment")

    @app.route('/assignment/<assignment_id>', methods=['GET'])
    @login_required
    def assignment_detail(assignment_id):
        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('dashboard'))
        
        assignment_doc = app.db.assignments.find_one({'_id': ObjectId(assignment_id)})
        
        if not assignment_doc or assignment_doc.get('class_name') != current_user.class_name:
            flash('Assignment not found or you do not have access.', 'danger')
            return redirect(url_for('dashboard'))

        assignment = Assignment(assignment_doc)

        submission_doc = app.db.submissions.find_one({'assignment_id': assignment_id, 'student_id': current_user.get_id()})
        submission = Submission(submission_doc) if submission_doc else None

        # Pass the user type to the template to conditionally show/hide the submission form
        return render_template('assignment_detail.html', title=assignment.title, assignment=assignment, submission=submission, user_type=current_user.user_type)

    @app.route('/download/assignment/<assignment_id>')
    @login_required
    def download_assignment(assignment_id):
        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('dashboard'))
            
        assignment_doc = app.db.assignments.find_one({'_id': ObjectId(assignment_id)})
        
        if not assignment_doc or not assignment_doc.get('file_path'):
            flash('File not found.', 'warning')
            return redirect(url_for('dashboard'))
        
        assignment = Assignment(assignment_doc)

        if assignment.class_name != current_user.class_name:
            flash('You do not have permission to download this file.', 'danger')
            return redirect(url_for('dashboard'))

        directory = os.path.dirname(assignment.file_path)
        filename = os.path.basename(assignment.file_path)

        return send_from_directory(directory, filename, as_attachment=True)

    @app.route('/download/submission/<submission_id>')
    @login_required
    def download_submission(submission_id):
        if current_user.user_type != 'teacher':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))

        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('dashboard'))

        submission_doc = app.db.submissions.find_one({'_id': ObjectId(submission_id)})
        
        if not submission_doc or not submission_doc.get('file_path'):
            flash('Submission file not found.', 'warning')
            return redirect(url_for('dashboard'))

        submission = Submission(submission_doc)
        
        # Verify the teacher is in the same class as the student who submitted
        if submission.class_name != current_user.class_name:
            flash('You do not have permission to download this submission.', 'danger')
            return redirect(url_for('dashboard'))

        directory = os.path.dirname(submission.file_path)
        filename = os.path.basename(submission.file_path)
        
        return send_from_directory(directory, filename, as_attachment=True)

    @app.route('/upload_submission/<assignment_id>', methods=['POST'])
    @login_required
    def upload_submission(assignment_id):
        if current_user.user_type != 'student':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))
        
        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('dashboard'))
        
        if 'file' not in request.files:
            flash('No file part in the request.', 'warning')
            return redirect(url_for('assignment_detail', assignment_id=assignment_id))
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file.', 'warning')
            return redirect(url_for('assignment_detail', assignment_id=assignment_id))

        if file and app.config['ALLOWED_EXTENSIONS'] and file.filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']:
            student_id = current_user.get_id()
            filename = secure_filename(file.filename)
            
            existing_submission = app.db.submissions.find_one({'assignment_id': assignment_id, 'student_id': student_id})
            
            submission_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'submissions', assignment_id)
            os.makedirs(submission_dir, exist_ok=True)
            file_path = os.path.join(submission_dir, f"{student_id}_{filename}")

            if existing_submission:
                app.db.submissions.update_one(
                    {'assignment_id': assignment_id, 'student_id': student_id},
                    {'$set': {'filename': filename, 'file_path': file_path, 'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')}}
                )
                flash('Your submission has been updated successfully!', 'success')
            else:
                app.db.submissions.insert_one({
                    'assignment_id': assignment_id,
                    'student_id': student_id,
                    'class_name': current_user.class_name, # Use class_name here
                    'filename': filename,
                    'file_path': file_path,
                    'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                flash('Your assignment has been submitted successfully!', 'success')

            file.save(file_path)
            return redirect(url_for('assignment_detail', assignment_id=assignment_id))
        else:
            flash('Invalid file type. Please upload a PDF or Word document.', 'warning')
            return redirect(url_for('assignment_detail', assignment_id=assignment_id))

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('home'))
