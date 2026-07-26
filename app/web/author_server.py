import os
import re
import uuid
import shutil
import logging
import io
from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib
import sys

# Python 3.8 compatibility patch for ReportLab's FIPS hashlib calls
if sys.version_info < (3, 9):
    def patch_hash_func(func):
        def patched(*args, **kwargs):
            kwargs.pop('usedforsecurity', None)
            return func(*args, **kwargs)
        return patched
    hashlib.md5 = patch_hash_func(hashlib.md5)
    hashlib.sha1 = patch_hash_func(hashlib.sha1)
    hashlib.sha256 = patch_hash_func(hashlib.sha256)
    original_new = hashlib.new
    def patched_new(name, *args, **kwargs):
        kwargs.pop('usedforsecurity', None)
        return original_new(name, *args, **kwargs)
    hashlib.new = patched_new

from fastapi import FastAPI, Form, BackgroundTasks, HTTPException, Depends, UploadFile, File, Header, Query
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session

# Force separate database for the authoring CMS
from app.config.settings import settings
settings.DATABASE_URL = f"sqlite:///{settings.DATA_DIR}/author_pipeline.db"

from app.database.session import db_session, init_db
from app.models.document import Document, Section, User, UserPermission, BookAccess
from app.epub.generator import EpubGenerator
from app.docx.generator import DocxGenerator
from app.pdf.generator import PdfGenerator
from app.utils.logger import logger

app = FastAPI(title="Interactive Authoring CMS & Multi-Format Publisher")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded media
uploads_dir = settings.DATA_DIR / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

ACTIVE_JOBS: Dict[str, Dict] = {}


class CreateTemplatePayload(BaseModel):
    title: str
    author: str
    modules: Optional[int] = 3
    chapters: Optional[int] = 2
    subtopics: Optional[int] = 4
    syllabus_text: Optional[str] = None
    stream: Optional[str] = "BCom"
    year: Optional[str] = "SY"
    university: Optional[str] = "Mumbai University"
    api_key: Optional[str] = None
    uploaded_jsons: Optional[List[Any]] = None

class AddSectionPayload(BaseModel):
    parent_id: Optional[str] = None
    title: str
    level: int
    section_type: str

class RenameSectionPayload(BaseModel):
    title: str

class SectionUpdate(BaseModel):
    validated_markdown: str

def get_db():
    db = db_session()
    try:
        yield db
    finally:
        db_session.remove()

ACTIVE_SESSIONS: Dict[str, str] = {} # token -> username

class LoginPayload(BaseModel):
    username: str
    password: str

class RegisterPayload(BaseModel):
    username: str
    password: str

def get_current_user(db: Session = Depends(get_db), authorization: Optional[str] = Header(None), token: Optional[str] = Query(None)):
    t = None
    if authorization:
        t = authorization.replace("Bearer ", "").strip()
    elif token:
        t = token.strip()
        
    if not t:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    username = ACTIVE_SESSIONS.get(t)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

@app.post("/api/auth/register")
def register_user(payload: RegisterPayload, db: Session = Depends(get_db)):
    username = payload.username.strip()
    password = payload.password.strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")
    
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = User(username=username, password_hash=password_hash)
    db.add(user)
    db.commit()
    return {"status": "success", "message": "User registered successfully"}

@app.post("/api/auth/login")
def login_user(payload: LoginPayload, db: Session = Depends(get_db)):
    username = payload.username.strip()
    password = payload.password.strip()
    
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid username or password")
        
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user.password_hash != password_hash:
        raise HTTPException(status_code=400, detail="Invalid username or password")
        
    token = str(uuid.uuid4())
    ACTIVE_SESSIONS[token] = username
    return {"token": token, "username": username, "is_admin": user.is_admin}

@app.on_event("startup")
def startup_event():
    logger.info("Starting up Authoring CMS FastAPI Server...")
    # Initialize the separate authoring database
    init_db()
    
    # Run dynamic migration check for owner_id and is_collaborative columns
    db = db_session()
    try:
        inspector = inspect(db.bind)
        
        # 1. Update documents table
        columns_docs = [c['name'] for c in inspector.get_columns('documents')]
        if 'owner_id' not in columns_docs:
            logger.info("Adding owner_id column to documents table...")
            db.execute(text("ALTER TABLE documents ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE;"))
            db.commit()
        if 'is_collaborative' not in columns_docs:
            logger.info("Adding is_collaborative column to documents table...")
            db.execute(text("ALTER TABLE documents ADD COLUMN is_collaborative BOOLEAN DEFAULT 0;"))
            db.commit()
            
        # 2. Update users table
        columns_users = [c['name'] for c in inspector.get_columns('users')]
        if 'is_admin' not in columns_users:
            logger.info("Adding is_admin column to users table...")
            db.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0;"))
            db.commit()
            
        # 3. Create default admin if not exists
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            logger.info("Creating default admin account (username: admin, password: admin123)...")
            admin_pwd_hash = hashlib.sha256(b"admin123").hexdigest()
            admin = User(username="admin", password_hash=admin_pwd_hash, is_admin=True)
            db.add(admin)
            db.commit()
            
        # 4. Create dummy "All Authors" user if not exists
        all_authors_user = db.query(User).filter(User.id == -1).first()
        if not all_authors_user:
            logger.info("Creating dummy 'All Authors' user in database...")
            db.execute(text("INSERT INTO users (id, username, password_hash, is_admin) VALUES (-1, 'all_authors', 'dummy_hash', 0);"))
            db.commit()
            
    except Exception as e:
        logger.warning(f"Migration check failed or not needed: {e}")
    finally:
        db_session.remove()

class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool

    class Config:
        from_attributes = True

class AdminCreateUserPayload(BaseModel):
    username: str
    password: str
    is_admin: bool = False

class ResetPasswordPayload(BaseModel):
    new_password: str

class ToggleCollaborativePayload(BaseModel):
    is_collaborative: bool

class SetPermissionPayload(BaseModel):
    document_id: str
    section_id: str
    user_ids: List[int]

class ReorderSectionsPayload(BaseModel):
    section_ids: List[str]

class MoveSectionPayload(BaseModel):
    section_id: str
    target_id: str
    relation: str # 'child', 'sibling', or 'root'

class SetBookAccessPayload(BaseModel):
    user_ids: List[int]

@app.get("/api/admin/users", response_model=List[UserResponse])
def get_admin_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    users = db.query(User).filter(User.id != -1).order_by(User.id.asc()).all()
    return users

