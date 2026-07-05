import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
sec = db.query(Section).filter(Section.document_id == "f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb").filter(Section.position == 45).first()

with open("d:/agentic_workflow/logs/view_sec_45_output.txt", "w", encoding="utf-8") as f:
    if sec:
        f.write(f"POSITION: {sec.position}\n")
        f.write(f"TITLE: {sec.title}\n")
        f.write(f"RAW MARKDOWN:\n{sec.raw_markdown}\n\n")
        f.write(f"VALIDATED MARKDOWN:\n{sec.validated_markdown}\n\n")
        f.write(f"HTML:\n{sec.html_content}\n")
    else:
        f.write("Section 45 not found!")

print("Successfully written to logs/view_sec_45_output.txt")
db_session.remove()
