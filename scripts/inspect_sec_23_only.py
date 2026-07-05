import sqlite3
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    conn = sqlite3.connect('d:/agentic_workflow/data/pipeline.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id FROM documents ORDER BY created_at DESC LIMIT 1")
    doc_id = c.fetchone()['id']
    
    pos = 23
    c.execute("""
        SELECT title, raw_markdown, formatted_markdown, validated_markdown, html_content 
        FROM sections 
        WHERE document_id = ? AND position = ?
    """, (doc_id, pos))
    sec = c.fetchone()
    if sec:
        print(f"\n==================== POSITION {pos}: {sec['title']} ====================")
        print("--- RAW MARKDOWN ---")
        print(repr(sec['raw_markdown']))
        print("--- FORMATTED MARKDOWN ---")
        print(repr(sec['formatted_markdown']))
        print("--- VALIDATED MARKDOWN ---")
        print(repr(sec['validated_markdown']))
        print("--- HTML CONTENT ---")
        print(repr(sec['html_content']))
        
    conn.close()

if __name__ == '__main__':
    main()
