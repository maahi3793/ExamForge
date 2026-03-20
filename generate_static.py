import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

topics_str = """
2. Variables and Simple Data Types (Integers, Floats)
3. Basic Arithmetic and Order of Operations
4. Introduction to Strings (Creation and Concatenation)
5. Essential String Methods (.upper(), .lower(), .strip())
6. String Slicing and Indexing
7. User Input and Type Conversion (int(), str())
8. Booleans and Comparison Operators
9. Logical Operators (and, or, not)
10. Control Flow: The if, elif, and else statements
11. Introduction to Lists (Creating and Indexing)
12. List Methods (Append, Insert, Remove, Pop)
13. The for Loop (Iterating over Lists)
14. The range() function and Loops
15. The while Loop and Infinite Loops
16. Control Statements (break, continue, pass)
17. Introduction to Dictionaries (Key-Value pairs)
18. Dictionary Methods (.keys(), .values(), .items())
19. Introduction to Tuples (Immutability)
20. Introduction to Sets (Uniqueness)
21. Defining Functions (def) and the return statement
22. Function Parameters vs Arguments (Positional vs Keyword)
"""

total_questions = 50
chunk_size = 15

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
all_questions = []

chunks = []
remaining = total_questions
while remaining > 0:
    if remaining >= chunk_size:
        chunks.append(chunk_size)
        remaining -= chunk_size
    else:
        chunks.append(remaining)
        remaining = 0

print(f"Generating 50 MCQs locally...")

for i, count in enumerate(chunks):
    print(f"Generating chunk {i+1}/{len(chunks)} ({count} questions)...")
    if i > 0:
        time.sleep(3)
        
    for attempt in range(3):
        try:
            prompt = f"""
            You are a senior technical interviewer creating an assessment for a developer with 2+ years of experience.
            Generate EXACTLY {count} tough, thought-provoking Multiple Choice Questions.
            DO NOT generate basic syntax questions. The questions should test deep understanding, edge cases, performance implications, and actual code output.

            TOPICS TO COVER:
            {topics_str}

            DISTRIBUTION AND DIFFICULTY:
            - Target Audience: 2+ Years Experience (Mid-level).
            - Mix question types: ~20% Deep Architecture/Theory, ~80% Tricky Code-Output / Debugging / Edge Cases.
            - Vary difficulty: ~20% Warm-up (but still not beginner), ~50% Challenging, ~30% Expert/Gotcha.

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
            1. Return ONLY the raw JSON. No markdown fences.
            2. Generate EXACTLY {count} questions.
            3. Each question MUST have exactly 4 options prefixed with A), B), C), D).
            4. "answer" MUST exactly match one of the "options".
            5. Questions must ONLY test topics from the provided list.
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )

            text = response.text.strip()
            if text.startswith("```json"): text = text[7:]
            elif text.startswith("```"): text = text[3:]
            if text.endswith("```"): text = text[:-3]
            text = text.strip()

            data = json.loads(text)
            questions = data.get('questions', [])
            for q in questions:
                q['id'] = len(all_questions) + questions.index(q) + 1
            
            all_questions.extend(questions)
            print(f"  ✓ Success! Got {len(questions)} questions.")
            break
        except Exception as e:
            err_str = str(e)
            print(f"  ✗ Attempt {attempt+1} failed: {err_str[:250]}...")
            
            if '429' in err_str or 'ResourceExhausted' in err_str or 'quota' in err_str.lower():
                print(f"    [!] Rate limited! Backing off for 45 seconds to respect Google's quotas...")
                time.sleep(45)
            else:
                print(f"    [!] General error. Sleeping for 10 seconds...")
                time.sleep(10)
                
            if attempt == 2:
                print("Failed after 3 attempts. Exiting.")
                with open("static_exam_data_PARTIAL.json", "w") as f:
                    json.dump(all_questions, f, indent=2)
                exit(1)

with open("static_exam_data.json", "w") as f:
    json.dump(all_questions, f, indent=2)

print(f"Successfully wrote {len(all_questions)} questions to static_exam_data.json!")
