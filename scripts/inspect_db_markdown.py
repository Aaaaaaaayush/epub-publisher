import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def main():
    db = db_session()
    
    # Find the most recent document
    last_doc = db.query(Document).order_by(Document.created_at.desc()).first()
    if not last_doc:
        print("No documents found!")
        return
        
    print(f"=== MOST RECENT DOCUMENT: {last_doc.id} ===")
    print(f"Title: '{last_doc.title}'\n")
    
    sections = db.query(Section).filter(Section.document_id == last_doc.id).order_by(Section.position).all()
    
    for sec in sections:
        if sec.level > 0 and sec.html_content and ("*" in sec.html_content or "**" in sec.html_content):
            print(f"\nPosition: {sec.position}, Title: '{sec.title}'")
            print("--- RAW MARKDOWN ---")
            print(repr(sec.raw_markdown[:200]))
            print("--- VALIDATED MARKDOWN ---")
            print(repr(sec.validated_markdown[:200]))
            print("--- HTML CONTENT ---")
            print(repr(sec.html_content[:200]))
            
    db_session.remove()

if __name__ == "__main__":
    main()
