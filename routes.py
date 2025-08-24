import os
import json
import secrets
from flask import render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from bson.objectid import ObjectId
from datetime import datetime, timedelta
from models import User, Assignment, Submission
from pdf2image import convert_from_path
import pytesseract
from gemini_api import call_gemini_api_for_evaluation, call_deepseek_api_for_summarization
from notification_system import send_notification

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
        
        teachers_docs = list(app.db.users.find({'user_type': 'teacher', 'class_name': class_name}))
        students_docs = list(app.db.users.find({'user_type': 'student', 'class_name': class_name}))
        
        teachers = [User(doc) for doc in teachers_docs]
        students = [User(doc) for doc in students_docs]
        
        assignments_docs = []
        if user_type == 'teacher':
            assignments_docs = list(app.db.assignments.find({
                'class_name': class_name,
                'teacher_id': current_user.get_id()
            }).sort('due_date'))
        else:
            assignments_docs = list(app.db.assignments.find({
                'class_name': class_name
            }).sort('due_date'))
            
        assignments = [Assignment(doc) for doc in assignments_docs]

        submitted_assignment_ids = []
        if user_type == 'student':
            student_id = current_user.get_id()
            submitted_assignment_ids = [
                str(s.get('assignment_id')) for s in app.db.submissions.find({'student_id': student_id}, {'assignment_id': 1})
            ]
        
        assignment_stats = {}
        if user_type == 'teacher':
            total_students_in_class = len(students)
            for assignment in assignments:
                submitted_count = app.db.submissions.count_documents({
                    'assignment_id': assignment.id
                })
                assignment_stats[assignment.id] = {
                    'submitted': submitted_count,
                    'pending': total_students_in_class - submitted_count
                }

        if user_type == 'teacher':
            return render_template("teacher_dashboard.html", title="Teacher Dashboard", class_name=class_name, students=students, teachers=teachers, assignments=assignments, assignment_stats=assignment_stats)
        
        elif user_type == 'student':
            return render_template("student_dashboard.html", title="Student Dashboard", class_name=class_name, students=students, teachers=teachers, assignments=assignments, submitted_assignment_ids=submitted_assignment_ids)
        
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
            reference_file = request.files['reference_file']

            if file and file.filename.rsplit('.', 1)[1].lower() == 'pdf' and \
               reference_file and reference_file.filename.rsplit('.', 1)[1].lower() == 'pdf':
                
                # We need to save the files first to get a path for pdf2image
                assignment_path = os.path.join(app.config['UPLOAD_FOLDER'], 'assignments', str(ObjectId()))
                os.makedirs(assignment_path, exist_ok=True)
                
                file_path = os.path.join(assignment_path, secure_filename(file.filename))
                file.save(file_path)
                
                reference_file_path = os.path.join(assignment_path, secure_filename(reference_file.filename))
                reference_file.save(reference_file_path)

                # Convert reference PDF to images and then to text
                reference_images = convert_from_path(reference_file_path)
                reference_text = ""
                for img in reference_images:
                    reference_text += pytesseract.image_to_string(img)
                
                # Summarize the reference text using DeepSeek
                deepseek_response = call_deepseek_api_for_summarization(reference_text)
                summarized_reference = deepseek_response if deepseek_response else reference_text

                assignment_id = app.db.assignments.insert_one({
                    'title': title,
                    'description': description,
                    'due_date': due_date,
                    'class_name': current_user.class_name,
                    'subject': current_user.subject,
                    'teacher_id': current_user.get_id(),
                    'filename': secure_filename(file.filename),
                    'file_path': file_path,
                    'reference_text': summarized_reference
                }).inserted_id
                
                flash('Assignment created successfully!', 'success')
                
                students_in_class = list(app.db.users.find({'class_name': current_user.class_name, 'user_type': 'student'}))
                student_emails = [s['email'] for s in students_in_class]
                
                notification_data = {
                    'title': title,
                    'subject': current_user.subject,
                    'class_name': current_user.class_name,
                    'due_date': due_date,
                    'emails': student_emails
                }
                send_notification('new_assignment', notification_data)
                
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid file type. Please upload a PDF file for both assignment and reference files.', 'warning')
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
    
    @app.route('/download/reference/<assignment_id>')
    @login_required
    def download_reference(assignment_id):
        if current_user.user_type != 'teacher':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))
        
        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('dashboard'))
            
        assignment_doc = app.db.assignments.find_one({'_id': ObjectId(assignment_id)})
        
        if not assignment_doc or not assignment_doc.get('reference_file_path'):
            flash('Reference file not found.', 'warning')
            return redirect(url_for('dashboard'))
        
        assignment = Assignment(assignment_doc)

        if assignment.class_name != current_user.class_name:
            flash('You do not have permission to download this file.', 'danger')
            return redirect(url_for('dashboard'))

        directory = os.path.dirname(assignment.reference_file_path)
        filename = os.path.basename(assignment.reference_file_path)

        return send_from_directory(directory, filename, as_attachment=True)

    @app.route('/submissions/<assignment_id>')
    @login_required
    def view_submissions(assignment_id):
        if current_user.user_type != 'teacher':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))

        if app.db is None:
            flash('Database connection error.', 'danger')
            return redirect(url_for('dashboard'))

        assignment = app.db.assignments.find_one({'_id': ObjectId(assignment_id)})
        if not assignment or assignment.get('class_name') != current_user.class_name:
            flash('Assignment not found or you do not have access.', 'danger')
            return redirect(url_for('dashboard'))
        
        submissions_docs = list(app.db.submissions.find({'assignment_id': assignment_id}))
        submissions = [Submission(doc) for doc in submissions_docs]

        for submission in submissions:
            student_doc = app.db.users.find_one({'_id': ObjectId(submission.student_id)})
            submission.student_username = student_doc['username'] if student_doc else 'Unknown'

        return render_template('submissions_list.html', title='Submissions', submissions=submissions, assignment_title=assignment['title'])

    @app.route('/grade_submission/<submission_id>', methods=['POST'])
    @login_required
    def grade_submission(submission_id):
        if current_user.user_type != 'teacher':
            flash('Unauthorized access.', 'danger')
            return redirect(url_for('dashboard'))
            
        submission_doc = app.db.submissions.find_one({'_id': ObjectId(submission_id)})
        if not submission_doc:
            flash('Submission not found.', 'warning')
            return redirect(url_for('dashboard'))

        assignment_doc = app.db.assignments.find_one({'_id': ObjectId(submission_doc['assignment_id'])})
        if not assignment_doc:
            flash('Assignment not found for this submission.', 'warning')
            return redirect(url_for('dashboard'))
        
        print("--- Starting AI Grading Process ---")
        try:
            print(f"Converting student PDF: {submission_doc['file_path']}")
            student_images = convert_from_path(submission_doc['file_path'])
            student_text = ""
            for img in student_images:
                student_text += pytesseract.image_to_string(img)
            print("Student submission text extracted.")
            
            print("--- Calling Gemini API for evaluation ---")
            
            # Prepare the prompt for Gemini
            prompt = f"""
            You are an AI grading assistant. Your task is to evaluate a student's answer against a reference answer.
            
            Reference Answer (summarized):
            {assignment_doc['reference_text']}
            
            Student's Answer (extracted from handwritten text):
            {student_text}
            
            Based on the provided texts, give a score from 0 to 100 for the student's work and provide constructive feedback of 1-2 sentences.

            Return the output in a JSON format with the following keys:
            "score": "The score as a number from 0 to 100",
            "remarks": "The constructive feedback"
            """
            
            gemini_response = call_gemini_api_for_evaluation(
                prompt_text=prompt,
                text_content="" # We pass an empty string as we are using text-only input
            )
            
            if gemini_response:
                print("--- AI Response Received Successfully ---")
                score = gemini_response.get('score', 'N/A')
                remarks = gemini_response.get('remarks', 'No remarks provided.')
                
                app.db.submissions.update_one(
                    {'_id': ObjectId(submission_id)},
                    {'$set': {
                        'ai_score': score,
                        'ai_remarks': remarks,
                        'ai_graded_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }}
                )
                flash('AI evaluation completed successfully!', 'success')
                print("--- Database updated with AI evaluation ---")

                student_doc = app.db.users.find_one({'_id': ObjectId(submission_doc['student_id'])})
                if student_doc:
                    notification_data = {
                        'email': student_doc['email'],
                        'username': student_doc['username'],
                        'assignment_title': assignment_doc['title'],
                        'score': score,
                        'remarks': remarks
                    }
                    print("--- Sending notification via n8n ---")
                    send_notification('evaluation_complete', notification_data)
                    print("--- Notification sent ---")

            else:
                flash('Failed to get a valid response from the AI.', 'danger')
                print("--- Failed to get a valid AI response ---")
        except Exception as e:
            flash(f'An error occurred during AI grading: {e}', 'danger')
            print(f"--- An unexpected error occurred: {e} ---")
        
        return redirect(url_for('view_submissions', assignment_id=submission_doc['assignment_id']))

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

        if file and file.filename.rsplit('.', 1)[1].lower() == 'pdf':
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
                    'class_name': current_user.class_name,
                    'filename': filename,
                    'file_path': file_path,
                    'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
                flash('Your assignment has been submitted successfully!', 'success')

            file.save(file_path)
            return redirect(url_for('assignment_detail', assignment_id=assignment_id))
        else:
            flash('Invalid file type. Please upload a PDF file.', 'warning')
            return redirect(url_for('assignment_detail', assignment_id=assignment_id))

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out.', 'info')
        return redirect(url_for('home'))
