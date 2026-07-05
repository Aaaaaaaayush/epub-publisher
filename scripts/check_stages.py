import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def check():
    db = db_session()
    # Fetch first non-book section
    sec = db.query(Section).filter(Section.level == 1).order_by(Section.position).first()
    if not sec:
        print("No section found.")
        return
        
    print(f"=== Section ID: {sec.id} ===")
    print(f"Title: '{sec.title}'")
    print(f"Level: {sec.level}, Pos: {sec.position}")
    print("\n--- RAW MARKDOWN ---")
    print(repr(sec.raw_markdown)[:500])
    print("\n--- FORMATTED MARKDOWN ---")
    print(repr(sec.formatted_markdown)[:500])
    print("\n--- VALIDATED MARKDOWN ---")
    print(repr(sec.validated_markdown)[:500])
    print("\n--- HTML CONTENT ---")
    print(repr(sec.html_content)[:500])
    
    db_session.remove()

if __name__ == "__main__":
    check()
