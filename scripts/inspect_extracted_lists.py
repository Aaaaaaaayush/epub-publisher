import glob
from pathlib import Path
import re

def main():
    extracted_files = glob.glob("d:/agentic_workflow/data/extracted/*_extracted.md")
    if not extracted_files:
        print("No extracted markdown files found!")
        return
        
    # Get the latest extracted file by modification time
    latest_file = max(extracted_files, key=lambda f: Path(f).stat().st_mtime)
    print(f"Inspecting latest extracted file: {latest_file}\n")
    
    with open(latest_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    lines = content.split("\n")
    
    print("=== INSPECTING PENETRATION PRICING SEQUENTIAL NUMBERS ===")
    found = False
    for idx, line in enumerate(lines):
        if "Encourage Trial and Adoption" in line:
            found = True
            print(f"Line {idx}: {line}")
            for k in range(idx + 1, min(idx + 15, len(lines))):
                print(f"Line {k}: {lines[k]}")
            break
            
    print("\n=== INSPECTING MCQ QUESTIONS AND OPTIONS ===")
    found = False
    for idx, line in enumerate(lines):
        if "Multiple Choice Question" in line:
            found = True
            print(f"Line {idx}: {line}")
            for k in range(idx + 1, min(idx + 35, len(lines))):
                print(f"Line {k}: {lines[k]}")
            break

    print("\n=== INSPECTING CASE STUDIES SEQUENTIAL NUMBERS ===")
    found = False
    for idx, line in enumerate(lines):
        if "Case studies" in line:
            found = True
            print(f"Line {idx}: {line}")
            for k in range(idx + 1, min(idx + 35, len(lines))):
                print(f"Line {k}: {lines[k]}")
            break

if __name__ == "__main__":
    main()
