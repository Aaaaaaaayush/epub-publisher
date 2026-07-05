from docx import Document
from pathlib import Path

def main():
    doc_path = Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    doc = Document(str(doc_path))
    
    print("=== INSPECTING DIRECT CHANNELS PARAGRAPH ===")
    for idx, p in enumerate(doc.paragraphs):
        text = p.text.strip()
        if "Direct channels" in text or "Key Elements of Place" in text:
            print(f"\n--- Paragraph {idx} (Style: '{p.style.name}') ---")
            print(f"Text: '{text}'")
            for r_idx, run in enumerate(p.runs):
                style_name = run.style.name if run.style else "None"
                print(f"  Run {r_idx}: text='{run.text}', bold={run.bold}, italic={run.italic}, style='{style_name}'")

if __name__ == "__main__":
    main()
