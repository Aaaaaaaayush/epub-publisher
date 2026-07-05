import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
doc_id = "f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb"
sections = db.query(Section).filter(Section.document_id == doc_id).order_by(Section.position).all()

for sec in sections:
    if "mcq" in sec.title.lower() or "questions" in sec.title.lower() or "exercise" in sec.title.lower():
        print(f"POSITION: {sec.position}, TITLE: '{sec.title}'")

db_session.remove()
