import sys
from pathlib import Path

# Add project root to python path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document
from app.epub.generator import EpubGenerator

def main():
    db = db_session()
    # Find the most recent document ingested
    last_doc = db.query(Document).order_by(Document.created_at.desc()).first()
    if not last_doc:
        print("No documents found in SQLite database.")
        sys.exit(1)
        
    print(f"Recompiling EPUB for last document: ID={last_doc.id}, Title='{last_doc.title}'")
    
    generator = EpubGenerator(db)
    output_path = Path("d:/agentic_workflow/data/epub/marketing_mix_principles_and_elements.epub")
    
    try:
        generator.generate_epub(last_doc.id, output_path)
        print("SUCCESS: EPUB compiled successfully!")
        # Copy to root folder as reproduced.epub
        root_epub = Path("d:/agentic_workflow/reproduced.epub")
        import shutil
        shutil.copy2(output_path, root_epub)
        print(f"Copied EPUB to {root_epub}")
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db_session.remove()

if __name__ == "__main__":
    main()
