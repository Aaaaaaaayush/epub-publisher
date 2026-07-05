import json
import pytest
from app.database.session import db_session, init_db
from app.models.document import Document, Section
from app.extraction.analyzer import GlobalDocumentAnalyzer

def test_global_document_analyzer():
    # Initialize DB
    init_db()
    
    with db_session() as db:
        # Create dummy doc
        doc_id = "test-doc-id-123"
        doc = Document(
            id=doc_id,
            title="Test Textbook",
            source_file="dummy.docx",
            author="Test Author"
        )
        db.add(doc)
        
        # Create sections representing Syllabus and Backmatter
        s_syllabus = Section(
            id="sec-1",
            document_id=doc_id,
            parent_id=None,
            section_type="chapter",
            level=1,
            position=1,
            title="Syllabus",
            raw_markdown="""# Syllabus
| Module | Contents |
| --- | --- |
| Module 1 | Introduction to Advertising |
| Module 2 | Ad Agency |
"""
        )
        
        s_accounting = Section(
            id="sec-2",
            document_id=doc_id,
            parent_id=None,
            section_type="chapter",
            level=1,
            position=2,
            title="Format for Accounting:",
            raw_markdown="""# Format for Accounting:
Some table here
"""
        )
        
        db.add(s_syllabus)
        db.add(s_accounting)
        db.commit()
        
        # Run analyzer
        analyzer = GlobalDocumentAnalyzer()
        blueprint_json = analyzer.analyze(db, doc_id)
        
        # Assertions
        assert blueprint_json is not None
        blueprint = json.loads(blueprint_json)
        assert "modules" in blueprint
        assert "non_chapter_pages" in blueprint
        
        # Clean up database
        db.query(Section).filter(Section.document_id == doc_id).delete()
        db.query(Document).filter(Document.id == doc_id).delete()
        db.commit()
