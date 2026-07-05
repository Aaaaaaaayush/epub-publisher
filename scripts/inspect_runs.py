from docx import Document
from pathlib import Path

def main():
    doc_path = Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    doc = Document(str(doc_path))
    
    print("=== INSPECTING RUN STYLES FOR BOLD/ITALIC ===")
    count = 0
    for idx, p in enumerate(doc.paragraphs):
        # Let's inspect some paragraphs that have formatting or contain specific words
        text = p.text.strip()
        if any(w in text for w in ["Product branding", "Types of Branding", "Penetration Pricing", "Netflix"]):
            print(f"\n--- Paragraph {idx} (Style: '{p.style.name}') ---")
            print(f"Text: '{text}'")
            for r_idx, run in enumerate(p.runs):
                style_name = run.style.name if run.style else "None"
                print(f"  Run {r_idx}: text='{run.text}', bold={run.bold}, italic={run.italic}, style='{style_name}'")
            count += 1
            if count > 20:
                break

if __name__ == "__main__":
    main()
