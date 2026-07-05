import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
latest_doc = db.query(Document).order_by(Document.created_at.desc()).first()

if latest_doc:
    sec = db.query(Section).filter(Section.document_id == latest_doc.id).filter(Section.position == 29).first()
    if sec:
        print("--- RAW LINES ---")
        for line in sec.raw_markdown.split("\n"):
            print(repr(line))
        print("--- VALIDATED LINES ---")
        for line in sec.validated_markdown.split("\n"):
            print(repr(line))
else:
    print("No docs!")

db_session.remove()
