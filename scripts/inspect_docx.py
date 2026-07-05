import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from docx import Document

def inspect_duplicated_headings():
    doc_path = Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    doc = Document(str(doc_path))
    
    print("=== INSPECTING HEADING DUPLICATIONS IN DOCX ===")
    
    for i, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if "Pricing" in text or "Pricing strategies" in text or "Multiple Choice" in text or "Case studies" in text:
            print(f"\n--- Paragraph {i} (Style: '{p.style.name}') ---")
            print(f"p.text: '{p.text}'")
            print(f"Runs count: {len(p.runs)}")
            for r_idx, run in enumerate(p.runs):
                print(f"  Run {r_idx}: text='{run.text}', bold={run.bold}, italic={run.italic}")

if __name__ == "__main__":
    inspect_duplicated_headings()
