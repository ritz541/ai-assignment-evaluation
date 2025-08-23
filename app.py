# To run this application, you will need to install the following libraries:
# pip install Flask pymongo werkzeug python-dotenv

import os
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
        user_type = request.form.get('user_type') # Get the new user type from the form

        # Check if email already exists
        if users_collection.find_one({'email': email}):
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('signup'))

        # Hash the password for security
        hashed_password = generate_password_hash(password)

        # Save the new user to the database, including the user_type
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password,
            'user_type': user_type # Store the user type
        })

        flash('Your account has been created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    # render_template now points to a file in the 'templates' folder
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
            session['user_type'] = user['user_type'] # Store the user type
            flash('Logged in successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))

    # render_template now points to a file in the 'templates' folder
    return render_template("login.html", title="Log In")

@app.route('/dashboard')
def dashboard():
    """A protected page for logged-in users."""
    if not session.get('logged_in'):
        flash('You must be logged in to view this page.', 'error')
        return redirect(url_for('login'))
    
    username = session.get('username')
    user_type = session.get('user_type') # Get the user type from the session
    
    # Conditional rendering based on user type
    if user_type == 'teacher':
        return render_template("teacher_dashboard.html", title="Teacher Dashboard", username=username)
    elif user_type == 'student':
        return render_template("student_dashboard.html", title="Student Dashboard", username=username)
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
    session.pop('user_type', None) # Clear the user type from the session
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

# --- Run the App ---
if __name__ == '__main__':
    # You can change host and port as needed
    app.run(host='0.0.0.0', port=5000, debug=True)
