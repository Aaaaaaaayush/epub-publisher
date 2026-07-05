import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.extraction.extractor import DocxExtractor

def test():
    docx_path = Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    ext = DocxExtractor(docx_path)
    md = ext.extract_to_markdown()
    
    print("=== DIRECT EXTRACTOR OUTPUT ===")
    print(md[:600])

if __name__ == "__main__":
    test()
