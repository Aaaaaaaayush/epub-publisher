import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def search():
    db = db_session()
    sec = db.query(Section).filter(Section.id == "995bc9c0-e541-40d5-bbf9-1e849ad5d90b").first()
    if not sec:
        print("Section not found!")
        return
        
    print(f"=== DATABASE SEARCH FOR ID: {sec.id} ===")
    print(f"Title: '{sec.title}'")
    print(f"Level: {sec.level}, Position: {sec.position}")
    print(f"Validation Status: {sec.validation_status}")
    print("\n--- RAW MARKDOWN ---")
    print(sec.raw_markdown)
    
    db_session.remove()

if __name__ == "__main__":
    search()
