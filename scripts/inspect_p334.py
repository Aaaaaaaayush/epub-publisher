import sys
from pathlib import Path
sys.path.append(str(Path.cwd()))

from docx import Document

def main():
    doc = Document("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    p = doc.paragraphs[334]
    print("=== INSPECTING PARAGRAPH 334 XML ===")
    numPr = p._element.xpath('.//*[local-name()="numPr"]')
    print("numPr found:", bool(numPr))
    if numPr:
        print("numPr XML:", p._element.xpath('.//*[local-name()="numPr"]')[0].xml)

if __name__ == "__main__":
    main()
