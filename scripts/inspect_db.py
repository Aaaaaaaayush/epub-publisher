import sys
from pathlib import Path

# Set project root path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def inspect():
    db = db_session()
    sections = db.query(Section).order_by(Section.position).all()
    print(f"Total sections in DB: {len(sections)}")
    empty_html_count = 0
    empty_raw_count = 0
    
    for sec in sections:
        html_len = len(sec.html_content) if sec.html_content else 0
        raw_len = len(sec.raw_markdown) if sec.raw_markdown else 0
        val_len = len(sec.validated_markdown) if sec.validated_markdown else 0
        
        if sec.level > 0 and not sec.html_content:
            empty_html_count += 1
            print(f"EMPTY HTML: ID={sec.id}, Pos={sec.position}, Level={sec.level}, Type={sec.section_type}, Title='{sec.title}'")
            print(f"  raw_len={raw_len}, val_len={val_len}, val_status={sec.validation_status}")
        
        if sec.level > 0 and not sec.raw_markdown:
            empty_raw_count += 1
            print(f"EMPTY RAW: ID={sec.id}, Pos={sec.position}, Level={sec.level}, Title='{sec.title}'")
            
    print(f"Sections with empty HTML: {empty_html_count}")
    print(f"Sections with empty RAW: {empty_raw_count}")
    db_session.remove()

if __name__ == "__main__":
    inspect()
