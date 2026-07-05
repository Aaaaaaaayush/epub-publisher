import sys
from pathlib import Path
sys.path.append("d:/agentic_workflow")

from app.extraction.extractor import DocxExtractor

def main():
    extractor = DocxExtractor(Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx"))
    raw_markdown = extractor.extract_to_markdown()
    
    # split and find "Types of Industrial Goods"
    lines = raw_markdown.split('\n')
    found = False
    for idx, line in enumerate(lines):
        if "3.2.2" in line:
            found = True
            print(f"Line {idx+1}: {repr(line)}")
            print("--- SURROUNDING ---")
            for j in range(max(0, idx - 2), min(len(lines), idx + 25)):
                print(f"  {j+1}: {repr(lines[j])}")
            break
            
    if not found:
        print("3.2.2 not found!")

if __name__ == '__main__':
    main()
