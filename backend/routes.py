import json
import logging
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from backend.database import (
    create_exam, update_exam_questions, mark_exam_failed,
    get_exam_by_code, get_exam_by_id, get_all_exams,
    get_exam_submission_count, save_submission, get_exam_submissions,
    get_submission_by_id, save_analysis, get_analysis, check_student_submitted
)
from backend.gemini_service import GeminiService
from backend.config import get_config

main = Blueprint('main', __name__)

# Initialize Gemini Service lazily
_gemini = None

def get_gemini():
    global _gemini
    if _gemini is None:
        config = get_config()
        try:
            _gemini = GeminiService(config['gemini_key'])
        except Exception as e:
            _gemini = None  # Reset so it retries on next request
            raise
    return _gemini


# ============================================================
# TEACHER ROUTES
# ============================================================

@main.route('/')
def dashboard():
    """Teacher dashboard — list all exams."""
    exams = get_all_exams()
    # Attach submission counts
    for exam in exams:
        exam['submission_count'] = get_exam_submission_count(exam['id'])
    return render_template('dashboard.html', exams=exams)


@main.route('/create')
def create_exam_page():
    """Show create exam form."""
    return render_template('create-exam.html')


@main.route('/api/generate', methods=['POST'])
def api_generate():
    """Generate MCQs from topics using Gemini AI."""
    try:
        data = request.get_json()
        title = data.get('title', '').strip()
        topics_raw = data.get('topics', '').strip()
        question_count = int(data.get('question_count', 10))

        if not title:
            return jsonify({"error": "Exam title is required"}), 400
        if not topics_raw:
            return jsonify({"error": "Topics are required"}), 400
        if question_count < 1 or question_count > 50:
            return jsonify({"error": "Question count must be between 1 and 50"}), 400

        # Create exam record first
        exam_id, exam_code = create_exam(title, topics_raw, question_count)

        # Generate MCQs
        gemini = get_gemini()
        questions_json = gemini.generate_mcqs(topics_raw, question_count)

        # Store questions
        update_exam_questions(exam_id, questions_json)

        return jsonify({
            "success": True,
            "exam_id": exam_id,
            "exam_code": exam_code,
            "questions": json.loads(questions_json)
        })

    except Exception as e:
        logging.error(f"Generation Error: {e}")
        # Mark exam as failed if it was created
        if 'exam_id' in locals():
            mark_exam_failed(exam_id)
        return jsonify({"error": str(e)}), 500


@main.route('/results/<int:exam_id>')
def results_page(exam_id):
    """Teacher views all submissions for an exam."""
    exam = get_exam_by_id(exam_id)
    if not exam:
        return "Exam not found", 404

    submissions = get_exam_submissions(exam_id)
    # Attach analysis status
    for sub in submissions:
        analysis = get_analysis(sub['id'])
        sub['has_analysis'] = analysis is not None
        if analysis:
            sub['analysis'] = json.loads(analysis['analysis_json'])

    return render_template('results.html', exam=exam, submissions=submissions)


@main.route('/api/analyze/<int:submission_id>', methods=['POST'])
def api_analyze(submission_id):
    """Trigger AI analysis for a student's submission."""
    try:
        submission = get_submission_by_id(submission_id)
        if not submission:
            return jsonify({"error": "Submission not found"}), 404

        exam = get_exam_by_id(submission['exam_id'])
        if not exam:
            return jsonify({"error": "Exam not found"}), 404

        gemini = get_gemini()
        analysis_json = gemini.analyze_results(
            exam['questions_json'],
            submission['answers_json'],
            submission['student_name']
        )

        save_analysis(submission_id, analysis_json)

        return jsonify({
            "success": True,
            "analysis": json.loads(analysis_json)
        })

    except Exception as e:
        logging.error(f"Analysis Error: {e}")
        return jsonify({"error": str(e)}), 500


@main.route('/api/results/<int:submission_id>')
def api_get_results(submission_id):
    """Get analysis results for a submission."""
    analysis = get_analysis(submission_id)
    if not analysis:
        return jsonify({"error": "No analysis found. Click 'Analyze' first."}), 404
    return jsonify(json.loads(analysis['analysis_json']))


# ============================================================
# STUDENT ROUTES
# ============================================================

@main.route('/exam/<code>')
def exam_page(code):
    """Student exam page — accessed via shareable link."""
    exam = get_exam_by_code(code)
    if not exam:
        return render_template('exam.html', error="Exam not found. Please check the link.")
    if exam['status'] != 'ready':
        return render_template('exam.html', error="This exam is still being prepared. Please try again shortly.")
    return render_template('exam.html', exam=exam)


@main.route('/api/submit', methods=['POST'])
def api_submit():
    """Student submits their exam answers."""
    try:
        data = request.get_json()
        exam_code = data.get('exam_code', '')
        student_name = data.get('student_name', '').strip()
        student_email = data.get('student_email', '').strip()
        answers = data.get('answers', {})
        violations = int(data.get('violations', 0))

        if not student_name or not student_email:
            return jsonify({"error": "Name and email are required"}), 400

        exam = get_exam_by_code(exam_code)
        if not exam:
            return jsonify({"error": "Invalid exam code"}), 404

        # Check if already submitted
        if check_student_submitted(exam['id'], student_email):
            return jsonify({"error": "You have already submitted this exam."}), 400

        # Calculate score
        questions = json.loads(exam['questions_json'])
        q_list = questions.get('questions', [])
        score = 0
        total = len(q_list)

        for q in q_list:
            q_id = str(q['id'])
            if answers.get(q_id) == q['answer']:
                score += 1

        # Save
        submission_id = save_submission(
            exam['id'], student_name, student_email,
            json.dumps(answers), score, total, violations
        )

        return jsonify({
            "success": True,
            "message": "Your exam has been submitted successfully!",
            "submission_id": submission_id,
            "score": score,
            "total": total
        })

    except Exception as e:
        logging.error(f"Submission Error: {e}")
        return jsonify({"error": str(e)}), 500


@main.route('/api/exam/<code>')
def api_get_exam(code):
    """Get exam questions (for student-side JavaScript)."""
    exam = get_exam_by_code(code)
    if not exam:
        return jsonify({"error": "Exam not found"}), 404
    if exam['status'] != 'ready':
        return jsonify({"error": "Exam not ready"}), 400

    questions = json.loads(exam['questions_json'])
    # Remove answers and explanations for students!
    safe_questions = []
    for q in questions.get('questions', []):
        safe_questions.append({
            "id": q['id'],
            "topic": q.get('topic', ''),
            "type": q.get('type', 'theory'),
            "question": q['question'],
            "options": q['options']
        })

    return jsonify({
        "title": exam['title'],
        "exam_code": exam['exam_code'],
        "questions": safe_questions,
        "total": len(safe_questions)
    })
