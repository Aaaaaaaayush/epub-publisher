import sqlite3
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    conn = sqlite3.connect('d:/agentic_workflow/data/pipeline.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id FROM documents ORDER BY created_at DESC LIMIT 1")
    doc_id = c.fetchone()['id']
    
    c.execute("""
        SELECT raw_markdown 
        FROM sections 
        WHERE document_id = ? AND level = 0
    """, (doc_id,))
    sec = c.fetchone()
    if sec:
        md = sec['raw_markdown']
        # Find where Hindustan is
        lines = md.split('\n')
        for idx, line in enumerate(lines):
            if "Hindustan Unilever Limited" in line:
                print(f"Line {idx+1}: {repr(line)}")
                print("--- SURROUNDING ---")
                for j in range(max(0, idx - 2), min(len(lines), idx + 8)):
                    print(f"  {j+1}: {repr(lines[j])}")
                    
    conn.close()

if __name__ == '__main__':
    main()
