import os
import json
import re
import random

import fitz
import mysql.connector
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash, send_from_directory
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

try:
    from google import genai

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    AI_AVAILABLE = True
except Exception as error:
    gemini_client = None
    AI_AVAILABLE = False
    print(f"Warning: Gemini disabled: {error}")

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "super_secret_key_for_this_mini_project"
)

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads", "notes")
ASSIGNMENT_FOLDER = os.path.join(
    app.root_path, "static", "uploads", "assignments"
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["ASSIGNMENT_FOLDER"] = ASSIGNMENT_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(ASSIGNMENT_FOLDER, exist_ok=True)

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "admin123",
    "database": "student_performance_db",
}


def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as error:
        print(f"Error connecting to MySQL: {error}")
        return None


def initialize_schema():
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            role ENUM('admin', 'teacher', 'student') DEFAULT 'student'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            name VARCHAR(100) NOT NULL,
            roll_number VARCHAR(20) NOT NULL UNIQUE,
            attendance_percent FLOAT NOT NULL DEFAULT 0,
            marks_percent FLOAT NOT NULL DEFAULT 0,
            assignments_score FLOAT NOT NULL DEFAULT 0,
            ai_prediction VARCHAR(50) NOT NULL DEFAULT 'Not Evaluated',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            name VARCHAR(100) NOT NULL,
            department VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            teacher_id INT,
            title VARCHAR(255) NOT NULL,
            subject VARCHAR(100),
            file_path VARCHAR(255) NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assignment_submissions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT,
            title VARCHAR(255) NOT NULL,
            roll_number VARCHAR(20),
            file_path VARCHAR(255) NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            score FLOAT DEFAULT NULL,
            remark TEXT,
            reviewed_by INT DEFAULT NULL,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (reviewed_by) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quizzes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            teacher_id INT,
            note_id INT NULL,
            title VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (note_id) REFERENCES notes(id) ON DELETE SET NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS questions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            quiz_id INT,
            question_text TEXT NOT NULL,
            option_a VARCHAR(255) NOT NULL,
            option_b VARCHAR(255) NOT NULL,
            option_c VARCHAR(255) NOT NULL,
            option_d VARCHAR(255) NOT NULL,
            correct_option CHAR(1) NOT NULL,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT,
            quiz_id INT,
            score INT NOT NULL,
            total_questions INT NOT NULL,
            ai_analysis TEXT,
            attempt_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT,
            teacher_id INT,
            attendance_date DATE,
            status ENUM('present', 'absent', 'leave') DEFAULT 'absent',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE KEY (student_id, teacher_id, attendance_date)
        )
    ''')

    conn.commit()

    # Ensure required columns exist and have defaults in student table.
    cursor.execute(
        '''
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        ''',
        (DB_CONFIG['database'], 'students', 'user_id')
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute('ALTER TABLE students ADD COLUMN user_id INT')

    cursor.execute(
        '''
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        ''',
        (DB_CONFIG['database'], 'assignment_submissions', 'roll_number')
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute('ALTER TABLE assignment_submissions ADD COLUMN roll_number VARCHAR(20) AFTER title')

    cursor.execute('''
        ALTER TABLE students
        MODIFY attendance_percent FLOAT NOT NULL DEFAULT 0,
        MODIFY marks_percent FLOAT NOT NULL DEFAULT 0,
        MODIFY assignments_score FLOAT NOT NULL DEFAULT 0,
        MODIFY ai_prediction VARCHAR(50) NOT NULL DEFAULT 'Not Evaluated'
    ''')

    # Ensure teacher link column exists if needed.
    cursor.execute(
        '''
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        ''',
        (DB_CONFIG['database'], 'teacher', 'user_id')
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute('ALTER TABLE teacher ADD COLUMN user_id INT')

    conn.commit()
    cursor.close()
    conn.close()

initialize_schema()

# --- AI Helper Functions ---
def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text()
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def generate_quiz_from_text(text):
    if not AI_AVAILABLE:
        return []
    prompt = f"""
    Based on the following text, generate 5 multiple choice questions.
    Return ONLY a valid JSON array of objects. Each object must have:
    "question_text" (string), "option_a" (string), "option_b" (string), "option_c" (string), "option_d" (string), "correct_option" (string 'A', 'B', 'C', or 'D').
    Do not include markdown blocks like ```json ... ```, just output the raw JSON array.
    Text: {text[:5000]}
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    try:
        response = model.generate_content(prompt)
        content = response.text.strip()
        import re
        match = re.search(r'\[\s*\{.*\}\s*\]', content, re.DOTALL)
        if match:
            content = match.group(0)
        questions = json.loads(content)
        return questions
    except Exception as e:
        print(f"AI Quiz Generation Error: {e}. Using fallback generator.")
        
        # Fallback basic generator
        import random, re
        sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if len(s.strip()) > 30]
        if not sentences:
            sentences = ["The study material covers important concepts.", "Students should review the material carefully.", "This is a placeholder sentence for testing.", "Understanding the core principles is vital.", "Always check your work before submitting."]
            
        selected = random.sample(sentences, min(5, len(sentences)))
        questions = []
        for i, sentence in enumerate(selected[:5]):
            words = sentence.split()
            if len(words) > 5:
                blank_idx = random.randint(2, len(words) - 2)
                correct_ans = words[blank_idx].strip(',;:"\'()')
                words[blank_idx] = "_____"
                q_text = "Fill in the blank: " + " ".join(words)
                
                options = [correct_ans, "System", "Process", "Data"]
                random.shuffle(options)
                correct_letter = chr(65 + options.index(correct_ans))
                
                questions.append({
                    "question_text": q_text,
                    "option_a": options[0],
                    "option_b": options[1],
                    "option_c": options[2],
                    "option_d": options[3],
                    "correct_option": correct_letter
                })
        
        return questions

def generate_performance_analysis(score, total, subject):
    if not AI_AVAILABLE:
        return "Good effort. Keep reviewing the material to improve your understanding."
    prompt = f"""
    A student scored {score} out of {total} in a quiz on the subject '{subject}'.
    Provide a brief, encouraging paragraph analyzing their performance, identifying potential weak and strong areas based on the score, and suggesting 1 or 2 improvement tips.
    Keep it concise.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"AI Analysis Error: {e}")
        return "Good effort. Keep reviewing the material to improve your understanding."

# --- Routes ---

@app.route('/')
def index():
    if 'loggedin' in session:
        role = session.get('role')
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role')
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('index'))
        
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s AND role = %s', (username, password, role))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user:
        session['loggedin'] = True
        session['id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        if role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    else:
        flash('Incorrect username/password/role!', 'danger')
        return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role')
        name = request.form.get('name')
        
        # Additional fields based on role
        if role == 'student':
            roll_number = request.form.get('roll_number')
        elif role == 'teacher':
            department = request.form.get('department')
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please check MySQL.", "danger")
            return redirect(url_for('register'))
        
        cursor = conn.cursor()
        
        try:
            # Insert into users table
            cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)',
                           (username, password, role))
            user_id = cursor.lastrowid
            
            # Insert into respective table
            if role == 'student':
                cursor.execute('INSERT INTO students (user_id, name, roll_number) VALUES (%s, %s, %s)',
                               (user_id, name, roll_number))
            elif role == 'teacher':
                cursor.execute('INSERT INTO teacher (user_id, name, department) VALUES (%s, %s, %s)',
                               (user_id, name, department))
            
            conn.commit()
            flash('Registration successful! Please login with your credentials.', 'success')
            return redirect(url_for('index'))
            
        except mysql.connector.Error as err:
            flash(f"Registration failed: {err}", "danger")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Admin Routes ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)
    
    # Get stats
    cursor.execute('SELECT COUNT(*) as cnt FROM users WHERE role=%s', ('student',))
    student_count = cursor.fetchone()['cnt']
    cursor.execute('SELECT COUNT(*) as cnt FROM users WHERE role=%s', ('teacher',))
    teacher_count = cursor.fetchone()['cnt']
    cursor.execute('SELECT COUNT(*) as cnt FROM quizzes')
    quiz_count = cursor.fetchone()['cnt']
    
    # Get recent attempts
    cursor.execute('''
        SELECT qa.score, qa.total_questions, u.username, q.title 
        FROM quiz_attempts qa 
        JOIN users u ON qa.student_id = u.id 
        JOIN quizzes q ON qa.quiz_id = q.id
        ORDER BY qa.attempt_date DESC LIMIT 5
    ''')
    recent_attempts = cursor.fetchall()
    
    # Get recent registrations
    cursor.execute('''
        SELECT u.username, u.role, 
               CASE 
                   WHEN u.role = 'student' THEN s.name 
                   WHEN u.role = 'teacher' THEN t.name 
                   ELSE u.username 
               END as name,
               u.id as user_id
        FROM users u 
        LEFT JOIN students s ON u.id = s.user_id 
        LEFT JOIN teacher t ON u.id = t.user_id 
        WHERE u.role IN ('student', 'teacher')
        ORDER BY u.id DESC LIMIT 10
    ''')
    recent_registrations = cursor.fetchall()
    
    # Get attendance data for chart
    cursor.execute('SELECT name, attendance_percent FROM students ORDER BY attendance_percent DESC LIMIT 10')
    attendance_records = cursor.fetchall()
    if attendance_records:
        attendance_data = {
            'labels': [record['name'] for record in attendance_records],
            'values': [record['attendance_percent'] for record in attendance_records]
        }
    else:
        attendance_data = {'labels': [], 'values': []}
    
    # Get quiz performance data (average scores over time)
    cursor.execute('''
        SELECT DATE(attempt_date) as date, AVG((score/total_questions)*100) as avg_score
        FROM quiz_attempts 
        GROUP BY DATE(attempt_date) 
        ORDER BY DATE(attempt_date) DESC LIMIT 10
    ''')
    quiz_performance_records = cursor.fetchall()

    cursor.execute('''
        SELECT asub.id, asub.title, asub.submitted_at, asub.score, asub.remark,
               COALESCE(s.name, u.username, 'Unknown') as student_name,
               COALESCE(asub.roll_number, s.roll_number, 'N/A') as roll_number
        FROM assignment_submissions asub
        LEFT JOIN users u ON asub.student_id = u.id
        LEFT JOIN students s ON asub.student_id = s.user_id
        ORDER BY asub.submitted_at DESC LIMIT 5
    ''')
    recent_assignments = cursor.fetchall()
    if quiz_performance_records:
        quiz_performance_data = {
            'labels': [
                record['date'].strftime('%d %b')
                for record in quiz_performance_records[::-1]
            ],
            'values': [round(record['avg_score'], 2) for record in quiz_performance_records[::-1]]
        }
    else:
        quiz_performance_data = {'labels': [], 'values': []}
    
    cursor.close()
    conn.close()
    
    return render_template('admin_dashboard.html', 
                           username=session['username'],
                           student_count=student_count,
                           teacher_count=teacher_count,
                           quiz_count=quiz_count,
                           recent_attempts=recent_attempts,
                           recent_registrations=recent_registrations,
                           attendance_data=attendance_data,
                           quiz_performance_data=quiz_performance_data,
                           recent_assignments=recent_assignments)

@app.route('/admin/add_students', methods=['GET', 'POST'])
def add_students():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        students_data = request.form.getlist('students')
        for student_json in students_data:
            student = json.loads(student_json)
            username = student['username']
            password = student['password']
            name = student['name']
            roll_number = student['roll_number']
            
            conn = get_db_connection()
            if not conn:
                flash("Database connection failed.", "danger")
                return redirect(url_for('add_students'))
            cursor = conn.cursor()
            
            try:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)',
                               (username, password, 'student'))
                user_id = cursor.lastrowid
                cursor.execute('INSERT INTO students (user_id, name, roll_number) VALUES (%s, %s, %s)',
                               (user_id, name, roll_number))
                conn.commit()
            except mysql.connector.Error as err:
                flash(f"Error adding student {name}: {err}", "danger")
                conn.rollback()
            finally:
                cursor.close()
                conn.close()
        
        flash("Students added successfully!", "success")
        return redirect(url_for('admin_dashboard'))
    
    return render_template('add_students.html', username=session['username'])

@app.route('/admin/add_teachers', methods=['GET', 'POST'])
def add_teachers():
    if session.get('role') != 'admin':
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        teachers_data = request.form.getlist('teachers')
        for teacher_json in teachers_data:
            teacher = json.loads(teacher_json)
            username = teacher['username']
            password = teacher['password']
            name = teacher['name']
            department = teacher['department']
            
            conn = get_db_connection()
            if not conn:
                flash("Database connection failed.", "danger")
                return redirect(url_for('add_teachers'))
            cursor = conn.cursor()
            
            try:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)',
                               (username, password, 'teacher'))
                user_id = cursor.lastrowid
                cursor.execute('INSERT INTO teacher (user_id, name, department) VALUES (%s, %s, %s)',
                               (user_id, name, department))
                conn.commit()
            except mysql.connector.Error as err:
                flash(f"Error adding teacher {name}: {err}", "danger")
                conn.rollback()
            finally:
                cursor.close()
                conn.close()
        
        flash("Teachers added successfully!", "success")
        return redirect(url_for('admin_dashboard'))
    
    return render_template('add_teachers.html', username=session['username'])

# --- Teacher Routes ---
@app.route('/teacher/dashboard', endpoint='teacher_dashboard')
def teacher_dashboard():
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
        
    search_roll = request.args.get('search_roll')
    attendance_search_student = None
    attendance_search_results = []

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT * FROM notes WHERE teacher_id = %s ORDER BY upload_date DESC', (session['id'],))
    notes = cursor.fetchall()
    
    cursor.execute('SELECT * FROM quizzes WHERE teacher_id = %s ORDER BY created_at DESC', (session['id'],))
    quizzes = cursor.fetchall()
    
    # Get all students for attendance
    cursor.execute('SELECT u.id, s.name, s.roll_number FROM users u JOIN students s ON u.id = s.user_id ORDER BY s.name')
    students = cursor.fetchall()
    
    # Get today's attendance records
    from datetime import date
    today = date.today()
    cursor.execute('SELECT student_id, status FROM attendance WHERE teacher_id = %s AND attendance_date = %s', (session['id'], today))
    attendance_records = {row['student_id']: row['status'] for row in cursor.fetchall()}

    # Search attendance by roll number
    if search_roll:
        cursor.execute('''
            SELECT u.id as student_id, s.name, s.roll_number
            FROM users u
            JOIN students s ON u.id = s.user_id
            WHERE s.roll_number = %s
        ''', (search_roll,))
        attendance_search_student = cursor.fetchone()
        if attendance_search_student:
            cursor.execute('''
                SELECT attendance_date, status
                FROM attendance
                WHERE student_id = %s
                ORDER BY attendance_date DESC
            ''', (attendance_search_student['student_id'],))
            attendance_search_results = cursor.fetchall()

    cursor.execute('''
        SELECT asub.id, asub.title, asub.file_path, asub.submitted_at, asub.score, asub.remark,
               u.username as student_username, s.name as student_name,
               COALESCE(asub.roll_number, s.roll_number) as roll_number
        FROM assignment_submissions asub
        LEFT JOIN users u ON asub.student_id = u.id
        LEFT JOIN students s ON asub.student_id = s.user_id
        ORDER BY asub.submitted_at DESC
    ''')
    assignment_submissions = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'teacher_dashboard.html',
        username=session['username'],
        notes=notes,
        quizzes=quizzes,
        students=students,
        attendance_records=attendance_records,
        today=today,
        assignment_submissions=assignment_submissions,
        attendance_search_student=attendance_search_student,
        attendance_search_results=attendance_search_results,
        search_roll=search_roll
    )

@app.route('/teacher/upload_note', methods=['POST'])
def upload_note():
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
        
    title = request.form.get('title')
    subject = request.form.get('subject')
    file = request.files.get('file')
    
    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please check MySQL.", "danger")
            return redirect(url_for('teacher_dashboard'))
        cursor = conn.cursor()
        cursor.execute('INSERT INTO notes (teacher_id, title, subject, file_path) VALUES (%s, %s, %s, %s)',
                       (session['id'], title, subject, filename))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Note uploaded successfully!', 'success')
    else:
        flash('Invalid file format. Only PDF allowed.', 'danger')
        
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/assignment_remark/<int:submission_id>', methods=['POST'])
def assignment_remark(submission_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))

    remark = request.form.get('remark')
    score = request.form.get('score')
    try:
        score_value = float(score) if score else None
    except ValueError:
        score_value = None

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('teacher_dashboard'))

    cursor = conn.cursor()
    cursor.execute('''
        UPDATE assignment_submissions
        SET remark = %s,
            score = %s,
            reviewed_by = %s
        WHERE id = %s
    ''', (remark, score_value, session['id'], submission_id))
    conn.commit()
    cursor.close()
    conn.close()

    flash('Assignment remark updated successfully!', 'success')
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/generate_quiz/<int:note_id>', methods=['POST'])
def generate_quiz(note_id):
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('teacher_dashboard'))
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM notes WHERE id = %s AND teacher_id = %s', (note_id, session['id']))
    note = cursor.fetchone()
    
    if note:
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], note['file_path'])
        text = extract_text_from_pdf(pdf_path)
        questions = generate_quiz_from_text(text)
        
        if questions:
            cursor.execute('INSERT INTO quizzes (teacher_id, note_id, title) VALUES (%s, %s, %s)',
                           (session['id'], note['id'], f"Quiz for {note['title']}"))
            quiz_id = cursor.lastrowid
            
            for q in questions:
                cursor.execute('''INSERT INTO questions 
                                  (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option) 
                                  VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                               (quiz_id, q['question_text'], q['option_a'], q['option_b'], q['option_c'], q['option_d'], q['correct_option']))
            conn.commit()
            flash(f'Quiz generated successfully with {len(questions)} questions!', 'success')
        else:
            pass # flash('Failed to generate quiz. Please ensure you have a valid GEMINI_API_KEY in your .env file and the PDF has readable text.', 'danger')
    
    cursor.close()
    conn.close()
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/mark_attendance', methods=['POST'])
def mark_attendance():
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
    
    student_id = request.form.get('student_id')
    status = request.form.get('status')
    
    from datetime import date
    today = date.today()
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('teacher_dashboard'))
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO attendance (student_id, teacher_id, attendance_date, status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status = VALUES(status)
        ''', (student_id, session['id'], today, status))
        conn.commit()
        flash('Attendance marked successfully!', 'success')
    except mysql.connector.Error as err:
        flash(f'Error marking attendance: {err}', 'danger')
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/view_attendance', methods=['GET'])
def view_attendance():
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
    
    date_str = request.args.get('date')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    from datetime import datetime
    selected_date = None
    range_start_date = None
    range_end_date = None

    if start_date_str or end_date_str:
        try:
            range_start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            range_end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Invalid date range.', 'danger')
            return redirect(url_for('teacher_dashboard'))

        if range_start_date > range_end_date:
            flash('From date cannot be after To date.', 'danger')
            return redirect(url_for('teacher_dashboard'))
    else:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
            return redirect(url_for('teacher_dashboard'))
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('teacher_dashboard'))
    
    cursor = conn.cursor(dictionary=True)
    
    # Get all students
    cursor.execute('SELECT u.id, s.name, s.roll_number FROM users u JOIN students s ON u.id = s.user_id ORDER BY s.name')
    students = cursor.fetchall()
    
    past_attendance_records = {}
    range_attendance_records = []

    if selected_date:
        # Get attendance records for the selected date
        cursor.execute('SELECT student_id, status FROM attendance WHERE teacher_id = %s AND attendance_date = %s', (session['id'], selected_date))
        past_attendance_records = {row['student_id']: row['status'] for row in cursor.fetchall()}

    if range_start_date and range_end_date:
        cursor.execute('''
            SELECT
                a.attendance_date,
                a.status,
                s.roll_number,
                s.name
            FROM attendance a
            JOIN users u ON a.student_id = u.id
            JOIN students s ON u.id = s.user_id
            WHERE a.teacher_id = %s
              AND a.attendance_date BETWEEN %s AND %s
            ORDER BY a.attendance_date DESC, s.name
        ''', (session['id'], range_start_date, range_end_date))
        range_attendance_records = cursor.fetchall()
    
    # Get today's data for the main attendance section
    from datetime import date
    today = date.today()
    cursor.execute('SELECT * FROM notes WHERE teacher_id = %s ORDER BY upload_date DESC', (session['id'],))
    notes = cursor.fetchall()
    
    cursor.execute('SELECT * FROM quizzes WHERE teacher_id = %s ORDER BY created_at DESC', (session['id'],))
    quizzes = cursor.fetchall()
    
    cursor.execute('SELECT student_id, status FROM attendance WHERE teacher_id = %s AND attendance_date = %s', (session['id'], today))
    attendance_records = {row['student_id']: row['status'] for row in cursor.fetchall()}
    
    cursor.close()
    conn.close()
    
    return render_template(
        'teacher_dashboard.html',
        username=session['username'],
        notes=notes,
        quizzes=quizzes,
        students=students,
        attendance_records=attendance_records,
        today=today,
        selected_date=selected_date,
        past_attendance_records=past_attendance_records,
        range_start_date=range_start_date,
        range_end_date=range_end_date,
        range_attendance_records=range_attendance_records
    )

@app.route('/teacher/mark_attendance_date', methods=['POST'])
def mark_attendance_date():
    if session.get('role') != 'teacher':
        return redirect(url_for('index'))
    
    student_id = request.form.get('student_id')
    status = request.form.get('status')
    attendance_date_str = request.form.get('attendance_date')
    
    from datetime import datetime
    try:
        attendance_date = datetime.strptime(attendance_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        flash('Invalid date format.', 'danger')
        return redirect(url_for('teacher_dashboard'))
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('teacher_dashboard'))
    
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO attendance (student_id, teacher_id, attendance_date, status)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE status = VALUES(status)
        ''', (student_id, session['id'], attendance_date, status))
        conn.commit()
        flash('Attendance marked successfully!', 'success')
    except mysql.connector.Error as err:
        flash(f'Error marking attendance: {err}', 'danger')
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('view_attendance', date=attendance_date_str))

