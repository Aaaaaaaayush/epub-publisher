from pathlib import Path

def main():
    log_path = Path("d:/agentic_workflow/logs/pipeline.log")
    if not log_path.exists():
        print("pipeline.log not found!")
        return
        
    print(f"File size: {log_path.stat().st_size} bytes")
    
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    print(f"Total lines: {len(lines)}")
    
    print("\n--- FIRST 30 LINES ---")
    for line in lines[:30]:
        print(line.strip())
        
    print("\n--- ERROR OR API KEY LINES ---")
    count = 0
    for idx, line in enumerate(lines):
        if "API" in line or "key" in line or "OpenAI" in line or "base_url" in line:
            print(f"Line {idx}: {line.strip()}")
            count += 1
            if count > 30:
                break

if __name__ == "__main__":
    main()
