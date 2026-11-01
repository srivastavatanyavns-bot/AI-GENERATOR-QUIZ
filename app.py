
import json
import os
import sqlite3
import time
from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape

import fitz
import streamlit as st
from dotenv import load_dotenv
from google import genai
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

load_dotenv()

APP_TITLE = "AI Question Generator"
DB_PATH = "quiz_history.db"
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

st.set_page_config(page_title=APP_TITLE, page_icon="📚", layout="wide")


# ---------------- DATABASE ----------------

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS quiz_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                question_type TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                question_count INTEGER NOT NULL,
                score INTEGER,
                total INTEGER,
                questions_json TEXT NOT NULL
            )
        """)


# ---------------- TEXT EXTRACTION ----------------

def extract_text(uploaded_file):
    if uploaded_file is None:
        return ""

    data = uploaded_file.getvalue()

    if uploaded_file.name.lower().endswith(".pdf"):
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(
                page.get_text("text") for page in doc
            )

    return data.decode("utf-8", errors="replace")


# ---------------- PROMPT CREATION ----------------

def build_prompt(source, question_type, difficulty, count, topic):
    return f"""
Create academic questions using only the source material.
Do not invent facts or use outside knowledge.

Topic: {topic or "Not specified"}
Question type: {question_type}
Difficulty: {difficulty}
Number requested: {count}

Return JSON only in this format:

{{
 "questions": [
  {{
   "type": "MCQ",
   "question": "Question text",
   "options": [
      "A. option one",
      "B. option two",
      "C. option three",
      "D. option four"
   ],
   "answer": "B. option two",
   "explanation": "Brief explanation based on the source"
  }}
 ]
}}

Rules:
- Generate up to {count} questions.
- Use fewer questions only if the source is insufficient.
- MCQs must have four distinct options and one correct answer.
- Short-answer questions must use type "Short Answer" and options [].
- Mixed Quiz must include both question types.
- Easy means recall and definitions.
- Medium means explain and compare.
- Hard means apply and analyse.
- Keep questions clear and non-duplicative.
- Output valid JSON only, without Markdown fences.