@app.post("/api/admin/users")
def admin_create_user(payload: AdminCreateUserPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    username = payload.username.strip()
    password = payload.password.strip()
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required.")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    user = User(username=username, password_hash=password_hash, is_admin=payload.is_admin)
    db.add(user)
    db.commit()
    return {"status": "success", "message": f"User '{username}' created successfully."}

@app.put("/api/admin/users/{user_id}/reset-password")
def admin_reset_password(user_id: int, payload: ResetPasswordPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    new_password = payload.new_password.strip()
    if not new_password:
        raise HTTPException(status_code=400, detail="Password cannot be empty.")
    user.password_hash = hashlib.sha256(new_password.encode()).hexdigest()
    db.add(user)
    db.commit()
    return {"status": "success", "message": "Password reset successfully."}

@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="You cannot delete yourself.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "User deleted successfully."}

@app.get("/api/admin/logs")
def get_server_logs(type: str = "pipeline", current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    
    log_file = "logs/pipeline.log" if type == "pipeline" else "logs/author_server.log"
    
    if not os.path.exists(log_file):
        return {"logs": f"Log file '{log_file}' does not exist on the server."}
        
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            from collections import deque
            last_lines = deque(f, 500)
            return {"logs": "".join(last_lines)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {str(e)}")

@app.put("/api/documents/{doc_id}/toggle-collaborative")
def toggle_collaborative(doc_id: str, payload: ToggleCollaborativePayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    doc.is_collaborative = payload.is_collaborative
    db.add(doc)
    db.commit()
    return {"status": "success", "is_collaborative": doc.is_collaborative}

@app.get("/api/admin/permissions/{doc_id}")
def get_document_permissions(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    
    modules = db.query(Section).filter(
        Section.document_id == doc_id,
        Section.level == 1
    ).order_by(Section.position).all()
    
    result = []
    for mod in modules:
        perms = db.query(UserPermission).filter(UserPermission.section_id == mod.id).all()
        result.append({
            "section_id": mod.id,
            "module_title": mod.title,
            "assigned_user_ids": [p.user_id for p in perms]
        })
    return result

@app.post("/api/admin/permissions")
def set_document_permission(payload: SetPermissionPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
        
    db.query(UserPermission).filter(UserPermission.section_id == payload.section_id).delete()
    
    for u_id in payload.user_ids:
        if u_id == -1:
            perm = UserPermission(
                user_id=-1,
                document_id=payload.document_id,
                section_id=payload.section_id
            )
            db.add(perm)
        else:
            user = db.query(User).filter(User.id == u_id).first()
            if user:
                perm = UserPermission(
                    user_id=u_id,
                    document_id=payload.document_id,
                    section_id=payload.section_id
                )
                db.add(perm)
                
    db.commit()
    return {"status": "success", "message": "Permissions saved."}

@app.get("/api/admin/books/{doc_id}/access")
def get_book_access(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    access_list = db.query(BookAccess).filter(BookAccess.document_id == doc_id).all()
    return [acc.user_id for acc in access_list]

@app.post("/api/admin/books/{doc_id}/access")
def set_book_access(doc_id: str, payload: SetBookAccessPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin authorization required.")
    db.query(BookAccess).filter(BookAccess.document_id == doc_id).delete()
    for u_id in payload.user_ids:
        if u_id != -1:
            user = db.query(User).filter(User.id == u_id).first()
            if user:
                acc = BookAccess(document_id=doc_id, user_id=u_id)
                db.add(acc)
    db.commit()
    return {"status": "success", "message": "Book access updated."}

@app.get("/", response_class=HTMLResponse)
def read_index():
    template_path = settings.WORKSPACE_DIR / "app" / "web" / "templates" / "author_index.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Templates directory not configured. Please create app/web/templates/author_index.html.</h1>")
    response = HTMLResponse(content=template_path.read_text(encoding="utf-8"))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/api/documents")
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.is_admin:
        docs = db.query(Document).order_by(Document.created_at.desc()).all()
    else:
        # User sees books they own OR books they are explicitly granted book access for
        accessible_doc_ids = db.query(BookAccess.document_id).filter(
            BookAccess.user_id == current_user.id
        ).distinct().all()
        accessible_doc_ids = [d[0] for d in accessible_doc_ids]
        
        docs = db.query(Document).filter(
            (Document.owner_id == current_user.id) | 
            ((Document.is_collaborative == True) & (Document.id.in_(accessible_doc_ids)))
        ).order_by(Document.created_at.desc()).all()

    result = []
    for doc in docs:
        sec_count = db.query(Section).filter(Section.document_id == doc.id).count()
        owner_name = "Unknown"
        if doc.owner_id:
            owner_user = db.query(User).filter(User.id == doc.owner_id).first()
            if owner_user:
                owner_name = owner_user.username
        result.append({
            "id": doc.id,
            "title": doc.title,
            "author": doc.author or "Unknown",
            "created_at": doc.created_at.isoformat() + "Z" if doc.created_at else None,
            "section_count": sec_count,
            "has_epub": True,
            "owner": owner_name,
            "is_collaborative": getattr(doc, 'is_collaborative', False)
        })
    return result

def clean_truncated_suffix(text: str, parsed_chapters: List) -> str:
    if not parsed_chapters:
        return text
    last_ch_id = parsed_chapters[-1][0]
    marker_pat = re.compile(rf'===\s*CHAPTER:\s*{re.escape(last_ch_id)}', re.IGNORECASE)
    match = marker_pat.search(text)
    if not match:
        return text
    start_pos = match.start()
    sub_text = text[start_pos:]
    json_start = sub_text.find('{')
    if json_start == -1:
        return text[:start_pos]
    
    depth = 0
    in_str = False
    esc = False
    json_end = -1
    for i in range(json_start, len(sub_text)):
        ch = sub_text[i]
        if esc:
            esc = False
            continue
        if ch == '\\' and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
        if in_str:
            continue
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                json_end = i
                break
    
    if json_end != -1:
        return text[:start_pos + json_start + json_end + 1]
    else:
        return clean_truncated_suffix(text[:start_pos], parsed_chapters[:-1])

@app.post("/api/documents/create-template")
def create_document_template(payload: CreateTemplatePayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create new books.")
    doc_id = str(uuid.uuid4())
    
    # 1. Create Document record
    doc = Document(
        id=doc_id,
        title=payload.title,
        author=payload.author,
        source_file="template",
        owner_id=current_user.id
    )
    db.add(doc)
    
    # 2. Add standard editable frontmatter sections
    frontmatter_titles = [
        ("Title Page", "book", 1),
        ("Copyright", "book", 1),
        ("About the Book", "book", 1),
        ("About the Author", "book", 1),
        ("Key Features", "book", 1),
        ("Acknowledgement", "book", 1),
        ("Course Outcomes", "book", 1),
        ("Syllabus", "book", 1)
    ]
    
    position = 10
    for title, sec_type, level in frontmatter_titles:
        placeholder = f"# {title}\n\n[Write {title.lower()} content here...]"
        if title == "Copyright":
            placeholder = f"# Copyright\n\nCopyright © 2026 {payload.author or 'Publisher'}. All rights reserved."
        elif title == "Syllabus":
            placeholder = "# Syllabus\n\n| Module | Topic | Chapters |\n|---|---|---|\n| Module 1 | Intro | Chapter 1, 2 |"
            
        sec = Section(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            title=title,
            section_type=sec_type,
            level=level,
            position=position,
            raw_markdown=placeholder,
            formatted_markdown=placeholder,
            validated_markdown=placeholder,
            validation_status="passed",
            processing_status="validated"
        )
        db.add(sec)
        # Seed default assignment to "All Authors" (-1)
        perm = UserPermission(
            user_id=-1,
            document_id=doc_id,
            section_id=sec.id
        )
        db.add(perm)
        position += 10
        
    # 3. Add modules, chapters, sections hierarchy
    chapters = []
    
    if payload.uploaded_jsons:
        logger.info(f"Consuming {len(payload.uploaded_jsons)} uploaded JSON blocks directly.")
        for item in payload.uploaded_jsons:
            if isinstance(item, list):
                for sub_item in item:
                    if isinstance(sub_item, dict) and "chapter_id" in sub_item:
                        ch_id = sub_item["chapter_id"]
                        ch_title = sub_item.get("title", f"Chapter {ch_id}")
                        chapters.append((ch_id, ch_title, sub_item))
            elif isinstance(item, dict):
                if "chapters" in item and isinstance(item["chapters"], list):
                    for sub_item in item["chapters"]:
                        if isinstance(sub_item, dict) and "chapter_id" in sub_item:
                            ch_id = sub_item["chapter_id"]
                            ch_title = sub_item.get("title", f"Chapter {ch_id}")
                            chapters.append((ch_id, ch_title, sub_item))
                elif "chapter_id" in item:
                    ch_id = item["chapter_id"]
                    ch_title = item.get("title", f"Chapter {ch_id}")
                    chapters.append((ch_id, ch_title, item))
                    
        if not chapters:
            raise HTTPException(
                status_code=400, 
                detail="No valid chapter JSON structures found in uploaded files. Please ensure each chapter has a 'chapter_id' and 'sections' field."
            )
            
        output_dir = f"blueprints/{doc_id}"
        os.makedirs(output_dir, exist_ok=True)
        from blueprints.generate_blueprints import save_chapter
        for chapter_id, chapter_title, ch_data in chapters:
            try:
                save_chapter(ch_data, chapter_id, payload.title, output_dir)
            except Exception as ex:
                logger.error(f"Error saving uploaded chapter blueprint: {ex}")
                
    elif payload.syllabus_text and payload.syllabus_text.strip():
        # AI Blueprint generation / parsing logic
        api_key = payload.api_key or os.environ.get("GROQ_API_KEY") or os.environ.get("LLM_API_KEY") or getattr(settings, 'LLM_API_KEY', '')
        base_url = os.environ.get("LLM_BASE_URL") or "https://api.groq.com/openai/v1"
        
        master_prompt = ""
        try:
            from blueprints.generate_blueprints import (
                _load_blueprint_prompt,
                build_prompt,
                extract_chapters,
                save_chapter,
                count_expected_chapters,
                response_seems_complete
            )
            master_prompt = _load_blueprint_prompt()
        except Exception as e:
            logger.error(f"Error importing generate_blueprints helpers: {e}")
            
        chapters = []
        if api_key and master_prompt:
            try:
                import requests
                # Build full prompt
                prompt = build_prompt(
                    payload.syllabus_text,
                    payload.title,
                    payload.title,  # subject
                    payload.stream or "BCom",
                    payload.year or "SY",
                    payload.university or "Mumbai University",
                    already_done=[]
                )
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/Aaaaaaaayush/epub-publisher",
                    "X-Title": "Interactive Authoring CMS"
                }
                url = f"{base_url.rstrip('/')}/chat/completions"
                models_to_try = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "llama-3.1-8b-instant"]
                max_tokens_val = 8192
                
                # Auto-detect OpenRouter keys or endpoint configurations
                if api_key.startswith("sk-or-") or "openrouter" in url.lower():
                    url = "https://openrouter.ai/api/v1/chat/completions"
                    max_tokens_val = 16384
                    models_to_try = [
                        "meta-llama/llama-3.3-70b-instruct:free",
                        "nousresearch/hermes-3-llama-3.1-405b:free",
                        "meta-llama/llama-3.2-3b-instruct:free",
                        "google/gemma-4-31b-it:free",
                        "google/gemma-4-26b-a4b-it:free",
                        "nvidia/nemotron-3-ultra-550b-a55b:free",
                        "nvidia/nemotron-3-super-120b-a12b:free",
                        "tencent/hy3:free",
                        "meta-llama/llama-3.3-70b-instruct"
                    ]
                
                expected_ch = count_expected_chapters(payload.syllabus_text)
                logger.info(f"Estimated chapters from syllabus: ~{expected_ch}")
                
                last_error = None
                successful_model = None
                first_round_content = None
                
                for model in models_to_try:
                    logger.info(f"Attempting syllabus blueprint generation using model: {model} on {url}")
                    data = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.25,
                        "max_tokens": max_tokens_val
                    }
                    try:
                        response = requests.post(url, json=data, headers=headers, timeout=180)
                        response.raise_for_status()
                        res_json = response.json()
                        if "choices" in res_json and len(res_json["choices"]) > 0:
                            res_content = res_json["choices"][0]["message"]["content"]
                        else:
                            err_details = res_json.get("error", {})
                            err_msg = err_details.get("message", "Empty choices returned")
                            raise Exception(f"OpenRouter/Groq API Error: {err_msg}")
                            
                        if not res_content or not isinstance(res_content, str):
                            raise Exception("Received empty or malformed assistant content")
                            
                        new_chapters = extract_chapters(res_content)
                        if new_chapters:
                            successful_model = model
                            first_round_content = clean_truncated_suffix(res_content, new_chapters)
                            chapters.extend(new_chapters)
                            logger.info(f"Successfully started blueprint generation using model: {model}")
                            break
                    except Exception as e:
                        logger.warning(f"Syllabus generation failed with model {model}: {e}")
                        last_error = e
                        
                if not successful_model:
                    if last_error:
                        raise last_error
                    else:
                        raise Exception("No model succeeded in generating blueprints")
                
                # Run continuation rounds if response is incomplete
                all_chapters = [ch[0] for ch in chapters]
                full_response = first_round_content
                
                is_complete = response_seems_complete(first_round_content, expected_ch, len(all_chapters))
                if not is_complete and len(all_chapters) < expected_ch:
                    max_rounds = 4
                    for round_num in range(2, max_rounds + 1):
                        logger.info(f"Requesting continuation round {round_num}/{max_rounds} using {successful_model}...")
                        last_ch_id = all_chapters[-1] if all_chapters else "M1C1"
                        data = {
                            "model": successful_model,
                            "messages": [
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": full_response},
                                {"role": "user", "content": (
                                    f"The last successfully generated chapter was {last_ch_id}. "
                                    "Continue generating the remaining chapters. "
                                    "Start exactly where you left off. "
                                    "Do not repeat any chapters already output. "
                                    "Output the next chapter JSON immediately, "
                                    "starting with === CHAPTER: "
                                )}
                            ],
                            "temperature": 0.25,
                            "max_tokens": max_tokens_val
                        }
                        try:
                            response = requests.post(url, json=data, headers=headers, timeout=180)
                            response.raise_for_status()
                            res_json = response.json()
                            if "choices" in res_json and len(res_json["choices"]) > 0:
                                res_content = res_json["choices"][0]["message"]["content"]
                            else:
                                err_details = res_json.get("error", {})
                                err_msg = err_details.get("message", "Empty choices in continuation")
                                raise Exception(f"API Error: {err_msg}")
                                
                            if not res_content or not isinstance(res_content, str):
                                raise Exception("Empty content in continuation response")
                                
                            new_chapters = extract_chapters(res_content)
                            logger.info(f"Round {round_num}: Found {len(new_chapters)} new chapters")
                            
                            added_new = False
                            for chapter_id, chapter_title, ch_data in new_chapters:
                                if chapter_id not in all_chapters:
                                    chapters.append((chapter_id, chapter_title, ch_data))
                                    all_chapters.append(chapter_id)
                                    added_new = True
                                    
                            if not added_new:
                                logger.info("No new chapters generated in this round. Stopping continuation.")
                                break
                                
                            clean_res = clean_truncated_suffix(res_content, new_chapters)
                            full_response += "\n\n" + clean_res
                            
                            if response_seems_complete(res_content, expected_ch, len(all_chapters)) or len(all_chapters) >= expected_ch:
                                logger.info("Continuation completed.")
                                break
                        except Exception as ce:
                            logger.warning(f"Continuation round {round_num} failed: {ce}")
                            break
                
                if chapters:
                    # Save generated JSON files to output_dir
                    output_dir = f"blueprints/{doc_id}"
                    os.makedirs(output_dir, exist_ok=True)
                    for chapter_id, chapter_title, ch_data in chapters:
                        try:
                            save_chapter(ch_data, chapter_id, payload.title, output_dir)
                        except Exception as ex:
                            logger.error(f"Error saving chapter blueprint: {ex}")
            except Exception as e:
                logger.error(f"AI Blueprint generation failed: {e}. Falling back to parser.")
                
        # Fallback if no key or API call failed
        if not chapters:
            fallback_modules = []
            try:
                # Helper parser
                import json
                modules_list = []
                current_module = None
                current_chapter = None
                
                lines = payload.syllabus_text.split('\n')
                mod_count = 0
                ch_count = 0
                
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                        
                    # Match Module/Unit
                    m_mod = re.match(r'^(Module|Unit|Part)\s*(\d+|[IVXLCDM]+)[:\-\s]*(.*)', line_str, re.IGNORECASE)
                    if m_mod:
                        mod_count += 1
                        current_module = {
                            "id": f"M{mod_count}",
                            "title": f"Module {mod_count}: {m_mod.group(3).strip() or 'Introduction'}",
                            "chapters": []
                        }
                        modules_list.append(current_module)
                        current_chapter = None
                        continue
                        
                    # Match Chapter/Topic
                    m_ch = re.match(r'^(Chapter|Topic|Section)\s*(\d+)[:\-\s]*(.*)', line_str, re.IGNORECASE)
                    if m_ch:
                        if not current_module:
                            mod_count += 1
                            current_module = {
                                "id": f"M{mod_count}",
                                "title": f"Module {mod_count}",
                                "chapters": []
                            }
                            modules_list.append(current_module)
                            
                        ch_count += 1
                        current_chapter = {
                            "chapter_id": f"{current_module['id']}C{len(current_module['chapters']) + 1}",
                            "title": m_ch.group(3).strip() or f"Chapter {ch_count}",
                            "sections": []
                        }
                        current_module["chapters"].append(current_chapter)
                        continue
                        
                    # If it's a bullet/item under a chapter, treat it as a section topic
                    if current_chapter and (line_str.startswith('-') or line_str.startswith('*') or re.match(r'^\d+\.', line_str)):
                        clean_title = re.sub(r'^[\-\*\d\.\s]+', '', line_str).strip()
                        if clean_title:
                            sec_num = len(current_chapter["sections"]) + 1
                            current_chapter["sections"].append({
                                "id": f"{current_chapter['chapter_id']}S{sec_num}",
                                "title": clean_title,
                                "word_budget": 1000,
                                "learning_outcomes": [f"Understand {clean_title}"],
                                "must_cover": [clean_title],
                                "keywords": [clean_title]
                            })
                            
                # If no modules or chapters were found, parse by units/paragraphs
                if not modules_list:
                    for i in range(1, 4):
                        current_module = {
                            "id": f"M{i}",
                            "title": f"Module {i}",
                            "chapters": []
                        }
                        modules_list.append(current_module)
                        for j in range(1, 3):
                            current_chapter = {
                                "chapter_id": f"M{i}C{j}",
                                "title": f"Chapter {j}: Topic of Module {i}",
                                "sections": [
                                    {
                                        "id": f"M{i}C{j}S1",
                                        "title": "Introduction",
                                        "word_budget": 1000,
                                        "learning_outcomes": ["Understand the core concept"],
                                        "must_cover": ["Definitions", "Key principles"],
                                        "keywords": ["Introduction"]
                                    }
                                ]
                            }
                            current_module["chapters"].append(current_chapter)
                fallback_modules = modules_list
            except Exception as pe:
                logger.error(f"Fallback syllabus parsing failed: {pe}")
                
            # Convert fallback modules to (chapter_id, chapter_title, data) list format
            chapters = []
            for mod in fallback_modules:
                for ch in mod.get("chapters", []):
                    chapter_id = ch["chapter_id"]
                    chapter_title = ch["title"]
                    ch_data = {
                        "chapter_id": chapter_id,
                        "title": chapter_title,
                        "estimated_words": sum(s.get("word_budget", 1000) for s in ch.get("sections", [])),
                        "sections": ch.get("sections", [])
                    }
                    chapters.append((chapter_id, chapter_title, ch_data))
                    
                    # Save JSON file on disk
                    output_dir = f"blueprints/{doc_id}"
                    os.makedirs(output_dir, exist_ok=True)
                    try:
                        import json
                        safe_name = re.sub(r'[^\w\s-]', '', payload.title).strip()
                        safe_name = re.sub(r'\s+', '_', safe_name)
                        save_path = os.path.join(output_dir, f"{safe_name}_M{chapter_id[1]}Chapter{chapter_id[3:]}_v2.json")
                        with open(save_path, 'w', encoding='utf-8') as f:
                            json.dump(ch_data, f, indent=2, ensure_ascii=False)
                    except Exception as ex:
                        logger.error(f"Error saving fallback JSON: {ex}")
                        
    if not chapters:
        # Legacy loop creation fallback
        logger.info("No chapters parsed/provided. Creating legacy generic outline skeleton.")
        num_mods = payload.modules if payload.modules is not None else 3
        num_chaps = payload.chapters if payload.chapters is not None else 2
        num_subs = payload.subtopics if payload.subtopics is not None else 4
        
        for m in range(1, num_mods + 1):
            for c in range(1, num_chaps + 1):
                chapter_id = f"M{m}C{c}"
                chapter_title = f"[Chapter Title]"
                sections = []
                for s in range(1, num_subs + 1):
                    sections.append({
                        "id": f"{chapter_id}S{s}",
                        "title": "[Subtopic Title]",
                        "word_budget": 1000,
                        "learning_outcomes": ["Understand the core concept"],
                        "must_cover": ["Definitions", "Key principles"],
                        "keywords": ["Introduction"]
                    })
                ch_data = {
                    "chapter_id": chapter_id,
                    "title": chapter_title,
                    "sections": sections
                }
                chapters.append((chapter_id, chapter_title, ch_data))

    # Insert chapters/sections from parsed outline
    modules_map = {}
    for chapter_id, chapter_title, data in chapters:
        m = re.match(r'M(\d+)C(\d+)', chapter_id, re.IGNORECASE)
        m_num = m.group(1) if m else "1"
        if m_num not in modules_map:
            modules_map[m_num] = []
        modules_map[m_num].append((chapter_id, chapter_title, data))
        
    for m_num in sorted(modules_map.keys(), key=int):
        m_title = f"Module {m_num}"
        m_id = str(uuid.uuid4())
        m_sec = Section(
            id=m_id,
            document_id=doc_id,
            title=m_title,
            section_type="chapter",
            level=1,
            position=position,
            raw_markdown=f"# {m_title}\n\n[Module introduction here...]",
            formatted_markdown=f"# {m_title}",
            validated_markdown=f"# {m_title}",
            validation_status="passed",
            processing_status="validated"
        )
        db.add(m_sec)
        position += 10
        
        chapters_list = modules_map[m_num]
        def get_ch_num(item):
            ch_id = item[0]
            match = re.match(r'M\d+C(\d+)', ch_id, re.IGNORECASE)
            return int(match.group(1)) if match else 1
        chapters_list.sort(key=get_ch_num)
        
        for chapter_id, chapter_title, data in chapters_list:
            match = re.match(r'M\d+C(\d+)', chapter_id, re.IGNORECASE)
            c_num = match.group(1) if match else "1"
            
            c_id = str(uuid.uuid4())
            c_title = f"Chapter {c_num}: {chapter_title}"
            c_sec = Section(
                id=c_id,
                document_id=doc_id,
                parent_id=m_id,
                title=c_title,
                section_type="chapter",
                level=2,
                position=position,
                raw_markdown=f"## {c_title}\n\n[Chapter introduction here...]",
                formatted_markdown=f"## {c_title}",
                validated_markdown=f"## {c_title}",
                validation_status="passed",
                processing_status="validated"
            )
            db.add(c_sec)
            position += 10
            
            sections = data.get("sections", [])
            for s_idx, s_data in enumerate(sections, 1):
                s_title = f"{c_num}.{s_idx} {s_data.get('title', 'Section')}"
                
                outcomes = s_data.get("learning_outcomes", [])
                if isinstance(outcomes, list):
                    outcomes_list = "\n".join(f"- {str(o)}" for o in outcomes)
                else:
                    outcomes_list = f"- {str(outcomes)}" if outcomes else "None"
                    
                keywords = s_data.get("keywords", [])
                if isinstance(keywords, list):
                    keywords_list = ", ".join(str(k) for k in keywords)
                else:
                    keywords_list = str(keywords) if keywords else "None"
                    
                must_cover = s_data.get("must_cover", [])
                if isinstance(must_cover, list):
                    must_cover_list = "\n".join(f"- [ ] {str(item)}" for item in must_cover)
                else:
                    must_cover_list = f"- [ ] {str(must_cover)}" if must_cover else "None"
                    
                notes_text = s_data.get("notes", "")
                if not isinstance(notes_text, str):
                    notes_text = str(notes_text)
                
                # Extract diagram, table, and examples info from blueprint safely
                diag_data = s_data.get("diagram")
                diag_required = False
                diag_info = ""
                if isinstance(diag_data, dict):
                    diag_required = bool(diag_data.get("required"))
                    if diag_required:
                        diag_info = f"\n**Required Diagram ({diag_data.get('type', 'General')}):** {diag_data.get('title', 'Not specified')}\n"
                elif isinstance(diag_data, bool):
                    diag_required = diag_data
                    if diag_required:
                        diag_info = "\n**Required Diagram:** Yes\n"
                    
                table_data = s_data.get("table")
                table_required = False
                table_info = ""
                if isinstance(table_data, dict):
                    table_required = bool(table_data.get("required"))
                    if table_required:
                        table_info = f"\n**Required Table ({table_data.get('type', 'General')}):** {table_data.get('title', 'Not specified')}\n"
                elif isinstance(table_data, bool):
                    table_required = table_data
                    if table_required:
                        table_info = "\n**Required Table:** Yes\n"
                    
                ex_data = s_data.get("examples")
                ex_required = False
                ex_info = ""
                if isinstance(ex_data, dict):
                    ex_val = ex_data.get("required")
                    ex_required = ex_val is True or (isinstance(ex_val, (int, float)) and ex_val > 0)
                    if ex_required:
                        suggs = ", ".join(str(s) for s in ex_data.get("suggestions", [])) if isinstance(ex_data.get("suggestions"), list) else ""
                        ex_type = ex_data.get("type", "General")
                        ex_info = f"\n**Required Example ({ex_type}):** {suggs}\n"
                elif isinstance(ex_data, bool):
                    ex_required = ex_data
                    if ex_required:
                        ex_info = "\n**Required Examples:** Yes\n"
                elif isinstance(ex_data, (int, float)):
                    ex_required = ex_data > 0
                    if ex_required:
                        ex_info = f"\n**Required Examples ({int(ex_data)}):** Yes\n"
                
                difficulty = s_data.get("difficulty", "medium")
                exam_weight = s_data.get("exam_weight", "medium")
                word_budget = s_data.get("word_budget", 1000)
                est_pages = s_data.get("estimated_pages", round(word_budget / 280, 1))
                
                not_cover = s_data.get("must_not_cover", [])
                if isinstance(not_cover, list):
                    not_cover_list = "\n".join(f"- {str(item)}" for item in not_cover)
                else:
                    not_cover_list = str(not_cover)
                if not not_cover_list.strip() or not_cover_list == "[]":
                    not_cover_list = "None"
                
                prereqs = s_data.get("prerequisites", [])
                if isinstance(prereqs, list):
                    prereqs_list = ", ".join(str(p) for p in prereqs)
                else:
                    prereqs_list = str(prereqs)
                if not prereqs_list.strip() or prereqs_list == "[]":
                    prereqs_list = "None"
                
                section_markdown = (
                    f"### {s_title}\n\n"
                    f"**Section Metadata:**\n"
                    f"- Difficulty: {difficulty.capitalize() if isinstance(difficulty, str) else 'Medium'}\n"
                    f"- Exam Weight: {exam_weight.capitalize() if isinstance(exam_weight, str) else 'Medium'}\n"
                    f"- Word Budget: {word_budget} words (~{est_pages} pages)\n"
                    f"- Prerequisites: {prereqs_list}\n\n"
                    f"**Learning Outcomes:**\n{outcomes_list}\n\n"
                    f"**Keywords:** {keywords_list}\n\n"
                    f"**Content Guidance:** {notes_text}\n\n"
                    f"{diag_info}"
                    f"{table_info}"
                    f"{ex_info}"
                    f"\n**Must Cover Checklist:**\n{must_cover_list}\n\n"
                    f"**Do Not Cover (Prevents Content Bleed):**\n{not_cover_list}\n\n"
                    f"[Write section content here...]"
                )
                
                s_id = str(uuid.uuid4())
                s_sec = Section(
                    id=s_id,
                    document_id=doc_id,
                    parent_id=c_id,
                    title=s_title,
                    section_type="topic",
                    level=3,
                    position=position,
                    raw_markdown=section_markdown,
                    formatted_markdown=f"### {s_title}",
                    validated_markdown=section_markdown,
                    validation_status="passed",
                    processing_status="validated"
                )
                db.add(s_sec)
                position += 10
                
            exercise_types = [
                ("MCQ", f"### MCQ\n\nQ1. [Enter question text here]\nA) [Option A]\nB) [Option B]\nC) [Option C]\nD) [Option D]\n<!-- ANSWER: B -->"),
                ("True or False", f"### True or False\n\nQ1. [Enter question text here]\nTrue / False\n<!-- ANSWER: True -->"),
                ("Fill in the Blanks", f"### Fill in the Blanks\n\nQ1. The capital of France is __________.\n<!-- ANSWER: Paris -->"),
                ("Match the Following", f"### Match the Following\n\nQ1. Match the following:\n1. Python | A. Programming Language\n2. HTML | B. Markup Language\n<!-- ANSWER: 1-A, 2-B -->")
            ]
            
            for ex_name, ex_tpl in exercise_types:
                ex_title = f"Chapter {c_num} {ex_name}"
                ex_sec = Section(
                    id=str(uuid.uuid4()),
                    document_id=doc_id,
                    parent_id=c_id,
                    title=ex_title,
                    section_type="topic",
                    level=3,
                    position=position,
                    raw_markdown=ex_tpl,
                    formatted_markdown=ex_tpl,
                    validated_markdown=ex_tpl,
                    validation_status="passed",
                    processing_status="validated"
                )
                db.add(ex_sec)
                position += 10
                
    # 4. Add backmatter sections
    backmatter_titles = [
        ("Practice Questions", "chapter", 1),
        ("Answers to Exercises", "chapter", 1)
    ]
    for title, sec_type, level in backmatter_titles:
        sec = Section(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            title=title,
            section_type=sec_type,
            level=level,
            position=position,
            raw_markdown=f"# {title}\n\n[Answers are dynamically generated here upon final compilation...]",
            formatted_markdown=f"# {title}",
            validated_markdown=f"# {title}",
            validation_status="passed",
            processing_status="validated"
        )
        db.add(sec)
        position += 10
        
    db.commit()
    return {"document_id": doc_id, "status": "success"}
def is_section_editable(user: User, doc: Document, sec: Section, db: Session) -> bool:
    if user.is_admin or doc.owner_id == user.id:
        return True
    if not doc.is_collaborative:
        return doc.owner_id == user.id
        
    has_access = db.query(BookAccess).filter(BookAccess.document_id == doc.id, BookAccess.user_id == user.id).first() is not None
    if not has_access:
        return False
        
    frontmatter_titles = ["Title Page", "Copyright", "About the Book", "About the Author", "Key Features", "Acknowledgement", "Course Outcomes", "Syllabus"]
    
    curr = sec
    visited = set()
    while curr and curr.parent_id and curr.id not in visited:
        visited.add(curr.id)
        curr = db.query(Section).filter(Section.id == curr.parent_id).first()
        
    if not curr:
        return False
        
    perm = db.query(UserPermission).filter(
        (UserPermission.document_id == doc.id) &
        (UserPermission.section_id == curr.id) &
        ((UserPermission.user_id == user.id) | (UserPermission.user_id == -1))
    ).first()
    return perm is not None

def is_section_readable(user: User, doc: Document, sec: Section, db: Session) -> bool:
    if user.is_admin or doc.owner_id == user.id:
        return True
    if not doc.is_collaborative:
        return doc.owner_id == user.id
        
    has_access = db.query(BookAccess).filter(BookAccess.document_id == doc.id, BookAccess.user_id == user.id).first() is not None
    if not has_access:
        return False
        
    frontmatter_titles = ["Title Page", "Copyright", "About the Book", "About the Author", "Key Features", "Acknowledgement", "Course Outcomes", "Syllabus"]
    
    curr = sec
    visited = set()
    while curr and curr.parent_id and curr.id not in visited:
        visited.add(curr.id)
        curr = db.query(Section).filter(Section.id == curr.parent_id).first()
        
    if not curr:
        return False
        
    if curr.title in frontmatter_titles:
        return True
        
    perm = db.query(UserPermission).filter(
        (UserPermission.document_id == doc.id) &
        (UserPermission.section_id == curr.id) &
        ((UserPermission.user_id == user.id) | (UserPermission.user_id == -1))
    ).first()
    return perm is not None

@app.get("/api/documents/{doc_id}/sections")
def list_document_sections(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not current_user.is_admin and doc.owner_id != current_user.id:
        if doc.is_collaborative:
            has_access = db.query(BookAccess).filter(BookAccess.document_id == doc_id, BookAccess.user_id == current_user.id).first() is not None
            if not has_access:
                raise HTTPException(status_code=403, detail="Access denied.")
        else:
            raise HTTPException(status_code=403, detail="Access denied.")
            
    sections = db.query(Section)\
        .filter(Section.document_id == doc_id)\
        .order_by(Section.position)\
        .all()
        
    if not sections:
        raise HTTPException(status_code=404, detail="No sections found.")
        
    return [{
        "id": sec.id,
        "parent_id": sec.parent_id,
        "title": sec.title,
        "level": sec.level,
        "position": sec.position,
        "section_type": sec.section_type,
        "editable": is_section_editable(current_user, doc, sec, db),
        "readable": is_section_readable(current_user, doc, sec, db)
    } for sec in sections]

@app.put("/api/documents/{doc_id}/sections/reorder")
def reorder_document_sections(doc_id: str, payload: ReorderSectionsPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not current_user.is_admin and doc.owner_id != current_user.id:
        if doc.is_collaborative:
            has_access = db.query(BookAccess).filter(BookAccess.document_id == doc_id, BookAccess.user_id == current_user.id).first() is not None
            if not has_access:
                raise HTTPException(status_code=403, detail="Access denied.")
        else:
            raise HTTPException(status_code=403, detail="Access denied.")
            
    for index, sec_id in enumerate(payload.section_ids):
        db.query(Section).filter(
            Section.document_id == doc_id,
            Section.id == sec_id
        ).update({Section.position: (index + 1) * 10})
        
    db.commit()
    return {"status": "success", "message": "Outline reordered."}

@app.post("/api/documents/{doc_id}/sections/move")
def move_document_section(doc_id: str, payload: MoveSectionPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    sec = db.query(Section).filter(Section.document_id == doc_id, Section.id == payload.section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found.")
        
    if not is_section_editable(current_user, doc, sec, db):
        raise HTTPException(status_code=403, detail="Permission denied.")
        
    old_level = sec.level
    
    if payload.relation == 'root':
        sec.parent_id = None
        sec.level = 1
        target_pos = sec.position
    else:
        target = db.query(Section).filter(Section.document_id == doc_id, Section.id == payload.target_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target section not found.")
            
        if payload.relation == 'child':
            sec.parent_id = target.id
            sec.level = target.level + 1
            target_pos = target.position + 1
        elif payload.relation == 'sibling':
            sec.parent_id = target.parent_id
            sec.level = target.level
            target_pos = target.position + 1
        else:
            raise HTTPException(status_code=400, detail="Invalid relation type.")
            
    # Update levels of all descendants recursively
    level_delta = sec.level - old_level
    if level_delta != 0:
        def update_descendants_level(parent_id, delta):
            children = db.query(Section).filter(Section.parent_id == parent_id).all()
            for child in children:
                child.level += delta
                db.add(child)
                update_descendants_level(child.id, delta)
        update_descendants_level(sec.id, level_delta)
        
    # Temporarily set the moved section's position to target_pos
    sec.position = target_pos
    db.add(sec)
    db.commit()
    
    # Re-query all sections of the document, order them by position (handling decimal positions appropriately)
    all_sections = db.query(Section).filter(Section.document_id == doc_id).all()
    
    # Sort them statefully. If positions are equal, the moved one (sec) goes after the target.
    all_sections.sort(key=lambda s: (s.position, 1 if s.id == sec.id else 0))
    
    # Re-assign positions as clean multiples of 10
    for idx, s in enumerate(all_sections):
        s.position = (idx + 1) * 10
        db.add(s)
        
    db.commit()
    return {"status": "success", "message": "Hierarchy and order updated."}

@app.post("/api/documents/{doc_id}/sections")
def add_section_node(doc_id: str, payload: AddSectionPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    level = payload.level
    position = 10
    parent_id = payload.parent_id
    
    if parent_id:
        parent = db.query(Section).filter(Section.id == parent_id).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent section not found.")
        if not is_section_editable(current_user, doc, parent, db):
            raise HTTPException(status_code=403, detail="You do not have permission to edit this module.")
        level = parent.level + 1
        
        db.query(Section).filter(
            Section.document_id == doc_id,
            Section.position > parent.position
        ).update({Section.position: Section.position + 10})
        position = parent.position + 10
    else:
        # Creating a module node or page (level 1). Allow if admin/owner or has any permission on this document.
        if not current_user.is_admin and doc.owner_id != current_user.id:
            has_any_perm = db.query(UserPermission).filter(
                (UserPermission.document_id == doc_id) &
                ((UserPermission.user_id == current_user.id) | (UserPermission.user_id == -1))
            ).first()
            if not has_any_perm:
                raise HTTPException(status_code=403, detail="Only authorized authors can create level-1 pages or modules.")
        from sqlalchemy import func
        max_pos = db.query(func.max(Section.position)).filter(Section.document_id == doc_id).scalar()
        position = (max_pos or 0) + 10
        
    new_sec = Section(
        id=str(uuid.uuid4()),
        document_id=doc_id,
        parent_id=parent_id,
        title=payload.title,
        section_type=payload.section_type,
        level=level,
        position=position,
        raw_markdown=f"# {payload.title}\n\n[Write content here...]",
        formatted_markdown=f"# {payload.title}",
        validated_markdown=f"# {payload.title}",
        validation_status="passed",
        processing_status="validated"
    )
    db.add(new_sec)
    db.commit()
    
    if level == 1 and payload.section_type == 'chapter':
        child_id = str(uuid.uuid4())
        child_title = "Chapter 1: [Chapter Title]"
        child_sec = Section(
            id=child_id,
            document_id=doc_id,
            parent_id=new_sec.id,
            title=child_title,
            section_type="chapter",
            level=2,
            position=position + 1,
            raw_markdown=f"## {child_title}\n\n[Chapter introduction here...]",
            formatted_markdown=f"## {child_title}",
            validated_markdown=f"## {child_title}",
            validation_status="passed",
            processing_status="validated"
        )
        db.add(child_sec)
        db.commit()
        
    return {"status": "success", "section_id": new_sec.id}

@app.put("/api/sections/{section_id}/rename")
def rename_section(section_id: str, payload: RenameSectionPayload, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sec = db.query(Section).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found.")
    doc = db.query(Document).filter(Document.id == sec.document_id).first()
    if not is_section_editable(current_user, doc, sec, db):
        raise HTTPException(status_code=403, detail="You do not have permission to rename this section.")
    sec.title = payload.title
    db.add(sec)
    db.commit()
    return {"status": "success"}

def _delete_descendants_recursive(db: Session, parent_id: str):
    children = db.query(Section).filter(Section.parent_id == parent_id).all()
    for child in children:
        _delete_descendants_recursive(db, child.id)
        db.delete(child)

@app.delete("/api/sections/{section_id}")
def delete_section(section_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sec = db.query(Section).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found.")
    doc = db.query(Document).filter(Document.id == sec.document_id).first()
    if not is_section_editable(current_user, doc, sec, db):
        raise HTTPException(status_code=403, detail="You do not have permission to delete this section.")
    
    _delete_descendants_recursive(db, sec.id)
    db.delete(sec)
    db.commit()
    return {"status": "success"}

@app.get("/api/sections/{section_id}")
def get_section(section_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sec = db.query(Section).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found.")
    doc = db.query(Document).filter(Document.id == sec.document_id).first()
    if not is_section_readable(current_user, doc, sec, db):
        raise HTTPException(status_code=403, detail="You do not have permission to read this section.")
    return {
        "id": sec.id,
        "title": sec.title,
        "raw_markdown": sec.raw_markdown or "",
        "validated_markdown": sec.validated_markdown or "",
        "editable": is_section_editable(current_user, doc, sec, db)
    }

@app.put("/api/sections/{section_id}")
def update_section(section_id: str, data: SectionUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sec = db.query(Section).filter(Section.id == section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found.")
    doc = db.query(Document).filter(Document.id == sec.document_id).first()
    if not is_section_editable(current_user, doc, sec, db):
        raise HTTPException(status_code=403, detail="You do not have permission to edit this section.")
        
    sec.raw_markdown = data.validated_markdown
    sec.validated_markdown = data.validated_markdown
    sec.formatted_markdown = data.validated_markdown
    sec.processing_status = "validated"
    sec.validation_status = "passed"
    
    from app.epub.generator import MarkdownToHtmlConverter
    converter = MarkdownToHtmlConverter()
    sec.html_content = converter.convert(data.validated_markdown)
    
    db.add(sec)
    db.commit()
    
    generator = EpubGenerator(db)
    html_preview = generator.post_process_html(sec.html_content)
    
    return {
        "status": "success",
        "html_preview": html_preview
    }

def find_epub_file(doc_id: str) -> Optional[Path]:
    epub_dir = settings.DATA_DIR / "epub"
    if not epub_dir.exists():
        return None
    for f in epub_dir.glob("*.epub"):
        if doc_id[:8] in f.name:
            return f
    return None

@app.post("/api/documents/{doc_id}/recompile")
def recompile_book(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not current_user.is_admin and doc.owner_id != current_user.id:
        has_any_perm = db.query(UserPermission).filter(UserPermission.user_id == current_user.id, UserPermission.document_id == doc_id).first()
        if not has_any_perm:
            raise HTTPException(status_code=403, detail="Access denied.")
        
    sanitized_title = re.sub(r'[\/:*?"<>|]', '', doc.title)
    sanitized_title = sanitized_title.lower().replace(' ', '_')
    epub_filename = f"{sanitized_title}_{doc.id[:8]}.epub"
    
    epub_dir = settings.DATA_DIR / "epub"
    epub_dir.mkdir(parents=True, exist_ok=True)
    epub_output_path = epub_dir / epub_filename
    
    generator = EpubGenerator(db)
    compiled_epub_path = generator.generate_epub(doc.id, epub_output_path)
    
    # Copy to root directory for easy local access
    try:
        shutil.copy2(compiled_epub_path, settings.WORKSPACE_DIR / "reproduced.epub")
    except Exception as e:
        logger.warning(f"Could not copy reproduced.epub to workspace root: {e}")
    
    return {
        "status": "success",
        "download_url": f"/api/documents/{doc_id}/download"
    }

@app.get("/api/documents/{doc_id}/download")
def download_epub(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not current_user.is_admin and doc.owner_id != current_user.id:
        has_any_perm = db.query(UserPermission).filter(UserPermission.user_id == current_user.id, UserPermission.document_id == doc_id).first()
        if not has_any_perm:
            raise HTTPException(status_code=403, detail="Access denied.")
            
    epub_path = find_epub_file(doc_id)
    if not epub_path or not epub_path.exists():
        raise HTTPException(status_code=404, detail="Compiled EPUB not found.")
    return FileResponse(
        path=epub_path,
        filename=epub_path.name,
        media_type="application/epub+zip"
    )

@app.get("/api/documents/{doc_id}/download/docx")
def download_docx(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not current_user.is_admin and doc.owner_id != current_user.id:
        has_any_perm = db.query(UserPermission).filter(UserPermission.user_id == current_user.id, UserPermission.document_id == doc_id).first()
        if not has_any_perm:
            raise HTTPException(status_code=403, detail="Access denied.")
            
    try:
        filter_user = None if (current_user.is_admin or doc.owner_id == current_user.id) else current_user
        generator = DocxGenerator(db)
        docx_doc = generator.generate(doc_id, user=filter_user)
        
        file_stream = io.BytesIO()
        docx_doc.save(file_stream)
        file_stream.seek(0)
        
        return StreamingResponse(
            file_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=book_{doc_id[:8]}.docx"}
        )
    except Exception as e:
        logger.exception(f"DOCX download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents/{doc_id}/download/pdf")
def download_pdf(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
        
    if not current_user.is_admin and doc.owner_id != current_user.id:
        has_any_perm = db.query(UserPermission).filter(UserPermission.user_id == current_user.id, UserPermission.document_id == doc_id).first()
        if not has_any_perm:
            raise HTTPException(status_code=403, detail="Access denied.")
            
    try:
        filter_user = None if (current_user.is_admin or doc.owner_id == current_user.id) else current_user
        generator = PdfGenerator(db)
        file_stream = io.BytesIO()
        success = generator.generate(doc_id, file_stream, user=filter_user)
        if not success:
            raise Exception("PDF compilation error.")
        file_stream.seek(0)
        
        return StreamingResponse(
            file_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=book_{doc_id[:8]}.pdf"}
        )
    except Exception as e:
        logger.exception(f"PDF download failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.is_admin:
        doc = db.query(Document).filter(Document.id == doc_id).first()
    else:
        doc = db.query(Document).filter(Document.id == doc_id, Document.owner_id == current_user.id).first()
        
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    
    db.delete(doc)
    db.commit()
    
    # Clean up generated EPUB file
    epub_path = find_epub_file(doc_id)
    if epub_path and epub_path.exists():
        try:
            epub_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete EPUB file {epub_path}: {e}")
            
    return {"status": "success"}

@app.post("/api/media/upload")
def upload_media(file: UploadFile = File(...)):
    uploads_dir = settings.DATA_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    
    ext = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{ext}"
    dest_path = uploads_dir / unique_filename
    
    with open(dest_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"url": f"/uploads/{unique_filename}", "filename": file.filename}
