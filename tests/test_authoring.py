import pytest
import io
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.database.base import Base
from app.models.document import Document, Section, User, UserPermission
from app.web.author_server import app, get_db, ACTIVE_SESSIONS
from app.docx.generator import DocxGenerator
from app.pdf.generator import PdfGenerator

# Setup temporary SQLite database for testing
TEST_DATABASE_URL = "sqlite:///test_authoring.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    existing_admin = db.query(User).filter_by(username="admin").first()
    if not existing_admin:
        import hashlib
        admin_pwd_hash = hashlib.sha256(b"admin123").hexdigest()
        admin = User(username="admin", password_hash=admin_pwd_hash, is_admin=True)
        db.add(admin)
        db.commit()
    db.close()
    
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    ACTIVE_SESSIONS.clear()  # reset sessions between tests
    if os.path.exists("test_authoring.db"):
        try:
            os.remove("test_authoring.db")
        except Exception:
            pass

@pytest.fixture
def auth_headers():
    # Register a test user
    reg_payload = {"username": "testuser", "password": "testpassword"}
    client.post("/api/auth/register", json=reg_payload)
    
    # Set the test user as admin in the DB so they can create templates in standard tests
    db = TestingSessionLocal()
    user = db.query(User).filter(User.username == "testuser").first()
    if user:
        user.is_admin = True
        db.add(user)
        db.commit()
    db.close()
    
    # Login and get token
    login_resp = client.post("/api/auth/login", json=reg_payload)
    token = login_resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}

def test_user_authentication():
    # 1. Register
    reg_payload = {"username": "newauthor", "password": "securepassword"}
    reg_resp = client.post("/api/auth/register", json=reg_payload)
    assert reg_resp.status_code == 200
    assert reg_resp.json()["status"] == "success"

    # 2. Register duplicate
    dup_resp = client.post("/api/auth/register", json=reg_payload)
    assert dup_resp.status_code == 400

    # 3. Login
    login_resp = client.post("/api/auth/login", json=reg_payload)
    assert login_resp.status_code == 200
    assert "token" in login_resp.json()
    assert login_resp.json()["username"] == "newauthor"

    # 4. Access without token should fail
    fail_resp = client.get("/api/documents")
    assert fail_resp.status_code == 401

