from flask import Flask, render_template, url_for, flash, redirect, request
import os
from forms import RegistrationForm, LoginForm, VideoUploadForm
from werkzeug.utils import secure_filename
from functools import wraps
from models import db, login_manager, User, Video
from flask_login import login_user, logout_user, current_user, login_required
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here' # Change this to a strong, random key in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if os.environ.get('VERCEL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:' # Use in-memory SQLite for Vercel
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads' # Folder to store uploaded videos

db.init_app(app)
login_manager.init_app(app)

# Function to create database tables
def create_database(app):
    with app.app_context():
        if os.environ.get('VERCEL'):
            print("Running on Vercel, skipping db.create_all() for in-memory DB.")
        else:
            db.create_all()

# Call create_database after app initialization to ensure tables are created
create_database(app)

# Ensure the upload folder exists
if os.environ.get('VERCEL'):
    print("Running on Vercel, skipping local UPLOAD_FOLDER creation.")
else:
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You do not have permission to access that page.', 'danger')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('login'))
        if not current_user.is_subscribed:
            flash('This feature requires an active subscription. Please register or subscribe to continue.', 'warning')
            return redirect(url_for('register')) # Or a dedicated subscribe page
        return f(*args, **kwargs)
    return decorated_function

# Routes will go here

@app.route('/')
def home():
    videos = Video.query.order_by(Video.upload_date.desc()).all()
    if current_user.is_authenticated and not current_user.is_subscribed:
        flash('You are not subscribed. Please register or subscribe to access all content.', 'warning')
    return render_template('index.html', videos=videos)

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        # Make the first user an admin for testing purposes
        if User.query.count() == 0:
            user.role = 'admin'
        
        # Mocking subscription after successful registration
        user.is_subscribed = True
        user.subscription_start_date = datetime.utcnow()
        user.subscription_end_date = datetime.utcnow() + timedelta(days=30) # 1 month subscription
        
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created and you are now subscribed for 1 month! You are now able to log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route("/upload_video", methods=['GET', 'POST'])
@login_required
@subscription_required
def upload_video():
    form = VideoUploadForm()
    if form.validate_on_submit():
        if os.environ.get('VERCEL'):
            flash('Video uploads are not supported on Vercel without external object storage.', 'danger')
            return redirect(url_for('home'))
        
        if form.video.data:
            filename = secure_filename(form.video.data.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            form.video.data.save(file_path)
            
            video = Video(title=form.title.data,
                          description=form.description.data,
                          filename=filename,
                          user_id=current_user.id)
            db.session.add(video)
            db.session.commit()
            flash('Your video has been uploaded!', 'success')
            return redirect(url_for('home'))
    return render_template('upload.html', title='Upload Video', form=form)

@app.route("/admin")
@admin_required
def admin_panel():
    return render_template('admin.html', title='Admin Panel')

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Create database tables if they don't exist
    app.run(debug=True)
