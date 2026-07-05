import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

def main():
    db = db_session()
    sections = db.query(Section).order_by(Section.position).all()
    
    print("=== SEARCHING FOR ASTERISKS IN HTML_CONTENT ===")
    count = 0
    for sec in sections:
        if sec.html_content and ("*" in sec.html_content or "**" in sec.html_content):
            print(f"\nID={sec.id}, Pos={sec.position}, Title='{sec.title}'")
            print("--- HTML CONTENT SAMPLE ---")
            # print lines containing *
            lines = sec.html_content.split("\n")
            for idx, line in enumerate(lines):
                if "*" in line:
                    print(f"Line {idx}: {line.strip()[:100]}")
            count += 1
            if count > 15:
                break
                
    db_session.remove()

if __name__ == "__main__":
    main()
