import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def list_sections():
    db = db_session()
    sections = db.query(Section).filter(Section.title.like("%Penetration%")).all()
    print(f"Found {len(sections)} sections:")
    for s in sections:
        print(f"ID: {s.id}, Pos: {s.position}, Level: {s.level}, Title: '{s.title}'")
    db_session.remove()

if __name__ == "__main__":
    list_sections()
