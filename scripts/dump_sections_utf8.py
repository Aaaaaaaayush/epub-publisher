import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
doc_id = "f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb"
sections = db.query(Section).filter(Section.document_id == doc_id).order_by(Section.position).all()

output_path = Path("d:/agentic_workflow/logs/sections_dump.txt")
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, "w", encoding="utf-8") as f:
    f.write(f"=== SECTIONS DUMP FOR {doc_id} ===\n")
    for sec in sections:
        f.write(f"\n=========================================\n")
        f.write(f"POSITION: {sec.position}\n")
        f.write(f"LEVEL: {sec.level}\n")
        f.write(f"TITLE: {sec.title}\n")
        f.write(f"SECTION TYPE: {sec.section_type}\n")
        f.write(f"VALIDATION STATUS: {sec.validation_status}\n")
        f.write(f"--- RAW MARKDOWN ---\n")
        f.write(str(sec.raw_markdown) + "\n")
        f.write(f"--- VALIDATED MARKDOWN ---\n")
        f.write(str(sec.validated_markdown) + "\n")
        f.write(f"--- HTML CONTENT ---\n")
        f.write(str(sec.html_content) + "\n")

print(f"Dumped {len(sections)} sections to {output_path}")
db_session.remove()
