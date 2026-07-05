import sqlite3
import sys

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    conn = sqlite3.connect('d:/agentic_workflow/data/pipeline.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, title FROM documents ORDER BY created_at DESC LIMIT 1")
    doc = c.fetchone()
    if not doc:
        print("No documents found!")
        return
        
    doc_id = doc['id']
    print(f"Checking latest document: {doc['title']} ({doc_id})")
    
    c.execute("""
        SELECT id, position, title, raw_markdown, validated_markdown, html_content 
        FROM sections 
        WHERE document_id = ? 
        ORDER BY position
    """, (doc_id,))
    
    sections = c.fetchall()
    
    total_with_asterisks = 0
    for sec in sections:
        html = sec['html_content'] or ""
        if "*" in html or "**" in html:
            total_with_asterisks += 1
            print(f"\nPos {sec['position']} | {sec['title']}")
            print("--- HTML CONTENT SAMPLE ---")
            lines = html.split('\n')
            for i, line in enumerate(lines):
                if '*' in line:
                    print(f"Line {i}: {line.strip()}")
                    
    print(f"\nTotal sections in this document with literal asterisks in HTML: {total_with_asterisks} / {len(sections)}")
    conn.close()

if __name__ == '__main__':
    main()
