import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.models.document import Document, Section
from app.extraction.splitter import MarkdownSplitter
from app.epub.generator import MarkdownToHtmlConverter, EpubGenerator
from app.agents.validation_agent import ValidationAgent

# Test configuration
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    """Sets up an in-memory SQLite database and yields a session."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

def test_document_creation(db_session):
    """Verifies that Document and Section models can be inserted and retrieved."""
    doc = Document(id="doc-123", title="Test Book", source_file="test.docx")
    db_session.add(doc)
    db_session.commit()
    
    retrieved_doc = db_session.query(Document).filter_by(id="doc-123").first()
    assert retrieved_doc is not None
    assert retrieved_doc.title == "Test Book"

def test_markdown_splitter(db_session):
    """Verifies that the MarkdownSplitter correctly builds a parent-child hierarchy tree."""
    # Insert document
    doc = Document(id="doc-split", title="Hierarchy Book", source_file="test.docx")
    db_session.add(doc)
    db_session.commit()
    
    splitter = MarkdownSplitter(db_session)
    markdown_content = """# Chapter 1: Foundations
Intro text under chapter 1.

## Topic 1.1: Core Concepts
Topic body text.

### Subtopic 1.1.1: Deep Details
Subtopic body text.

# Chapter 2: Summary
Final chapter text.
"""
    splitter.split_and_store("doc-split", markdown_content)
    
    # Query stored sections
    sections = db_session.query(Section).filter_by(document_id="doc-split").order_by(Section.level, Section.position).all()
    
    # Level 0 (Book), Level 1 (Chapters), Level 2 (Topics), Level 3 (Subtopics)
    levels = [s.level for s in sections]
    assert 0 in levels  # Book
    assert 1 in levels  # Chapters
    assert 2 in levels  # Topics
    assert 3 in levels  # Subtopics
    
    # Check parent-child relation
    subtopic = db_session.query(Section).filter_by(section_type="subtopic").first()
    assert subtopic is not None
    assert subtopic.parent is not None
    assert subtopic.parent.section_type == "topic"
    assert subtopic.parent.parent is not None
    assert subtopic.parent.parent.section_type == "chapter"

def test_heading_jumps_detector():
    """Verifies that heading jumps (e.g. H1 to H3) are flagged correctly by the ValidationAgent."""
    agent = ValidationAgent()
    
    # Clean headings
    valid_md = "# Title 1\n## Topic 1.1\n### Subtopic 1.1.1"
    assert len(agent.check_heading_jumps(valid_md)) == 0
    
    # Jumps heading
    invalid_md = "# Title 1\n### Subtopic 1.1.1"
    errors = agent.check_heading_jumps(invalid_md)
    assert len(errors) == 1
    assert "Heading jump detected: H1 followed immediately by H3" in errors[0]

def test_markdown_to_html_converter():
    """Verifies that MarkdownToHtmlConverter outputs clean semantic HTML elements."""
    converter = MarkdownToHtmlConverter()
    md_text = """### Subsection Header
* **Bold Item**
* *Italic Item*

| Header 1 | Header 2 |
| --- | --- |
| Cell A | Cell B |
"""
    html = converter.convert(md_text)
    assert "<h3>Subsection Header</h3>" in html
    assert "<strong>Bold Item</strong>" in html
    assert "<em>Italic Item</em>" in html
    assert "<table>" in html
    assert "<th>Header 1</th>" in html