# --- Student Routes ---
@app.route('/student/dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT * FROM notes ORDER BY upload_date DESC')
    notes = cursor.fetchall()
    
    cursor.execute('SELECT * FROM quizzes ORDER BY created_at DESC')
    quizzes = cursor.fetchall()
    
    cursor.execute('''
        SELECT qa.*, q.title as quiz_title 
        FROM quiz_attempts qa 
        JOIN quizzes q ON qa.quiz_id = q.id 
        WHERE qa.student_id = %s ORDER BY qa.attempt_date DESC
    ''', (session['id'],))
    attempts = cursor.fetchall()

    cursor.execute('''
        SELECT asub.id, asub.student_id, asub.title, asub.file_path, asub.submitted_at,
               asub.score, asub.remark, asub.reviewed_by,
               u.username as student_username, s.name as student_name,
               COALESCE(asub.roll_number, s.roll_number) as roll_number
        FROM assignment_submissions asub
        LEFT JOIN users u ON asub.student_id = u.id
        LEFT JOIN students s ON asub.student_id = s.user_id
        WHERE asub.student_id = %s
        ORDER BY asub.submitted_at DESC
    ''', (session['id'],))
    assignment_submissions = cursor.fetchall()

    cursor.execute('SELECT roll_number FROM students WHERE user_id = %s', (session['id'],))
    student_profile = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'student_dashboard.html',
        username=session['username'],
        notes=notes,
        quizzes=quizzes,
        attempts=attempts,
        assignment_submissions=assignment_submissions,
        student_profile=student_profile
    )

