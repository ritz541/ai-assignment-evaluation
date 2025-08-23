# To run this application, you will need to install the following libraries:
# pip install Flask pymongo werkzeug python-dotenv secrets

import os
import secrets
from flask import Flask, request, render_template, redirect, url_for, flash, session
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# --- Load Environment Variables from .env file ---
load_dotenv()

# --- Flask App Configuration ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# --- MongoDB Configuration ---
MONGO_URI = os.environ.get('MONGO_URI')
DB_NAME = 'user_auth_db'

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    users_collection = db['users']
    classes_collection = db['classes'] # New collection for classes
    print("Successfully connected to MongoDB.")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    client = None
    users_collection = None
    classes_collection = None

# --- Helper Function ---
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
        # FIX: Changed the truthiness check to an explicit comparison with None.
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
                # Check for a unique class code in a rare case of collision
                while classes_collection.find_one({'class_code': class_code}):
                    class_code = generate_class_code()
                
                # Create a new class document
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

        # Hash the password for security
        hashed_password = generate_password_hash(password)
        
        # Save the new user to the database
        user_id = users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password,
            'user_type': user_type,
            'class_code': class_code
        }).inserted_id

        # Update the class document with the new user's ID
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
        # FIX: Changed the truthiness check to an explicit comparison with None.
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
    
    # Fetch all class details
    class_doc = classes_collection.find_one({'class_code': class_code})

    if not class_doc:
        flash('Class not found. Please contact support.', 'error')
        return redirect(url_for('logout'))

    # Get a list of student and teacher user IDs
    teacher_ids = class_doc.get('teacher_ids', [])
    student_ids = class_doc.get('student_ids', [])

    # Fetch user details for display
    teachers = list(users_collection.find({'_id': {'$in': [ObjectId(uid) for uid in teacher_ids]}}))
    students = list(users_collection.find({'_id': {'$in': [ObjectId(uid) for uid in student_ids]}}))

    if user_type == 'teacher':
        return render_template("teacher_dashboard.html", title="Teacher Dashboard", username=username, class_code=class_code, students=students, teachers=teachers)
    elif user_type == 'student':
        return render_template("student_dashboard.html", title="Student Dashboard", username=username, class_code=class_code, students=students, teachers=teachers)
    else:
        flash('Unexpected user type.', 'error')
        return redirect(url_for('logout'))

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
    app.run(host='0.0.0.0', port=5000, debug=True)
