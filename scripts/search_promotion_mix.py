import sys
from pathlib import Path

extracted_file = Path("d:/agentic_workflow/data/extracted/f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb_extracted.md")
if extracted_file.exists():
    with open(extracted_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    idx = content.find("Main Elements of the Promotion Mix")
    if idx != -1:
        print("=== FOUND IN EXTRACTED FILE ===")
        print(content[idx-50:idx+350])
    else:
        print("Not found in extracted file!")
else:
    print("Extracted file not found!")
