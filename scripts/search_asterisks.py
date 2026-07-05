import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
doc_id = "f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb"
sections = db.query(Section).filter(Section.document_id == doc_id).order_by(Section.position).all()

print("Searching for asterisks in validated markdown:")
for sec in sections:
    if sec.validated_markdown:
        lines = sec.validated_markdown.split("\n")
        for idx, line in enumerate(lines):
            if "*" in line:
                # print the line if it has isolated or weird asterisks
                if " ** " in line or " * " in line or "** **" in line or line.strip() == "*" or line.strip() == "**":
                    print(f"Sec {sec.position} Line {idx}: {repr(line)}")
                elif line.count("*") % 2 != 0:
                    print(f"Sec {sec.position} Line {idx} (UNBALANCED): {repr(line)}")

db_session.remove()
