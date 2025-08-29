import os
from flask import Flask, request, jsonify, g, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from sqlalchemy import create_engine, text, exc

# --- Basic Flask App Setup ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))

# --- Database Connection ---
# Render provides this DATABASE_URL as an environment variable
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)

def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = engine.connect()
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database using the schema.sql file."""
    with app.app_context():
        db = get_db()
        # Use a transaction to ensure all commands succeed or none do.
        with db.begin() as trans:
            with app.open_resource('schema.sql', mode='r') as f:
                # Execute the entire schema file
                db.execute(text(f.read()))
            
            # Add a default admin user and a default class
            hashed_password = generate_password_hash('adminpass')
            db.execute(
                text("INSERT INTO admins (username, password) VALUES (:user, :pw) ON CONFLICT (username) DO NOTHING"),
                {'user': 'admin', 'pw': hashed_password}
            )
            db.execute(
                text("INSERT INTO classes (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),
                {'name': 'Default Class'}
            )
        print("Database initialized.")


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
            # Add user object to g so routes can access it
            db = get_db()
            if role == 'admin':
                result = db.execute(text("SELECT * FROM admins WHERE id = :id"), {'id': session['user_id']})
            elif role == 'teacher':
                result = db.execute(text("SELECT * FROM teachers WHERE id = :id"), {'id': session['user_id']})
            elif role == 'student':
                 result = db.execute(text("SELECT * FROM students WHERE id = :id"), {'id': session['user_id']})
            g.user = result.fetchone()
            if g.user is None:
                return jsonify({"success": False, "message": "User not found"}), 401
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

    try:
        if role == 'admin':
            result = db.execute(text("SELECT * FROM admins WHERE username = :user"), {'user': username})
            user = result.fetchone()
        elif role == 'teacher':
            result = db.execute(text("SELECT * FROM teachers WHERE email = :user"), {'user': username})
            user = result.fetchone()
            if user and not user.is_approved:
                return jsonify({"success": False, "message": "Account not approved by admin."}), 403
        elif role == 'student':
            result = db.execute(text("SELECT * FROM students WHERE username = :user"), {'user': username})
            user = result.fetchone()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = role
            user_data = {
                'id': user.id,
                'name': getattr(user, 'name', user.username)
            }
            return jsonify({"success": True, "user": user_data})
        else:
            return jsonify({"success": False, "message": "Invalid username or password"}), 401
    except exc.SQLAlchemyError as e:
        # Log the error for debugging
        print(f"Database error during login: {e}")
        return jsonify({"success": False, "message": "A database error occurred."}), 500


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully."})

# --- Admin Routes ---
@app.route('/api/admin/pending_teachers', methods=['GET'])
@login_required('admin')
def get_pending_teachers():
    db = get_db()
    result = db.execute(text('SELECT id, name, email FROM teachers WHERE is_approved = false'))
    teachers = [dict(row._mapping) for row in result.fetchall()]
    return jsonify({"teachers": teachers})

@app.route('/api/admin/approve_teacher', methods=['POST'])
@login_required('admin')
def approve_teacher():
    data = request.json
    teacher_id = data.get('teacher_id')
    db = get_db()
    db.execute(text('UPDATE teachers SET is_approved = true WHERE id = :id'), {'id': teacher_id})
    db.commit()
    return jsonify({"success": True, "message": "Teacher approved."})

# --- Teacher Routes ---
@app.route('/api/teacher/students', methods=['GET'])
@login_required('teacher')
def get_teacher_students():
    db = get_db()
    teacher = g.user # Get user from decorator
    
    if not teacher or not teacher.class_id:
         return jsonify({"error": "Teacher not assigned to a class"}), 404

    result = db.execute(text('SELECT id, name FROM students WHERE class_id = :cid ORDER BY name'), {'cid': teacher.class_id})
    students = [dict(row._mapping) for row in result.fetchall()]
    return jsonify({"students": students})

# --- Student Routes ---
@app.route('/api/student/data', methods=['GET'])
@login_required('student')
def get_student_data():
    db = get_db()
    student_id = session['user_id']
    result = db.execute(text('SELECT date, status, remarks FROM attendance WHERE student_id = :sid ORDER BY date DESC'), {'sid': student_id})
    records = [dict(row._mapping) for row in result.fetchall()]

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

