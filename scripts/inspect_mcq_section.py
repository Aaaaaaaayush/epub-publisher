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
        SELECT id, position, title, raw_markdown, validated_markdown, html_content 
        FROM sections 
        WHERE document_id = ? AND title LIKE '%Multiple Choice%'
        ORDER BY position
    """, (doc_id,))
    
    sec = c.fetchone()
    if sec:
        print(f"=== Found MCQ Section: Pos {sec['position']} | {sec['title']} ===")
        print("--- RAW MARKDOWN ---")
        print(repr(sec['raw_markdown'][:2000]))
        print("\n--- VALIDATED MARKDOWN ---")
        print(repr(sec['validated_markdown'][:2000]))
        print("\n--- HTML CONTENT ---")
        print(repr(sec['html_content'][:2000]))
    else:
        print("MCQ Section not found!")
        
    conn.close()

if __name__ == '__main__':
    main()
