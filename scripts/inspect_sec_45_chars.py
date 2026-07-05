import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
sec = db.query(Section).filter(Section.document_id == "f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb").filter(Section.position == 45).first()

if sec:
    raw_lines = sec.raw_markdown.split("\n")
    for idx, line in enumerate(raw_lines):
        if "Answer" in line:
            print(f"Line {idx}: {repr(line)}")
else:
    print("Section 45 not found!")

db_session.remove()
