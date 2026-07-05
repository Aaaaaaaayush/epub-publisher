import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
latest_doc = db.query(Document).order_by(Document.created_at.desc()).first()
if latest_doc:
    print(f"=== LATEST DOC: {latest_doc.id} ({latest_doc.title}) ===")
    sec = db.query(Section).filter(Section.document_id == latest_doc.id).filter(Section.position == 29).first()
    if sec:
        print(f"=== SECTION 29: {sec.title} ===")
        print("--- RAW MARKDOWN ---")
        print(repr(sec.raw_markdown))
        print("--- VALIDATED MARKDOWN ---")
        print(repr(sec.validated_markdown))
        print("--- HTML CONTENT ---")
        print(repr(sec.html_content))
    else:
        print("Section 29 not found!")
else:
    print("No documents found!")

db_session.remove()
