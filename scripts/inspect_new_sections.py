import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
latest_doc = db.query(Document).order_by(Document.created_at.desc()).first()

if latest_doc:
    print(f"=== LATEST DOC ID: {latest_doc.id} ({latest_doc.title}) ===")
    
    # 1. Inspect Section 29 (Importance of Pricing)
    sec29 = db.query(Section).filter(Section.document_id == latest_doc.id).filter(Section.position == 29).first()
    if sec29:
        print(f"\n--- SECTION {sec29.position}: {sec29.title} ---")
        print("HTML content:")
        print(sec29.html_content)
    else:
        print("Section 29 not found!")

    # 2. Inspect Section 45 (MCQ)
    sec45 = db.query(Section).filter(Section.document_id == latest_doc.id).filter(Section.position == 45).first()
    if sec45:
        print(f"\n--- SECTION {sec45.position}: {sec45.title} ---")
        print("HTML content (first 1200 chars):")
        if sec45.html_content:
            print(sec45.html_content[:1200])
        else:
            print("None")
    else:
        print("Section 45 not found!")

else:
    print("No documents found!")

db_session.remove()
