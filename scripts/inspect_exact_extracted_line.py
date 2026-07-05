import sys
from pathlib import Path

extracted_file = Path("d:/agentic_workflow/data/extracted/f171d26c-6ad8-4f13-8a0a-bcd2f6253ecb_extracted.md")
if extracted_file.exists():
    with open(extracted_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # find lines containing "main objective"
    for idx, line in enumerate(lines):
        if "The main objective of pricing is to" in line:
            print(f"Found at line {idx}!")
            for k in range(max(0, idx-5), min(len(lines), idx+15)):
                print(f"{k:4d}: {repr(lines[k])}")
            break
else:
    print("Extracted file not found!")
