import sys
from pathlib import Path
from docx import Document

docx_path = Path("d:/agentic_workflow/data/input/Marketing Mix-1 -Formatted.docx")
doc = Document(str(docx_path))

for idx, p in enumerate(doc.paragraphs):
    if "Main Elements of the Promotion Mix" in p.text:
        print(f"Found paragraph {idx}: {repr(p.text)}")
        break
db_session = None
