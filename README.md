# AI Question Generator — Google Gemini

A beginner-friendly college project that turns academic content into MCQs, short-answer questions, or mixed quizzes using the Google Gemini API.

## Features
- Upload PDF or TXT, or paste text
- Choose question type, difficulty, and question count
- Generate answers and explanations
- Attempt MCQs and calculate a score
- Export a student quiz PDF, answer-key PDF, and JSON
- Save quiz history locally with SQLite

## Requirements
- Python 3.10 or newer
- Internet connection
- Google Gemini API key

## Setup on Windows (VS Code)

1. Install Python from https://www.python.org/downloads/ and VS Code from https://code.visualstudio.com/.
2. Extract this project ZIP.
3. Open the extracted folder in VS Code.
4. Open Terminal > New Terminal.
5. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use Command Prompt terminal and run:
   ```bat
   .venv\Scripts\activate.bat
   ```

6. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

7. Copy `.env.example` to a new file named `.env`. Open `.env` and replace the placeholder with your own Gemini API key.
   Get a key at https://aistudio.google.com/apikey.
   Never share the key or upload `.env` to GitHub.

8. Run the app:

   ```bash
   streamlit run app.py
   ```

9. Open the local URL shown in the terminal, usually http://localhost:8501.

## Test data

Paste this sample:
"Photosynthesis is the process by which green plants use sunlight, water, and carbon dioxide to produce glucose and oxygen. Chlorophyll absorbs light energy."

Choose MCQ, Easy, and 3 questions. Generate the quiz, select answers, submit, then inspect the answer key and download the PDFs.

## Troubleshooting
- `GEMINI_API_KEY is missing`: confirm the `.env` file is in the same folder as `app.py`, with the exact filename `.env`, then restart Streamlit.
- Model not found / unavailable: change `GEMINI_MODEL` in `.env` to a text-generation model currently available to your Google AI Studio project.
- Quota or billing error: check API usage and limits in Google AI Studio.
- PDF has no extracted text: it may be a scanned image. This version extracts selectable PDF text and does not include OCR.
- Invalid output: try a shorter, clearer source passage and generate again.
- Do not use generated answers without checking them against the source.

## Project structure
- `app.py`: complete Streamlit app
- `requirements.txt`: Python dependencies
- `.env.example`: API key template
- `PROJECT_REPORT.md`: report draft you can customize
- `PRESENTATION_OUTLINE.md`: viva/presentation outline
- `.gitignore`: prevents secrets and local database from being committed

## Academic note
This is a working student-project starter. Test it with your course materials, add screenshots of your own runs, record observed limitations, and cite the official Gemini documentation in your report.