@app.route('/student/upload_assignment', methods=['POST'])
def upload_assignment():
    if session.get('role') != 'student':
        return redirect(url_for('index'))

    title = request.form.get('title') or 'Assignment'
    roll_number = (request.form.get('roll_number') or '').strip()
    file = request.files.get('file')
    allowed_extensions = {'pdf', 'docx', 'doc', 'txt'}

    if not roll_number:
        flash('Roll number is required to upload an assignment.', 'danger')
        return redirect(url_for('student_dashboard'))

    if file and '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['ASSIGNMENT_FOLDER'], filename)
        file.save(file_path)

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed. Please check MySQL.", "danger")
            return redirect(url_for('student_dashboard'))

        cursor = conn.cursor()
        cursor.execute('INSERT INTO assignment_submissions (student_id, title, roll_number, file_path) VALUES (%s, %s, %s, %s)',
                       (session['id'], title, roll_number, filename))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Assignment uploaded successfully!', 'success')
    else:
        flash('Invalid file format. Only PDF, DOCX, DOC, and TXT files are allowed.', 'danger')

    return redirect(url_for('student_dashboard'))

@app.route('/student/quiz_performance_data')
def student_quiz_performance_data():
    if session.get('role') != 'student':
        return jsonify({'labels': [], 'percentages': [], 'scores': [], 'totals': []}), 403

    conn = get_db_connection()
    if not conn:
        return jsonify({'labels': [], 'percentages': [], 'scores': [], 'totals': []}), 500

    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        SELECT qa.score, qa.total_questions, qa.attempt_date, q.title as quiz_title
        FROM quiz_attempts qa
        JOIN quizzes q ON qa.quiz_id = q.id
        WHERE qa.student_id = %s
        ORDER BY qa.attempt_date ASC
    ''', (session['id'],))
    attempts = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify({
        'labels': [
            f"{attempt['quiz_title']} ({attempt['attempt_date'].strftime('%d %b')})"
            for attempt in attempts
        ],
        'percentages': [
            round((attempt['score'] / attempt['total_questions']) * 100, 2)
            if attempt['total_questions'] else 0
            for attempt in attempts
        ],
        'scores': [attempt['score'] for attempt in attempts],
        'totals': [attempt['total_questions'] for attempt in attempts]
    })

@app.route('/student/take_quiz/<int:quiz_id>')
def take_quiz(quiz_id):
    if session.get('role') != 'student':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM quizzes WHERE id = %s', (quiz_id,))
    quiz = cursor.fetchone()
    
    cursor.execute('SELECT id, question_text, option_a, option_b, option_c, option_d FROM questions WHERE quiz_id = %s', (quiz_id,))
    questions = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('take_quiz.html', quiz=quiz, questions=questions)

@app.route('/student/submit_quiz/<int:quiz_id>', methods=['POST'])
def submit_quiz(quiz_id):
    if session.get('role') != 'student':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed. Please check MySQL.", "danger")
        return redirect(url_for('index'))
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT id, correct_option FROM questions WHERE quiz_id = %s', (quiz_id,))
    questions = cursor.fetchall()
    
    cursor.execute('SELECT n.subject FROM quizzes q JOIN notes n ON q.note_id = n.id WHERE q.id = %s', (quiz_id,))
    res = cursor.fetchone()
    subject = res['subject'] if res else "General"
    
    score = 0
    total = len(questions)
    
    for q in questions:
        ans = request.form.get(f"question_{q['id']}")
        if ans == q['correct_option']:
            score += 1
            
    # AI Analysis
    ai_feedback = generate_performance_analysis(score, total, subject)
    
    cursor.execute('''INSERT INTO quiz_attempts (student_id, quiz_id, score, total_questions, ai_analysis) 
                      VALUES (%s, %s, %s, %s, %s)''',
                   (session['id'], quiz_id, score, total, ai_feedback))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f'Quiz submitted! Score: {score}/{total}. Check dashboard for AI feedback.', 'success')
    return redirect(url_for('student_dashboard'))

@app.route('/download/note/<filename>')
def download_note(filename):
    if 'loggedin' not in session:
        return redirect(url_for('index'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@app.route('/download/assignment/<filename>')
def download_assignment(filename):
    if 'loggedin' not in session:
        return redirect(url_for('index'))
    return send_from_directory(app.config['ASSIGNMENT_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
