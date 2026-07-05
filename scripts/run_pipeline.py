import os
import sys
import shutil
from pathlib import Path

# Add root folder to python path so we can resolve app package
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.config.settings import settings
from app.database.session import init_db, db_session
from app.agents.coordinator import PipelineCoordinator
from app.utils.logger import logger

import argparse

def ensure_api_key():
    env_path = settings.WORKSPACE_DIR / ".env"
    api_key = os.environ.get("LLM_API_KEY")
    
    # If not in env, check .env file
    if not api_key and env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("LLM_API_KEY"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        val = parts[1].strip().strip('"').strip("'")
                        if val and "your-api-key" not in val.lower() and "placeholder" not in val.lower():
                            api_key = val
                            break
                            
    # If key is missing or placeholder, prompt the user
    if not api_key or "your-api-key" in api_key.lower() or "placeholder" in api_key.lower():
        # Setup .env if it doesn't exist by copying example
        if not env_path.exists():
            example_path = settings.WORKSPACE_DIR / ".env.example"
            if example_path.exists():
                shutil.copy2(example_path, env_path)
                # Clean the placeholder in the copy
                lines = []
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("LLM_API_KEY="):
                            lines.append('LLM_API_KEY=""\n')
                        else:
                            lines.append(line)
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)

        print("\n" + "="*60)
        print("                   GEMINI API KEY REQUIRED")
        print("="*60)
        print("To run the AI formatting and validation agents, you need a Gemini API key.")
        print("If you don't have one, you can get it from Google AI Studio.")
        print("Press Enter to run in deterministic fallback mode (without AI agents).")
        print("-"*60)
        
        while True:
            user_input = input("Please enter your Gemini API Key: ").strip()
            if not user_input:
                print("Running in deterministic fallback mode (No AI formatting/validation).")
                break
            else:
                api_key = user_input
                # Save/Update in .env
                lines = []
                key_replaced = False
                if env_path.exists():
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("LLM_API_KEY"):
                                lines.append(f'LLM_API_KEY="{api_key}"\n')
                                key_replaced = True
                            else:
                                lines.append(line)
                
                if not key_replaced:
                    lines.append(f'\n# Gemini API Key\nLLM_API_KEY="{api_key}"\n')
                    
                with open(env_path, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                
                print("API key successfully saved to .env file!")
                os.environ["LLM_API_KEY"] = api_key
                settings.LLM_API_KEY = api_key
                break
        print("="*60 + "\n")

def main():
    ensure_api_key()
    parser = argparse.ArgumentParser(description="Semantic Digital Publishing Pipeline CLI")
    parser.add_argument("-i", "--input", type=str, help="Path to input DOCX file")
    parser.add_argument("-t", "--title", type=str, help="Book title")
    parser.add_argument("-a", "--author", type=str, help="Book author")
    args = parser.parse_args()

    logger.info("Initializing Semantic Document Processing Database...")
    init_db()
    
    # Selection of document
    if args.input:
        docx_source = Path(args.input)
    else:
        docs_dir = Path("d:/agentic_workflow/docs")
        test_docx_filename = "Marketing Mix-1 -Formatted.docx"
        docx_source = docs_dir / test_docx_filename
        
    if not docx_source.exists():
        logger.error(f"Input Word document not found at: {docx_source}")
        sys.exit(1)
        
    # Copy file to data/input/ for clean processing audit trail
    input_dir = settings.DATA_DIR / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    
    copied_docx_dest = input_dir / docx_source.name
    if docx_source.resolve() != copied_docx_dest.resolve():
        shutil.copy2(docx_source, copied_docx_dest)
        logger.info(f"Copied input document to: {copied_docx_dest.name}")
    else:
        logger.info(f"Input document is already in destination: {copied_docx_dest.name}")
    
    # Run the coordinator pipeline
    db = db_session()
    coordinator = PipelineCoordinator(db)
    
    try:
        output_epub = coordinator.run_pipeline(
            docx_path=copied_docx_dest,
            doc_title=args.title,
            doc_author=args.author
        )
        
        logger.info(f"SUCCESS! EPUB generated successfully at: {output_epub}")
        
        # Copy to root folder as reproduced.epub
        root_epub = Path("d:/agentic_workflow/reproduced.epub")
        shutil.copy2(output_epub, root_epub)
        logger.info(f"Copied EPUB to {root_epub}")
        
    except Exception as e:
        logger.exception(f"Pipeline Execution Failed: {e}")
    finally:
        db_session.remove()

if __name__ == "__main__":
    main()
