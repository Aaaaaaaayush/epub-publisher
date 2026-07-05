import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database.session import db_session
from app.models.document import Document, Section

db = db_session()
docs = db.query(Document).all()
print(f"Total documents in DB: {len(docs)}")
for doc in docs:
    print(f"Doc: ID={doc.id}, Title='{doc.title}', File='{doc.source_file}', CreatedAt={doc.created_at}")

db_session.remove()
