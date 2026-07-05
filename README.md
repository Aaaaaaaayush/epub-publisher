# Semantic EPUB Digital Publisher

A fully automated, portable pipeline to convert styled Word documents (`.docx`) into premium, interactive, beautifully styled EPUB3 textbooks.

---

## 🚀 How to Run the Program

We have provided two self-contained batch launcher scripts to run the program without needing any terminal command experience.

### Option 1: Interactive Web Dashboard (FastAPI Localhost)
1. Double-click the **`run_web.bat`** file in the root folder.
2. The script will automatically start the FastAPI backend server and open the web dashboard in your default browser at **`http://127.0.0.1:8000`**.
3. In the web dashboard:
   - Upload any formatted Word document (`.docx`).
   - Fill in the title and author (or leave blank to extract automatically).
   - Review and dynamically edit text sections, formulas, list structures, or chapter layouts before final compilation.
   - Click Compile to download your customized EPUB textbook.

### Option 2: CLI Command Launcher
1. Double-click the **`run.bat`** file in the root folder.
2. When prompted:
   - Type or drag-and-drop your Word document (e.g., `docs/Ad_Making -Formatted.docx`) into the window.
   - Press **Enter**.
3. The pipeline will begin compiling. Your final EPUB file will be ready at **`reproduced.epub`** in the root directory!

---

## 🔑 Managing your Gemini API Key

The pipeline uses the **Google Gemini API** to run format verification and validation agents.

1. **Automatic Prompt**: On your first run, if the pipeline does not detect a Gemini API key in your environment or `.env` file, it will display a prompt in the console:
   ```
   Please enter your Gemini API Key: 
   ```
2. **Persistent Storage**: Once entered, the key is saved automatically inside your local `.env` file (`LLM_API_KEY="..."`). You will **not** be prompted to enter it again on subsequent runs.
3. **Fallback Mode**: If you do not have an API key or wish to run without AI verification, press **Enter** on the prompt. The pipeline will run in deterministic fallback mode.

---

## 📦 How to Port / Send to Someone Else

The entire project is designed to be **100% portable**. To share it:
1. Delete the `.venv/` directory and any compiled EPUBs in `reproduced.epub` to keep the file size small.
2. Zip the entire workspace folder (containing `run.bat`, `run_web.bat`, `app/`, `scripts/`, `requirements.txt`, etc.).
3. Send the zip file to anyone!
4. On their computer, they only need to:
   - Extract the zip folder.
   - Double-click **`run_web.bat`** or **`run.bat`** (which will automatically configure the Python virtual environment and dependencies on their system).
   - Enter their own Gemini API key when prompted.