def test_create_template_book(auth_headers):
    payload = {
        "title": "Introduction to Finance",
        "author": "Dr. Krati Sharma",
        "modules": 2,
        "chapters": 2,
        "subtopics": 3
    }
    response = client.post("/api/documents/create-template", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    doc_id = data["document_id"]
    
    # Verify DB state
    db = TestingSessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        assert doc is not None
        assert doc.title == "Introduction to Finance"
        
        # Verify document owner is testuser
        owner = db.query(User).filter(User.username == "testuser").first()
        assert doc.owner_id == owner.id
        
        # Sections verify: 8 frontmatter + 2 modules + (2 * 2 chapters) + (2 * 2 * 3 subtopics) + (2 * 2 * 4 exercises) + 2 backmatter
        # Total = 8 + 2 + 4 + 12 + 16 + 2 = 44 sections
        sections_count = db.query(Section).filter(Section.document_id == doc_id).count()
        assert sections_count == 44
    finally:
        db.close()

def test_create_book_from_syllabus(auth_headers):
    syllabus_text = """
    Module 1: Basic Economics
    Chapter 1: Supply and Demand
    - Introduction to supply and demand
    - Price elasticity
    
    Module 2: Advanced Finance
    Chapter 2: Corporate Valuation
    - Discounted Cash Flow
    - Relative Valuation
    """
    payload = {
        "title": "Economics and Finance",
        "author": "Dr. Smith",
        "syllabus_text": syllabus_text,
        "stream": "BCom",
        "year": "SY",
        "university": "Mumbai University"
    }
    response = client.post("/api/documents/create-template", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    doc_id = data["document_id"]
    
    # Verify JSON files are created on disk in blueprints/{doc_id}
    blueprint_dir = f"blueprints/{doc_id}"
    assert os.path.exists(blueprint_dir)
    json_files = [f for f in os.listdir(blueprint_dir) if f.endswith(".json")]
    assert len(json_files) == 2  # one per chapter
    
    # Clean up the test blueprint files
    import shutil
    shutil.rmtree(blueprint_dir, ignore_errors=True)

def test_section_management(auth_headers):
    # 1. Create template book
    payload = {
        "title": "Business Communication",
        "author": "Aayush",
        "modules": 1,
        "chapters": 1,
        "subtopics": 1
    }
    response = client.post("/api/documents/create-template", json=payload, headers=auth_headers)
    doc_id = response.json()["document_id"]
    
    db = TestingSessionLocal()
    try:
        # Find chapter 1
        ch_sec = db.query(Section).filter(Section.document_id == doc_id, Section.title.like("Chapter%")).first()
        assert ch_sec is not None
        
        # 2. Add child section under chapter 1
        add_payload = {
            "parent_id": ch_sec.id,
            "title": "1.2 Case Study of Microsoft",
            "level": 3,
            "section_type": "topic"
        }
        add_resp = client.post(f"/api/documents/{doc_id}/sections", json=add_payload, headers=auth_headers)
        assert add_resp.status_code == 200
        new_sec_id = add_resp.json()["section_id"]
        
        # Verify inserted node
        new_sec = db.query(Section).filter(Section.id == new_sec_id).first()
        assert new_sec is not None
        assert new_sec.parent_id == ch_sec.id
        assert new_sec.level == 3
        
        # 3. Rename section
        rename_resp = client.put(f"/api/sections/{new_sec_id}/rename", json={"title": "1.2 Case Study of Google"}, headers=auth_headers)
        assert rename_resp.status_code == 200
        db.refresh(new_sec)
        assert new_sec.title == "1.2 Case Study of Google"
        
        # 4. Delete section
        del_resp = client.delete(f"/api/sections/{new_sec_id}", headers=auth_headers)
        assert del_resp.status_code == 200
        assert db.query(Section).filter(Section.id == new_sec_id).first() is None
    finally:
        db.close()

def test_docx_and_pdf_compilation(auth_headers):
    payload = {
        "title": "Computational Mathematics",
        "author": "Math Dept",
        "modules": 1,
        "chapters": 1,
        "subtopics": 1
    }
    response = client.post("/api/documents/create-template", json=payload, headers=auth_headers)
    doc_id = response.json()["document_id"]
    
    # Compile PDF and DOCX generators
    db = TestingSessionLocal()
    try:
        # Add answer tags to test answer key generation
        sec = db.query(Section).filter(Section.document_id == doc_id, Section.title.like("%Exercises")).first()
        assert sec is not None
        sec.raw_markdown += "\n\nQ1. Is math fun?\n<!-- ANSWER: Yes -->"
        db.add(sec)
        db.commit()
        
        # Test DocxGenerator
        docx_gen = DocxGenerator(db)
        doc = docx_gen.generate(doc_id)
        assert doc is not None
        # Should have content sections and title page
        assert len(doc.paragraphs) > 5
        
        # Test PdfGenerator
        pdf_gen = PdfGenerator(db)
        stream = io.BytesIO()
        success = pdf_gen.generate(doc_id, stream)
        assert success is True
        assert stream.getvalue() != b""
    finally:
        db.close()

def test_delete_document(auth_headers):
    # 1. Create a template book
    payload = {
        "title": "Document to Delete",
        "author": "Test Author",
        "modules": 1,
        "chapters": 1,
        "subtopics": 1
    }
    response = client.post("/api/documents/create-template", json=payload, headers=auth_headers)
    assert response.status_code == 200
    doc_id = response.json()["document_id"]
    
    # Verify it exists in DB
    db = TestingSessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        assert doc is not None
        sections_count = db.query(Section).filter(Section.document_id == doc_id).count()
        assert sections_count > 0
    finally:
        db.close()
        
    # 2. Call delete API
    del_resp = client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"
    
    # 3. Verify it is gone from DB
    db = TestingSessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        assert doc is None
        sections_count = db.query(Section).filter(Section.document_id == doc_id).count()
        assert sections_count == 0
    finally:
        db.close()

def test_media_upload():
    # Test uploading an image
    image_data = b"fake-image-binary-data"
    response = client.post(
        "/api/media/upload",
        files={"file": ("test_image.png", image_data, "image/png")}
    )
    assert response.status_code == 200
    data = response.json()
    assert "url" in data
    assert "/uploads/" in data["url"]
    
    # Verify file was written to disk
    from app.config.settings import settings
    uploads_dir = settings.DATA_DIR / "uploads"
    filename = data["url"].split("/")[-1]
    uploaded_file_path = uploads_dir / filename
    assert uploaded_file_path.exists()
    assert uploaded_file_path.read_bytes() == image_data
    
    # Clean up
    uploaded_file_path.unlink()

def test_collaborative_book_permissions():
    # 1. Register test users (author1, author2)
    client.post("/api/auth/register", json={"username": "author1", "password": "pwd"})
    client.post("/api/auth/register", json={"username": "author2", "password": "pwd"})
    
    # Login admin (admin is created automatically on startup)
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['token']}"}
    
    # Get user records to know user IDs
    db = TestingSessionLocal()
    u1 = db.query(User).filter(User.username == "author1").first()
    u2 = db.query(User).filter(User.username == "author2").first()
    db.close()
    
    # 2. Admin creates a template book
    payload = {
        "title": "Collab Biology",
        "author": "Bio Dept",
        "modules": 2,
        "chapters": 1,
        "subtopics": 1
    }
    response = client.post("/api/documents/create-template", json=payload, headers=admin_headers)
    assert response.status_code == 200
    doc_id = response.json()["document_id"]
    
    # 3. Toggle collaborative mode ON
    collab_resp = client.put(f"/api/documents/{doc_id}/toggle-collaborative", json={"is_collaborative": True}, headers=admin_headers)
    assert collab_resp.status_code == 200
    
    # 4. Assign Module 1 to author1, Module 2 to author2
    db = TestingSessionLocal()
    modules = db.query(Section).filter(
        Section.document_id == doc_id,
        Section.title.like("Module%")
    ).order_by(Section.position).all()
    assert len(modules) >= 2
    mod1_id = modules[0].id
    mod2_id = modules[1].id
    db.close()
    
    # Assign mod1 to u1
    resp1 = client.post("/api/admin/permissions", json={"document_id": doc_id, "section_id": mod1_id, "user_ids": [u1.id]}, headers=admin_headers)
    assert resp1.status_code == 200
    
    # Assign mod2 to u2
    resp2 = client.post("/api/admin/permissions", json={"document_id": doc_id, "section_id": mod2_id, "user_ids": [u2.id]}, headers=admin_headers)
    assert resp2.status_code == 200
    
    # Grant book access to author1 and author2, but NOT author3
    access_resp = client.post(f"/api/admin/books/{doc_id}/access", json={"user_ids": [u1.id, u2.id]}, headers=admin_headers)
    assert access_resp.status_code == 200
    
    # Register and log in as author3 (dummy user with no book access)
    client.post("/api/auth/register", json={"username": "author3", "password": "pwd"})
    a3_login = client.post("/api/auth/login", json={"username": "author3", "password": "pwd"})
    a3_headers = {"Authorization": f"Bearer {a3_login.json()['token']}"}
    
    # Verify author3 CANNOT read sections list of the document (should return 403)
    sec_list_a3 = client.get(f"/api/documents/{doc_id}/sections", headers=a3_headers)
    assert sec_list_a3.status_code == 403
    
    # 5. Log in as author1
    a1_login = client.post("/api/auth/login", json={"username": "author1", "password": "pwd"})
    a1_headers = {"Authorization": f"Bearer {a1_login.json()['token']}"}
    
    # Verify author1 can read sections list of the document
    sec_list_resp = client.get(f"/api/documents/{doc_id}/sections", headers=a1_headers)
    assert sec_list_resp.status_code == 200
    sections = sec_list_resp.json()
    
    # Verify edit capabilities:
    # Find Module 1, Module 2, and Copyright section
    mod1_node = next(s for s in sections if s["id"] == mod1_id)
    mod2_node = next(s for s in sections if s["id"] == mod2_id)
    copyright_node = next(s for s in sections if s["title"] == "Copyright")
    
    assert mod1_node["editable"] is True
    assert mod2_node["editable"] is False
    # Introductory pages (Copyright) are now editable by any author with access!
    assert copyright_node["editable"] is True
    assert copyright_node["readable"] is True
    
    # Try updating Module 1 (should succeed)
    up_m1 = client.put(f"/api/sections/{mod1_id}", json={"validated_markdown": "# Updated Module 1"}, headers=a1_headers)
    assert up_m1.status_code == 200
    
    # Try updating Module 2 (should fail 403, since it's currently assigned to author2)
    up_m2 = client.put(f"/api/sections/{mod2_id}", json={"validated_markdown": "# Hacked Module 2"}, headers=a1_headers)
    assert up_m2.status_code == 403
    
    # Try updating Copyright (should succeed now!)
    up_copy = client.put(f"/api/sections/{copyright_node['id']}", json={"validated_markdown": "# New Copyright"}, headers=a1_headers)
    assert up_copy.status_code == 200

    # 6. Admin assigns Module 2 to "All Authors" (-1)
    resp_all = client.post("/api/admin/permissions", json={"document_id": doc_id, "section_id": mod2_id, "user_ids": [-1]}, headers=admin_headers)
    assert resp_all.status_code == 200

    # Verify author1 can now edit Module 2!
    sec_list_resp2 = client.get(f"/api/documents/{doc_id}/sections", headers=a1_headers)
    sections2 = sec_list_resp2.json()
    mod2_node_updated = next(s for s in sections2 if s["id"] == mod2_id)
    assert mod2_node_updated["editable"] is True

    up_m2_all = client.put(f"/api/sections/{mod2_id}", json={"validated_markdown": "# Updated Module 2 by author1"}, headers=a1_headers)
    assert up_m2_all.status_code == 200

    # 7. Author1 adds a level-1 page (e.g. "About the Author 2")
    add_l1 = client.post(f"/api/documents/{doc_id}/sections", json={
        "parent_id": None,
        "title": "About the Author 2",
        "level": 1,
        "section_type": "book"
    }, headers=a1_headers)
    assert add_l1.status_code == 200

def test_create_template_with_uploaded_jsons(auth_headers):
    # Prepare dummy uploaded JSON blueprints payload
    uploaded_json = {
        "chapter_id": "M1C1",
        "title": "Introduction to HRM",
        "sections": [
            {
                "title": "Overview of Human Resources",
                "word_budget": 1200,
                "learning_outcomes": ["Outcomes 1"],
                "must_cover": ["Scope of HRM"],
                "keywords": ["HRM", "Scope"]
            },
            {
                "title": "Strategic Importance of HR",
                "word_budget": 800,
                "learning_outcomes": ["Outcomes 2"],
                "must_cover": ["Strategic Alignment"],
                "keywords": ["Strategy"]
            }
        ]
    }
    
    payload = {
        "title": "Manual Blueprint HRM Book",
        "author": "Test Author",
        "uploaded_jsons": [uploaded_json]
    }
    
    response = client.post("/api/documents/create-template", json=payload, headers=auth_headers)
    assert response.status_code == 200
    doc_id = response.json()["document_id"]
    
    # Query all sections of this document to verify correct structure was created
    sections_resp = client.get(f"/api/documents/{doc_id}/sections", headers=auth_headers)
    assert sections_resp.status_code == 200
    sections = sections_resp.json()
    
    # Verify we have "Module 1", "Chapter 1: Introduction to HRM" and subtopic sections
    titles = [s["title"] for s in sections]
    assert "Module 1" in titles
    assert "Chapter 1: Introduction to HRM" in titles
    assert "1.1 Overview of Human Resources" in titles
    assert "1.2 Strategic Importance of HR" in titles
    
    # Verify exercise sections were also generated automatically
    assert "Chapter 1 MCQ" in titles
    assert "Chapter 1 True or False" in titles
    assert "Chapter 1 Fill in the Blanks" in titles
    assert "Chapter 1 Match the Following" in titles


def test_math_to_mathml_conversion():
    from app.epub.generator import MarkdownToHtmlConverter
    converter = MarkdownToHtmlConverter()
    
    # 1. Test display math
    md_display = "$$x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$$"
    html_display = converter.convert(md_display, convert_math=True)
    assert '<math display="inline" xmlns="http://www.w3.org/1998/Math/MathML" displaystyle="true">' in html_display
    assert '<mfrac>' in html_display or '<math' in html_display
    
    # 2. Test inline math
    md_inline = "This is $E=mc^2$ formula."
    html_inline = converter.convert(md_inline, convert_math=True)
    assert '<math' in html_inline
    assert 'E' in html_inline
    
    # 3. Test convert_math=False preserves raw math
    html_pres = converter.convert(md_display, convert_math=False)
    assert '$$x =' in html_pres
    assert '<math' not in html_pres


def test_query_token_authentication():
    # Setup test DB user session
    client.post("/api/auth/register", json={"username": "downloaduser", "password": "pwd"})
    login_resp = client.post("/api/auth/login", json={"username": "downloaduser", "password": "pwd"})
    token = login_resp.json()["token"]
    
    # 1. Accessing documents list with Query Parameter token instead of Header
    response = client.get(f"/api/documents?token={token}")
    assert response.status_code == 200
