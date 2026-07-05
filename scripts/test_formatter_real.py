import sys
from pathlib import Path
sys.path.append("d:/agentic_workflow")

from app.extraction.extractor import DocxExtractor
from app.formatting.formatter import clean_markdown_formatting

def main():
    extractor = DocxExtractor(Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx"))
    raw_markdown = extractor.extract_to_markdown()
    
    # Run the real formatting function
    cleaned = clean_markdown_formatting(raw_markdown)
    
    # Print where Hindustan is in the formatted markdown
    lines = cleaned.split('\n')
    found = False
    for idx, line in enumerate(lines):
        if "Hindustan" in line:
            found = True
            print(f"Line {idx+1}: {repr(line)}")
            print("--- SURROUNDING ---")
            for j in range(max(0, idx - 2), min(len(lines), idx + 8)):
                print(f"  {j+1}: {repr(lines[j])}")
                
    if not found:
        print("Hindustan not found in formatted markdown!")

if __name__ == '__main__':
    main()
