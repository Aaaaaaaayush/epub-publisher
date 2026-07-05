import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
latest_doc = db.query(Document).order_by(Document.created_at.desc()).first()

if latest_doc:
    sections = db.query(Section).filter(Section.document_id == latest_doc.id).order_by(Section.position).all()
    for sec in sections:
        if "importance of pricing" in sec.title.lower() or "mcq" in sec.title.lower() or "pricing policies" in sec.title.lower():
            print(f"Pos {sec.position}: Title='{sec.title}'")
            # print first 300 chars of raw and html content
            print("  --- HTML ---")
            print(sec.html_content[:500] if sec.html_content else "None")
db_session.remove()
