import sys
from pathlib import Path

extracted_file = Path("d:/agentic_workflow/data/extracted/f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb_extracted.md")
if extracted_file.exists():
    with open(extracted_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # print around the first occurrence of "main objective"
    idx = content.find("The main objective of pricing is to")
    if idx != -1:
        print("=== FOUND IN EXTRACTED FILE ===")
        print(content[idx-50:idx+200])
    else:
        print("Not found in extracted file!")
else:
    print("Extracted file not found!")
