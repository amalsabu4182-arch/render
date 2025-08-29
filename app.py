import sqlite3
from flask import Flask, request, jsonify, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os

# --- Basic Flask App Setup ---
app = Flask(__name__)
# This is crucial for session security
app.secret_key = os.urandom(24)
DATABASE = 'attendance.db'

# --- Database Functions ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        # Add a default admin user and a default class
        hashed_password = generate_password_hash('adminpass')
        db.execute('INSERT INTO admins (username, password) VALUES (?, ?)', ('admin', hashed_password))
        db.execute('INSERT INTO classes (name) VALUES (?)', ('Default Class',))
        db.commit()
        print("Database initialized with default admin and class.")

@app.cli.command('initdb')
def initdb_command():
    init_db()

# --- Decorator for Login ---
def login_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                return jsonify({"success": False, "message": "Unauthorized"}), 401
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- API Routes ---
@app.route('/')
def index():
    return "Backend is running!"

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')

    db = get_db()
    user = None

    if role == 'admin':
        user = db.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
    elif role == 'teacher':
        user = db.execute('SELECT * FROM teachers WHERE email = ?', (username,)).fetchone()
        if user and not user['is_approved']:
            return jsonify({"success": False, "message": "Account not approved by admin."}), 403
    elif role == 'student':
        user = db.execute('SELECT * FROM students WHERE username = ?', (username,)).fetchone()


    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['role'] = role
        user_data = {
            'id': user['id'],
            'name': user.get('name', user['username']) # Use name if it exists, otherwise username
        }
        return jsonify({"success": True, "user": user_data})
    else:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully."})


# --- Admin Routes ---
@app.route('/api/admin/pending_teachers', methods=['GET'])
@login_required('admin')
def get_pending_teachers():
    db = get_db()
    teachers_cursor = db.execute('SELECT id, name, email FROM teachers WHERE is_approved = 0')
    teachers = [dict(row) for row in teachers_cursor.fetchall()]
    return jsonify({"teachers": teachers})

@app.route('/api/admin/approve_teacher', methods=['POST'])
@login_required('admin')
def approve_teacher():
    data = request.json
    teacher_id = data.get('teacher_id')
    db = get_db()
    db.execute('UPDATE teachers SET is_approved = 1 WHERE id = ?', (teacher_id,))
    db.commit()
    return jsonify({"success": True, "message": "Teacher approved."})

# --- Teacher Routes ---
@app.route('/api/teacher/students', methods=['GET'])
@login_required('teacher')
def get_teacher_students():
    db = get_db()
    teacher = db.execute('SELECT class_id FROM teachers WHERE id = ?', (session['user_id'],)).fetchone()
    if not teacher or not teacher['class_id']:
         return jsonify({"error": "Teacher not assigned to a class"}), 404

    students_cursor = db.execute('SELECT id, name FROM students WHERE class_id = ? ORDER BY name', (teacher['class_id'],))
    students = [dict(row) for row in students_cursor.fetchall()]
    return jsonify({"students": students})


# --- Student Routes ---
@app.route('/api/student/data', methods=['GET'])
@login_required('student')
def get_student_data():
    db = get_db()
    student_id = session['user_id']
    records_cursor = db.execute('SELECT date, status, remarks FROM attendance WHERE student_id = ? ORDER BY date DESC', (student_id,))
    records = [dict(row) for row in records_cursor.fetchall()]

    present_days = sum(1 for r in records if r['status'] == 'Full Day')
    absent_days = sum(1 for r in records if r['status'] == 'Absent')
    total_marked_days = len(records)
    percentage = (present_days / total_marked_days * 100) if total_marked_days > 0 else 0

    return jsonify({
        "records": records,
        "present_days": present_days,
        "absent_days": absent_days,
        "percentage": round(percentage)
    })

if __name__ == '__main__':
    app.run(debug=True)

