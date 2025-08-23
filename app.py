import os
from flask import Flask, request, render_template, redirect, url_for, flash, session
from pymongo import MongoClient
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

        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if email already exists
        if users_collection.find_one({'email': email}):
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('signup'))

        # Hash the password for security
        hashed_password = generate_password_hash(password)

        # Save the new user to the database
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password
        })

        flash('Your account has been created successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    # render_template now points to a file in the 'templates' folder
    return render_template("signup.html", title="Sign Up")

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    if request.method == 'POST':

        email = request.form.get('email')
        password = request.form.get('password')

        # Find the user by email
        user = users_collection.find_one({'email': email})

        # Check if user exists and password is correct
        if user and check_password_hash(user['password'], password):
            # Store user info in the session
            session['logged_in'] = True
            session['username'] = user['username']
            session['email'] = user['email']
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
    # render_template now points to a file in the 'templates' folder
    return render_template("dashboard.html", title="Dashboard", username=username)

@app.route('/logout')
def logout():
    """Logs the user out."""
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('email', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

# --- Run the App ---
if __name__ == '__main__':
    # You can change host and port as needed
    app.run(debug=True)
