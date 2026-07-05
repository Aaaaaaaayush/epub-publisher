import docx
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    doc = docx.Document("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    
    found = False
    for i, p in enumerate(doc.paragraphs):
        if "Hindustan Unilever" in p.text:
            found = True
            print(f"--- Paragraph {i} ---")
            print("Raw text:", repr(p.text))
            print("Runs:")
            for j, r in enumerate(p.runs):
                print(f"  Run {j}: text={repr(r.text)}, bold={r.bold}, italic={r.italic}, style={r.style.name if r.style else None}")
                
    if not found:
        print("Hindustan Unilever not found in docx paragraphs!")

if __name__ == '__main__':
    main()
