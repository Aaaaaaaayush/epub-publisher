import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def main():
    db = db_session()
    last_doc = db.query(Document).order_by(Document.created_at.desc()).first()
    if not last_doc:
        print("No documents found!")
        return
        
    print(f"=== INSPECTING LATEST DOCUMENT: {last_doc.id} ({last_doc.title}) ===")
    
    sections = db.query(Section).filter(Section.document_id == last_doc.id).order_by(Section.position).all()
    
    count = 0
    for sec in sections:
        if sec.html_content and ("*" in sec.html_content or "**" in sec.html_content):
            print(f"\nPos {sec.position}: Title='{sec.title}'")
            # print all lines in html_content that contain *
            lines = sec.html_content.split("\n")
            for idx, line in enumerate(lines):
                if "*" in line:
                    print(f"  Line {idx}: {line.strip()}")
            count += 1
            
    print(f"\nTotal sections in latest document with literal asterisks in HTML: {count}")
    db_session.remove()

if __name__ == "__main__":
    main()
