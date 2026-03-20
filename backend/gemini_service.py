import os
import time
import json
import logging
from google import genai
from google.genai import types

# Setup Logging
logging.basicConfig(
    filename='examforge.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class GeminiService:
    def __init__(self, api_key):
        if not api_key:
            logging.error("GeminiService initialized without API Key")
            raise ValueError("API Key is missing. Please set GEMINI_API_KEY in your .env file.")

        # Check for placeholder key
        if api_key.startswith('your_') or api_key == 'your_gemini_api_key_here':
            print("\n❌ ERROR: You still have the placeholder API key in .env!")
            print("   Please replace 'your_gemini_api_key_here' with your actual Gemini API key.")
            print("   Get one free at: https://aistudio.google.com/apikey\n")
            raise ValueError("API key is still the placeholder. Please set your real Gemini API key in .env file.")

        print(f"🔑 Configuring Gemini with Key: {api_key[:5]}...{api_key[-3:]}")
        logging.info(f"Configuring Gemini with Key: {api_key[:5]}...{api_key[-3:]}")
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-2.5-flash'
        print(f"🤖 Using Model: {self.model_name}")
        logging.info(f"Using Model: {self.model_name}")

        self.system_instruction = """
You are "ExamForge AI", an expert educational assessment engine.
Your mission: Generate high-quality, fair, and accurate Multiple Choice Questions (MCQs) 
and provide detailed, constructive student performance analysis.
Tone: Professional, precise, and educational.
"""

    def parse_topics(self, raw_text):
        """Parse a curriculum dump into a clean list of topics."""
        lines = raw_text.strip().split('\n')
        topics = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Skip headers (lines starting with # or ##)
            if line.startswith('#'):
                continue
            # Skip lines that look like phase/goal descriptions
            if line.lower().startswith('goal:'):
                continue
            # Remove numbering (e.g., "1.", "2.", "1)", "a)")
            cleaned = re.sub(r'^[\d]+[\.\)]\s*', '', line).strip()
            # Remove bullet points
            cleaned = re.sub(r'^[-•*]\s*', '', cleaned).strip()
            if cleaned and len(cleaned) > 3:
                topics.append(cleaned)
        return topics

    def generate_mcqs(self, topics_raw, question_count):
        """Generate MCQs from a curriculum dump using Gemini AI."""
        topics = self.parse_topics(topics_raw)
        if not topics:
            raise ValueError("No valid topics found in the input. Please check your topic list.")

        topics_str = "\n".join([f"- {t}" for t in topics])
        print(f"\n📝 Parsed {len(topics)} topics from input:")
        for t in topics[:5]:
            print(f"   • {t}")
        if len(topics) > 5:
            print(f"   ... and {len(topics) - 5} more")
        
        all_questions = []
        chunk_size = 15 # Max questions per API call to avoid JSON truncation
        
        chunks = []
        remaining = question_count
        while remaining > 0:
            if remaining >= chunk_size:
                chunks.append(chunk_size)
                remaining -= chunk_size
            else:
                chunks.append(remaining)
                remaining = 0

        logging.info(f"Generating {question_count} MCQs in {len(chunks)} chunks: {chunks}")
        print(f"🎯 Generating {question_count} MCQs in {len(chunks)} chunks...")
        
        for i, count in enumerate(chunks):
            if i > 0:
                print(f"\n⏳ Sleeping for 15 seconds to respect Gemini API free-tier rate limits...")
                logging.info(f"Sleeping for 15 seconds to respect Gemini API rate limits...")
                time.sleep(15)
                
            print(f"\n⏳ Processing Chunk {i+1}/{len(chunks)} ({count} questions)...")
            logging.info(f"Processing Chunk {i+1}/{len(chunks)} ({count} questions)...")
            chunk_results = self._generate_mcq_chunk(topics_str, count, current_id_offset=len(all_questions))
            all_questions.extend(chunk_results)
            
        final_json = {
            "questions": all_questions
        }
        print(f"✅ All {question_count} MCQs generated successfully.")
        logging.info(f"✅ All {question_count} MCQs generated successfully.")
        return json.dumps(final_json)

    def _generate_mcq_chunk(self, topics_str: str, question_count: int, current_id_offset: int) -> list:
        """Generate a specific chunk of MCQs, with retry logic."""
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                logging.info(f"Chunk Attempt {attempt + 1}/{max_retries} for {question_count} questions")

                prompt = f"""
                You are a senior technical interviewer creating an assessment for a developer with 2+ years of experience.
                Generate EXACTLY {question_count} tough, thought-provoking Multiple Choice Questions.
                DO NOT generate basic syntax questions. The questions should test deep understanding, edge cases, performance implications, and actual code output.

                TOPICS TO COVER:
                {topics_str}

                DISTRIBUTION AND DIFFICULTY:
                - Target Audience: 2+ Years Experience (Mid-level).
                - Mix question types: ~20% Deep Architecture/Theory, ~80% Tricky Code-Output / Debugging / Edge Cases.
                - Vary difficulty: ~20% Warm-up (but still not beginner), ~50% Challenging, ~30% Expert/Gotcha.
                - The goal is to make them think hard and learn, but not feel unfairly tricked by syntax typos.

                JSON SCHEMA (Return ONLY this JSON, no markdown):
                {{
                    "questions": [
                        {{
                            "id": 1,
                            "topic": "The specific topic this tests",
                            "difficulty": "medium|hard|expert",
                            "type": "theory|code_output|debugging",
                            "question": "The question text. For code questions, include a realistic, slightly complex code snippet.",
                            "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
                            "answer": "A) option1",
                            "explanation": "Detailed explanation of why this is the correct answer and why the others are wrong/common traps."
                        }}
                    ]
                }}

                STRICT RULES:
                1. Return ONLY the raw JSON. No markdown fences, no commentary.
                2. Generate EXACTLY {question_count} questions.
                3. Each question MUST have exactly 4 options prefixed with A), B), C), D).
                4. "answer" MUST exactly match one of the "options".
                5. Options must be highly plausible. Wrong answers should represent common senior-level misconceptions.
                6. Include complex realistic code snippets (e.g., using closures, generators, decorators, subtle reference bugs if testing Python).
                7. Questions must ONLY test topics from the provided list.
                """

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=self.system_instruction,
                        response_mime_type="application/json",
                    )
                )

                # Clean markdown fences if they wrap the entire response
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                elif text.startswith("```"):
                    text = text[3:]
                
                if text.endswith("```"):
                    text = text[:-3]
                    
                text = text.strip()

                # Parse and validate
                if not text.startswith("{"):
                    raise ValueError("Output is not valid JSON")

                data = json.loads(text)
                questions = data.get('questions', [])

                if len(questions) != question_count:
                    raise ValueError(f"Got {len(questions)} questions, expected {question_count}")

                for q in questions:
                    if not q.get('question'):
                        raise ValueError("Empty question text found")
                    options = q.get('options', [])
                    if len(options) != 4:
                        raise ValueError(f"Question has {len(options)} options instead of 4")
                    answer = q.get('answer', '')
                    if answer not in options:
                        raise ValueError(f"Answer '{answer}' not in options")
                    for opt in options:
                        if len(opt.strip()) < 3:
                            raise ValueError(f"Empty/malformed option: '{opt}'")
                            
                    # Fix ID ordering for combined chunks
                    q['id'] = current_id_offset + questions.index(q) + 1

                print(f"✅ Valid MCQ Chunk generated: {question_count} questions")
                return questions

            except Exception as e:
                last_error = str(e)
                print(f"❌ Chunk Attempt {attempt + 1} failed: {e}")
                logging.warning(f"Chunk Attempt {attempt + 1} failed: {e}")
                
                # Debugging: Dump the exact text that failed parsing
                print("\n" + "="*50)
                print("🚨 DEBUG: FAILED RAW RESPONSE TEXT 🚨")
                print("="*50)
                try:
                    print(response.text)
                except Exception as text_err:
                    print(f"(Could not print response.text: {text_err})")
                try:
                    print("clean text variable:", text)
                except:
                    pass
                print("="*50 + "\n")
                
                # Don't retry on API key errors — they'll fail every time
                if 'API_KEY_INVALID' in str(e) or 'API key not valid' in str(e):
                    print("\n🔑 Your API key is invalid! Please check your .env file.")
                    raise Exception("Your Gemini API key is invalid. Please check the GEMINI_API_KEY in your .env file and restart the app.")
                
                time.sleep(2)

        logging.error("All MCQ generation retries failed.")
        error_msg = f"Failed to generate MCQs after {max_retries} attempts."
        if last_error:
            error_msg += f" Last error: {last_error}"
        raise Exception(error_msg)

    def analyze_results(self, questions_json, student_answers, student_name):
        """Analyze a student's exam performance using Gemini AI."""
        logging.info(f"Analyzing results for student: {student_name}")

        try:
            questions = json.loads(questions_json) if isinstance(questions_json, str) else questions_json
            answers = json.loads(student_answers) if isinstance(student_answers, str) else student_answers

            q_list = questions.get('questions', questions) if isinstance(questions, dict) else questions

            # Build a detailed comparison for Gemini
            comparison = []
            correct_count = 0
            total = len(q_list)

            for q in q_list:
                q_id = str(q['id'])
                student_answer = answers.get(q_id, "Not answered")
                is_correct = student_answer == q['answer']
                if is_correct:
                    correct_count += 1
                comparison.append({
                    "question_id": q['id'],
                    "topic": q.get('topic', 'General'),
                    "difficulty": q.get('difficulty', 'medium'),
                    "question": q['question'][:200],  # Truncate for token efficiency
                    "correct_answer": q['answer'],
                    "student_answer": student_answer,
                    "is_correct": is_correct,
                    "explanation": q.get('explanation', '')
                })

            prompt = f"""
            You are a Senior Academic Mentor analyzing exam results for a student.

            STUDENT: {student_name}
            SCORE: {correct_count}/{total} ({round(correct_count/total*100) if total > 0 else 0}%)

            DETAILED ANSWERS:
            {json.dumps(comparison, indent=2)}

            TASK: Provide a comprehensive, honest, and constructive analysis.

            OUTPUT JSON SCHEMA (Return ONLY this JSON):
            {{
                "overall_score": "{correct_count}/{total}",
                "percentage": {round(correct_count/total*100) if total > 0 else 0},
                "grade": "A+/A/B+/B/C+/C/D/F based on percentage",
                "overall_assessment": "2-3 sentences about where the student stands overall. Be specific and honest.",
                "strengths": [
                    {{
                        "topic": "Topic name",
                        "detail": "What they demonstrated well"
                    }}
                ],
                "weaknesses": [
                    {{
                        "topic": "Topic name",
                        "detail": "What they struggled with specifically",
                        "suggestion": "Concrete action to improve"
                    }}
                ],
                "wrong_answers": [
                    {{
                        "question_id": 1,
                        "question": "The question text (brief)",
                        "student_answered": "What they chose",
                        "correct_answer": "The right answer",
                        "why_wrong": "Brief explanation of the misconception"
                    }}
                ],
                "topics_to_revisit": ["Topic 1", "Topic 2"],
                "study_recommendations": "A paragraph of personalized study advice based on the error patterns.",
                "readiness_level": "Not Ready / Needs Work / Almost There / Solid / Excellent"
            }}

            RULES:
            1. Return ONLY valid JSON. No markdown.
            2. Be specific — mention exact concepts, not vague statements.
            3. For "wrong_answers", include ALL questions they got wrong.
            4. "study_recommendations" should reference the specific topics they need to revisit.
            5. Be encouraging but honest. Don't sugarcoat if the performance is poor.
            """

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    response_mime_type="application/json",
                )
            )

            text = response.text.strip()
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()

            # Validate it's valid JSON
            parsed = json.loads(text)
            logging.info(f"✅ Analysis generated for {student_name}")
            return json.dumps(parsed)

        except Exception as e:
            logging.error(f"Analysis Error for {student_name}: {e}")
            # Return a basic analysis if AI fails
            return json.dumps({
                "overall_score": f"{correct_count}/{total}",
                "percentage": round(correct_count / total * 100) if total > 0 else 0,
                "grade": "N/A",
                "overall_assessment": f"Analysis could not be generated. Score: {correct_count}/{total}.",
                "strengths": [],
                "weaknesses": [],
                "wrong_answers": [],
                "topics_to_revisit": [],
                "study_recommendations": "Please retry the analysis.",
                "readiness_level": "Unknown",
                "error": str(e)
            })
