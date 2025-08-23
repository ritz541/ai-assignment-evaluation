
import os
import secrets # Used for generating secure, unique class codes
from flask import Flask, request, render_template, redirect, url_for, flash, session
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# --- Load Environment Variables from .env file ---
load_dotenv()

# --- Flask App Configuration ---
app = Flask(__name__)
# A secret key is required for sessions and flashing messages
# It is now loaded from the .env file
app.secret_key = os.environ.get('FLASK_SECRET_KEY')

# --- MongoDB Configuration ---
# The connection URI is now loaded from the .env file
MONGO_URI = os.environ.get('MONGO_URI')
DB_NAME = 'user_auth_db'

try:
    # Attempt to connect to MongoDB
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    users_collection = db['users']
    print("Successfully connected to MongoDB.")
except Exception as e:
    # Handle connection errors
    print(f"Error connecting to MongoDB: {e}")
    client = None
    users_collection = None

# --- Helper Function ---
def generate_class_code():
    """Generates a unique 8-character hex token for a class code."""
    return secrets.token_hex(4).upper()

# --- Routes ---

@app.route('/')
@app.route('/home')
def home():
    """Renders the home page."""
    # render_template now points to a file in the 'templates' folder
    return render_template("home.html", title="Home")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """Handles user registration."""
    if request.method == 'POST':
        # if not users_collection:
        #     flash('Database connection error.', 'error')
        #     return redirect(url_for('signup'))

        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        user_type = request.form.get('user_type') # Get the user type from the form
        
        class_code = None

        # Check if email already exists
        if users_collection.find_one({'email': email}):
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('signup'))
        
        if user_type == 'teacher':
            # Teachers get a new class code
            class_code = generate_class_code()
            # Check for a unique class code in a rare case of collision
            while users_collection.find_one({'class_code': class_code}):
                class_code = generate_class_code()
        
        elif user_type == 'student':
            # Students must provide an existing class code
            class_code = request.form.get('class_code')
            if not users_collection.find_one({'class_code': class_code, 'user_type': 'teacher'}):
                flash('Invalid or non-existent class code. Please try again.', 'error')
                return redirect(url_for('signup'))

        # Hash the password for security
        hashed_password = generate_password_hash(password)

        # Save the new user to the database, including the user_type and class_code
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password,
            'user_type': user_type,
            'class_code': class_code
        })

        flash('Your account has been created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template("signup.html", title="Sign Up")

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':
        # if not users_collection:
        #     flash('Database connection error.', 'error')
        #     return redirect(url_for('login'))

        email = request.form.get('email')
        password = request.form.get('password')

        # Find the user by email
        user = users_collection.find_one({'email': email})

        # Check if user exists and password is correct
        if user and check_password_hash(user['password'], password):
            # Store user info and their type in the session
            session['logged_in'] = True
            session['username'] = user['username']
            session['email'] = user['email']
            session['user_type'] = user['user_type']
            session['class_code'] = user['class_code'] # Store the class code
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
    class_code = session.get('class_code') # Get the class code from the session
    
    if user_type == 'teacher':
        return render_template("teacher_dashboard.html", title="Teacher Dashboard", username=username, class_code=class_code)
    elif user_type == 'student':
        return render_template("student_dashboard.html", title="Student Dashboard", username=username, class_code=class_code)
    else:
        # Fallback for unexpected user types
        flash('Unexpected user type.', 'error')
        return redirect(url_for('logout'))

@app.route('/logout')
def logout():
    """Logs the user out."""
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('email', None)
    session.pop('user_type', None)
    session.pop('class_code', None) # Clear the class code from the session
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

# --- Run the App ---
if __name__ == '__main__':
    # You can change host and port as needed
    app.run(host='0.0.0.0', port=5000, debug=True)