SOURCE MATERIAL:
{source}
"""


# ---------------- GEMINI QUESTION GENERATION ----------------

def generate_questions(source, question_type, difficulty, count, topic):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key or api_key == "put_your_api_key_here":
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add your key to .env and restart the app."
        )

    client = genai.Client(api_key=api_key)

    schema = {
        "type": "OBJECT",
        "properties": {
            "questions": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "type": {"type": "STRING"},
                        "question": {"type": "STRING"},
                        "options": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"}
                        },
                        "answer": {"type": "STRING"},
                        "explanation": {"type": "STRING"}
                    },
                    "required": [
                        "type",
                        "question",
                        "options",
                        "answer",
                        "explanation"
                    ]
                }
            }
        },
        "required": ["questions"]
    }

    response = None
    prompt = build_prompt(
        source, question_type, difficulty, count, topic
    )

    # Retry temporary API errors up to three times.
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    "temperature": 0.3
                }
            )
            break

        except Exception as exc:
            message = str(exc)

            temporary_error = any(
                code in message
                for code in (
                    "503",
                    "UNAVAILABLE",
                    "429",
                    "RESOURCE_EXHAUSTED",
                    "500",
                    "INTERNAL"
                )
            )

            if not temporary_error or attempt == 2:
                raise

            time.sleep(2 ** (attempt + 1))

    if response is None or not response.text:
        raise ValueError(
            "Gemini returned an empty response. Please try again."
        )

    try:
        data = json.loads(response.text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Gemini did not return valid JSON. Please try again."
        ) from exc

    clean = []

    for item in data.get("questions", [])[:count]:
        if not isinstance(item, dict):
            continue

        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        q_type = str(
            item.get("type", "Short Answer")
        ).strip()

        options = item.get("options", [])

        if not question or not answer:
            continue

        if q_type.lower().startswith("mcq"):
            if not isinstance(options, list) or len(options) != 4:
                continue

            q_type = "MCQ"
        else:
            q_type = "Short Answer"
            options = []

        clean.append({
            "type": q_type,
            "question": question,
            "options": [str(x) for x in options],
            "answer": answer,
            "explanation": str(
                item.get("explanation", "")
            ).strip()
        })

    if not clean:
        raise ValueError(
            "No valid questions were returned. Try a longer source text."
        )

    return clean


# ---------------- SAVE QUIZ HISTORY ----------------

def save_history(
    topic,
    question_type,
    difficulty,
    questions,
    score=None,
    total=None
):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO quiz_history
            (
                created_at,
                topic,
                question_type,
                difficulty,
                question_count,
                score,
                total,
                questions_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(timespec="seconds"),
            topic or "Untitled topic",
            question_type,
            difficulty,
            len(questions),
            score,
            total,
            json.dumps(questions, ensure_ascii=False)
        ))


# ---------------- PDF GENERATION ----------------

def make_pdf(questions, title, include_answers=True):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm
    )

    styles = getSampleStyleSheet()

    story = [
        Paragraph(escape(title), styles["Title"]),
        Spacer(1, 12)
    ]

    for i, question in enumerate(questions, 1):
        story.append(
            Paragraph(
                f"<b>Q{i}. {escape(question['question'])}</b>",
                styles["BodyText"]
            )
        )

        story.append(Spacer(1, 5))

        for option in question.get("options", []):
            story.append(
                Paragraph(
                    escape(str(option)),
                    styles["BodyText"]
                )
            )

        if include_answers:
            story.append(
                Paragraph(
                    f"<b>Answer:</b> {escape(question['answer'])}",
                    styles["BodyText"]
                )
            )

            explanation = question.get("explanation", "")

            if explanation:
                story.append(
                    Paragraph(
                        f"<b>Explanation:</b> {escape(explanation)}",
                        styles["BodyText"]
                    )
                )

        story.append(Spacer(1, 12))

    doc.build(story)
    buffer.seek(0)

    return buffer.getvalue()


# ---------------- APPLICATION START ----------------

init_db()

st.title("📚 AI Question Generator")

st.write(
    "Turn your academic notes into quizzes using Google Gemini."
)

with st.sidebar:
    st.header("About this project")
    st.write("**AI provider:** Google Gemini")
    st.write(f"**Model:** `{MODEL_NAME}`")
    st.write(
        "Upload notes, generate questions, attempt MCQs, "
        "and export your quiz."
    )
    st.caption(
        "Review AI-generated answers before formal assessments."
    )

api_key = os.getenv("GEMINI_API_KEY")

if not api_key or api_key == "put_your_api_key_here":
    st.warning(
        "API key not found. Add GEMINI_API_KEY to your .env file "
        "and restart the app."
    )


# ---------------- INPUT MATERIAL ----------------

uploaded = st.file_uploader(
    "Upload academic material (PDF or TXT)",
    type=["pdf", "txt"]
)

pasted = st.text_area(
    "Or paste your academic content here",
    height=180,
    placeholder=(
        "Example: Photosynthesis is the process by which "
        "green plants use sunlight..."
    )
)

source = pasted.strip()

if uploaded:
    try:
        file_text = extract_text(uploaded).strip()

        if file_text:
            source = file_text
            st.success(
                f"Read {len(source):,} characters from {uploaded.name}."
            )
        else:
            st.warning(
                "No selectable text found. Scanned PDFs need OCR."
            )

    except Exception as exc:
        st.error(f"Could not read this file: {exc}")


# ---------------- QUIZ SETTINGS ----------------

with st.form("quiz_settings"):
    c1, c2, c3 = st.columns(3)

    with c1:
        topic = st.text_input(
            "Subject / topic",
            placeholder="e.g. Computer Science"
        )

        question_type = st.selectbox(
            "Question type",
            ["MCQ", "Short Answer", "Mixed Quiz"]
        )

    with c2:
        difficulty = st.selectbox(
            "Difficulty",
            ["Easy", "Medium", "Hard"]
        )

        count = st.slider(
            "Number of questions",
            1, 20, 5
        )

    with c3:
        st.markdown("**Source guidance**")
        st.caption(
            "Use clear notes. Maximum source length: 50,000 characters."
        )

    submitted = st.form_submit_button(
        "✨ Generate questions",
        type="primary",
        use_container_width=True
    )


# ---------------- GENERATE QUIZ ----------------

if submitted:
    if not source:
        st.error(
            "Please upload a PDF/TXT file or paste academic content."
        )

    elif len(source) > 50000:
        st.error(
            "This version supports up to 50,000 characters. "
            "Please use a shorter excerpt."
        )

    elif not api_key or api_key == "put_your_api_key_here":
        st.error(
            "Add your Gemini API key to .env, then restart Streamlit."
        )

    else:
        try:
            with st.spinner("Gemini is creating your quiz..."):
                generated = generate_questions(
                    source,
                    question_type,
                    difficulty,
                    count,
                    topic
                )

            st.session_state["questions"] = generated
            st.session_state["quiz_topic"] = topic or "Academic Quiz"
            st.session_state["quiz_type"] = question_type
            st.session_state["quiz_difficulty"] = difficulty
            st.session_state["last_score_saved"] = False

            st.session_state.pop("attempt_score", None)
            st.session_state.pop("attempt_total", None)

        except Exception as exc:
            st.error(f"Question generation failed: {exc}")

            message = str(exc)

            if "503" in message or "UNAVAILABLE" in message:
                st.info(
                    "Gemini may be temporarily overloaded. "
                    "The app retried automatically. Wait and try again, "
                    "or select a model available to your API key."
                )

            elif "429" in message or "RESOURCE_EXHAUSTED" in message:
                st.info(
                    "The API may have reached a rate or usage limit. "
                    "Check your Gemini API quota."
                )

            else:
                st.info(
                    "Check your internet connection, API key, "
                    "model setting, and API quota."
                )


# ---------------- DISPLAY GENERATED QUESTIONS ----------------

questions = st.session_state.get("questions", [])

if questions:
    st.divider()

    st.subheader(
        f"Generated quiz: "
        f"{st.session_state.get('quiz_topic', 'Academic Quiz')}"
    )

    st.caption(
        f"{len(questions)} questions · "
        f"{st.session_state.get('quiz_type', '')} · "
        f"{st.session_state.get('quiz_difficulty', '')}"
    )

    with st.form("attempt_quiz"):
        st.markdown("### Attempt the quiz")

        for i, question in enumerate(questions):
            st.markdown(
                f"**Q{i + 1}. {question['question']}**"
            )

            if question["type"] == "MCQ":
                st.radio(
                    "Select one answer",
                    question["options"],
                    key=f"quiz_answer_{i}",
                    index=None,
                    label_visibility="collapsed"
                )

            else:
                st.text_area(
                    "Your answer",
                    key=f"short_answer_{i}",
                    height=75
                )

            st.markdown("---")

        submitted_attempt = st.form_submit_button(
            "Submit MCQ answers and calculate score"
        )

    if submitted_attempt:
        score = 0
        total = 0

        for i, question in enumerate(questions):
            if question["type"] != "MCQ":
                continue

            total += 1
            chosen = st.session_state.get(f"quiz_answer_{i}")

            if (
                chosen
                and chosen.strip().casefold()
                == question["answer"].strip().casefold()
            ):
                score += 1

        st.session_state["attempt_score"] = score
        st.session_state["attempt_total"] = total
        st.session_state["last_score_saved"] = False

        if total:
            st.success(f"Your MCQ score: {score}/{total}")
        else:
            st.info(
                "No MCQs to score. Review the answer key below."
            )

    if "attempt_score" in st.session_state:
        score = st.session_state["attempt_score"]
        total = st.session_state["attempt_total"]

        if total:
            st.metric(
                "Latest MCQ score",
                f"{score}/{total}",
                f"{score / total:.0%}"
            )

        if not st.session_state.get("last_score_saved", False):
            if st.button("Save this quiz to history"):
                save_history(
                    st.session_state.get("quiz_topic", "Academic Quiz"),
                    st.session_state.get("quiz_type", ""),
                    st.session_state.get("quiz_difficulty", ""),
                    questions,
                    score,
                    total
                )

                st.session_state["last_score_saved"] = True
                st.success("Quiz saved to local history.")

    # Answer key
    with st.expander("Show answer key and explanations"):
        for i, question in enumerate(questions, 1):
            st.markdown(
                f"**Q{i}. {question['question']}**"
            )

            st.write("**Answer:**", question["answer"])

            if question.get("explanation"):
                st.write(
                    "**Explanation:**",
                    question["explanation"]
                )

    # Download options
    col_a, col_b, col_c = st.columns(3)

    quiz_json = json.dumps(
        {
            "topic": st.session_state.get(
                "quiz_topic", "Academic Quiz"
            ),
            "difficulty": st.session_state.get(
                "quiz_difficulty", ""
            ),
            "questions": questions
        },
        ensure_ascii=False,
        indent=2
    )

    with col_a:
        st.download_button(
            "Download JSON",
            data=quiz_json,
            file_name="generated_quiz.json",
            mime="application/json",
            use_container_width=True
        )

    with col_b:
        st.download_button(
            "Download PDF with answers",
            data=make_pdf(
                questions,
                "AI Generated Quiz — Answer Key",
                True
            ),
            file_name="quiz_with_answers.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with col_c:
        st.download_button(
            "Download student quiz PDF",
            data=make_pdf(
                questions,
                "AI Generated Quiz",
                False
            ),
            file_name="student_quiz.pdf",
            mime="application/pdf",
            use_container_width=True
        )


# ---------------- QUIZ HISTORY ----------------

st.divider()

with st.expander("Quiz history (stored on this computer)"):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT
                created_at,
                topic,
                question_type,
                difficulty,
                question_count,
                score,
                total
            FROM quiz_history
            ORDER BY id DESC
            LIMIT 20
        """).fetchall()

    if rows:
        st.dataframe(
            [
                {
                    "Date": row[0],
                    "Topic": row[1],
                    "Type": row[2],
                    "Difficulty": row[3],
                    "Questions": row[4],
                    "Score": (
                        f"{row[5]}/{row[6]}"
                        if row[5] is not None
                        else "Not scored"
                    )
                }
                for row in rows
            ],
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info(
            "No saved quizzes yet. Generate a quiz and save it to history."
        )
