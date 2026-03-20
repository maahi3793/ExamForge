import sqlite3
import os
import string
import random
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'examforge.db')


def get_db():
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            topics_raw TEXT NOT NULL,
            question_count INTEGER NOT NULL,
            questions_json TEXT,
            exam_code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'generating',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER NOT NULL,
            student_name TEXT NOT NULL,
            student_email TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            score INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            violations INTEGER DEFAULT 0,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (exam_id) REFERENCES exams(id)
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL UNIQUE,
            analysis_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (submission_id) REFERENCES submissions(id)
        );
    ''')

    conn.commit()
    conn.close()


def generate_exam_code():
    """Generate a unique 6-character exam code."""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=6))
        conn = get_db()
        existing = conn.execute("SELECT id FROM exams WHERE exam_code = ?", (code,)).fetchone()
        conn.close()
        if not existing:
            return code


def create_exam(title, topics_raw, question_count):
    """Create a new exam record and return the exam code."""
    code = generate_exam_code()
    conn = get_db()
    conn.execute(
        "INSERT INTO exams (title, topics_raw, question_count, exam_code) VALUES (?, ?, ?, ?)",
        (title, topics_raw, question_count, code)
    )
    conn.commit()
    exam_id = conn.execute("SELECT id FROM exams WHERE exam_code = ?", (code,)).fetchone()['id']
    conn.close()
    return exam_id, code


def update_exam_questions(exam_id, questions_json):
    """Store generated questions and mark exam as ready."""
    conn = get_db()
    conn.execute(
        "UPDATE exams SET questions_json = ?, status = 'ready' WHERE id = ?",
        (questions_json, exam_id)
    )
    conn.commit()
    conn.close()


def mark_exam_failed(exam_id):
    """Mark exam generation as failed."""
    conn = get_db()
    conn.execute("UPDATE exams SET status = 'failed' WHERE id = ?", (exam_id,))
    conn.commit()
    conn.close()


def get_exam_by_code(code):
    """Fetch an exam by its shareable code."""
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE exam_code = ?", (code,)).fetchone()
    conn.close()
    return dict(exam) if exam else None


def get_exam_by_id(exam_id):
    """Fetch an exam by ID."""
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    conn.close()
    return dict(exam) if exam else None


def get_all_exams():
    """Get all exams, newest first."""
    conn = get_db()
    exams = conn.execute("SELECT * FROM exams ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(e) for e in exams]


def get_exam_submission_count(exam_id):
    """Get number of submissions for an exam."""
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) as count FROM submissions WHERE exam_id = ?", (exam_id,)
    ).fetchone()['count']
    conn.close()
    return count


def save_submission(exam_id, student_name, student_email, answers_json, score, total, violations):
    """Save a student's exam submission."""
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO submissions 
           (exam_id, student_name, student_email, answers_json, score, total, violations) 
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (exam_id, student_name, student_email, answers_json, score, total, violations)
    )
    submission_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return submission_id


def get_exam_submissions(exam_id):
    """Get all submissions for an exam."""
    conn = get_db()
    subs = conn.execute(
        "SELECT * FROM submissions WHERE exam_id = ? ORDER BY submitted_at DESC", (exam_id,)
    ).fetchall()
    conn.close()
    return [dict(s) for s in subs]


def get_submission_by_id(submission_id):
    """Get a single submission."""
    conn = get_db()
    sub = conn.execute("SELECT * FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    conn.close()
    return dict(sub) if sub else None


def save_analysis(submission_id, analysis_json):
    """Save AI analysis for a submission."""
    conn = get_db()
    # Upsert — replace if already exists
    conn.execute(
        """INSERT INTO results (submission_id, analysis_json) VALUES (?, ?)
           ON CONFLICT(submission_id) DO UPDATE SET analysis_json = ?, created_at = CURRENT_TIMESTAMP""",
        (submission_id, analysis_json, analysis_json)
    )
    conn.commit()
    conn.close()


def get_analysis(submission_id):
    """Get analysis for a submission."""
    conn = get_db()
    result = conn.execute(
        "SELECT * FROM results WHERE submission_id = ?", (submission_id,)
    ).fetchone()
    conn.close()
    return dict(result) if result else None


def check_student_submitted(exam_id, student_email):
    """Check if a student has already submitted for this exam."""
    conn = get_db()
    sub = conn.execute(
        "SELECT id FROM submissions WHERE exam_id = ? AND student_email = ?",
        (exam_id, student_email)
    ).fetchone()
    conn.close()
    return sub is not None
