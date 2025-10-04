from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mail import Mail, Message
import sqlite3
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
load_dotenv()  # Loads .env vars into os.environ

app = Flask(__name__)
import os
app.secret_key = os.environ.get('SECRET_KEY', 'Freej@Secret#786$123')  # Set SECRET_KEY in Render env vars

# Email configuration (for Gmail; use app password in production)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

# Hardcoded admin credentials (change in production)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'

# Database setup
import mysql.connector
from mysql.connector import Error

def init_db():
    try:
        conn = mysql.connector.connect(
            host='yourusername.mysql.pythonanywhere-services.com',  # From dashboard
            user='yourusername',  # Your PA username
            password=os.environ.get('DB_PASSWORD'),  # Set in dashboard
            database='yourusername$reservationdb'  # Create this DB
        )
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS reservations
                     (id INT AUTO_INCREMENT PRIMARY KEY,
                      name VARCHAR(255) NOT NULL,
                      mobile VARCHAR(20) NOT NULL,
                      email VARCHAR(255) NOT NULL,
                      guests INT NOT NULL,
                      seat_type VARCHAR(50) NOT NULL,
                      status VARCHAR(20) DEFAULT 'waiting',
                      seat_number INT,
                      rejection_reason TEXT,
                      timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)''')
        conn.commit()
    except Error as e:
        print(f"DB Error: {e}")
    finally:
        if conn.is_connected():
            conn.close()

# Function to send email
def send_email(to_email, subject, body):
    msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[to_email])
    msg.body = body
    try:
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        email = request.form['email']
        guests = int(request.form['guests'])
        seat_type = request.form['seat_type']
        
        conn = sqlite3.connect('reservations.db')
        c = conn.cursor()
        c.execute("INSERT INTO reservations (name, mobile, email, guests, seat_type) VALUES (?, ?, ?, ?, ?)",
                  (name, mobile, email, guests, seat_type))
        res_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Send initial waiting email
        subject = "Reservation Submitted - Freej Swaeleh Restaurant"
        body = f"""
Dear {name},

Your reservation request has been submitted successfully!
- ID: {res_id}
- Guests: {guests}
- Seat Type: {seat_type}
- Status: Waiting

We will notify you via email once your reservation is confirmed or updated.

Best regards,
Freej Swaeleh Restaurant Team
        """
        send_email(email, subject, body)
        
        flash('Reservation submitted successfully! Confirmation email sent.', 'success')
        return redirect(url_for('home'))
    
    return render_template('home.html')

@app.route('/admin')
@login_required
def admin():
    conn = sqlite3.connect('reservations.db')
    c = conn.cursor()
    c.execute("SELECT * FROM reservations ORDER BY updated_at DESC")
    reservations = c.fetchall()
    conn.close()
    return render_template('admin.html', reservations=reservations)

@app.route('/admin/update/<int:res_id>', methods=['POST'])
@login_required
def update_reservation(res_id):
    new_status = request.form['status']
    seat_number_str = request.form['seat_number']
    seat_number = int(seat_number_str) if seat_number_str else None
    rejection_reason = request.form['rejection_reason'] if request.form['rejection_reason'] else None
    
    conn = sqlite3.connect('reservations.db')
    c = conn.cursor()
    # Fetch current details
    c.execute("SELECT name, email, status FROM reservations WHERE id=?", (res_id,))
    current = c.fetchone()
    if not current:
        flash('Reservation not found.', 'error')
        return redirect(url_for('admin'))
    
    name, email, old_status = current
    
    # Update
    c.execute("UPDATE reservations SET status=?, seat_number=?, rejection_reason=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
              (new_status, seat_number, rejection_reason, res_id))
    conn.commit()
    conn.close()
    
    # Send email if status changed to accepted or rejected
    if new_status == 'accepted' and old_status != 'accepted':
        subject = "Reservation Confirmed - Freej Swaeleh Restaurant"
        body = f"""
Dear {name},

Your reservation has been confirmed!
- ID: {res_id}
- Seat Number: {seat_number or 'TBD'}
- Status: Confirmed

Please arrive on time.

Best regards,
Freej Swaeleh Restaurant Team
        """
        if send_email(email, subject, body):
            flash('Reservation updated and confirmation email sent!', 'success')
        else:
            flash('Reservation updated, but email failed to send.', 'success')
    elif new_status == 'rejected' and old_status != 'rejected':
        subject = "Reservation Rejected - Freej Swaeleh Restaurant"
        body = f"""
Dear {name},

Unfortunately, your reservation could not be accommodated.
- ID: {res_id}
- Reason: {rejection_reason or 'No specific reason provided'}

We apologize for any inconvenience.

Best regards,
Freej Swaeleh Restaurant Team
        """
        if send_email(email, subject, body):
            flash('Reservation updated and rejection email sent!', 'success')
        else:
            flash('Reservation updated, but email failed to send.', 'success')
    else:
        flash('Reservation updated!', 'success')
    
    return redirect(url_for('admin'))

@app.route('/status')
def status():
    conn = sqlite3.connect('reservations.db')
    c = conn.cursor()
    
    c.execute("SELECT * FROM reservations WHERE status='accepted' ORDER BY updated_at DESC")
    confirmed = c.fetchall()
    
    c.execute("SELECT * FROM reservations WHERE status='waiting' ORDER BY updated_at DESC")
    waiting = c.fetchall()
    
    c.execute("SELECT * FROM reservations WHERE status='rejected' ORDER BY updated_at DESC")
    rejected = c.fetchall()
    
    conn.close()
    return render_template('status.html', confirmed=confirmed, waiting=waiting, rejected=rejected)

if __name__ == '__main__':
    app.run(debug=True)
