import os
import re
import uuid
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config.settings import settings
from app.database.session import db_session, init_db
from app.models.document import Document, Section
from app.agents.coordinator import PipelineCoordinator
from app.epub.generator import EpubGenerator
from app.utils.logger import logger

app = FastAPI(title="Semantic EPUB Publisher Web Dashboard")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory status store for background jobs
ACTIVE_JOBS: Dict[str, Dict] = {}

class SectionUpdate(BaseModel):
    validated_markdown: str

@app.on_event("startup")
def startup_event():
    logger.info("Starting up FastAPI Server...")
    init_db()

@app.get("/", response_class=HTMLResponse)
def read_index():
    template_path = settings.WORKSPACE_DIR / "app" / "web" / "templates" / "index.html"
    if not template_path.exists():
        # Fallback template if file not found
        return HTMLResponse("<h1>Templates directory not configured. Please create app/web/templates/index.html.</h1>")
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))

def run_ingestion_job(doc_id: str, docx_path: Path, title: Optional[str] = None, author: Optional[str] = None, api_key: Optional[str] = None):
    db = db_session()
    coordinator = PipelineCoordinator(db, api_key=api_key)
    try:
        ACTIVE_JOBS[doc_id] = {"status": "processing", "progress": 5, "error": None}
        output_epub = coordinator.run_pipeline(
            docx_path=docx_path,
            doc_title=title,
            doc_author=author,
            doc_id=doc_id
        )
        ACTIVE_JOBS[doc_id] = {
            "status": "completed",
            "progress": 100,
            "error": None,
            "epub_path": str(output_epub)
        }
        logger.info(f"Background Job Success for document {doc_id} -> {output_epub}")
    except Exception as e:
        logger.exception(f"Background Job Failed for document {doc_id}: {e}")
        ACTIVE_JOBS[doc_id] = {
            "status": "failed",
            "progress": 0,
            "error": str(e)
        }
    finally:
        db_session.remove()

@app.post("/api/documents/upload")
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    api_key: Optional[str] = Form(None)
):
    if not file.filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only Word (.docx) documents are supported.")
        
    doc_id = str(uuid.uuid4())
    
    # Save uploaded file
    input_dir = settings.DATA_DIR / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    temp_docx_path = input_dir / f"{doc_id}_{file.filename}"
    
    with open(temp_docx_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Start pipeline in the background
    background_tasks.add_task(
        run_ingestion_job,
        doc_id=doc_id,
        docx_path=temp_docx_path,
        title=title,
        author=author,
        api_key=api_key
    )
    
    return {
        "document_id": doc_id,
        "message": "Upload successful. Ingestion pipeline started in background.",
        "status_url": f"/api/documents/{doc_id}/status"
    }

@app.get("/api/documents/{doc_id}/status")
def get_document_status(doc_id: str):
    db = db_session()
    try:
        # Check active jobs dictionary first
        job = ACTIVE_JOBS.get(doc_id)
        if job:
            if job["status"] == "processing":
                # Calculate progress dynamically based on sections processed
                total_sections = db.query(Section).filter(Section.document_id == doc_id).count()
                if total_sections > 0:
                    processed = db.query(Section).filter(
                        Section.document_id == doc_id,
                        Section.processing_status.in_(["validated", "html_generated"])
                    ).count()
                    progress = min(95, int((processed / total_sections) * 90) + 5)
                    job["progress"] = progress
            return job
            
        # If not in active jobs (e.g. server restarted but exists in DB)
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        # Check if EPUB file exists on disk
        epub_path = find_epub_file(doc_id)
        if epub_path:
            return {
                "status": "completed",
                "progress": 100,
                "error": None,
                "epub_path": str(epub_path)
            }
            
        return {
            "status": "processing",
            "progress": 50,
            "error": "Pipeline status untracked but document exists in DB."
        }
    finally:
        db_session.remove()

@app.get("/api/documents")
def list_documents():
    db = db_session()
    try:
        docs = db.query(Document).order_by(Document.created_at.desc()).all()
        result = []
        for doc in docs:
            sec_count = db.query(Section).filter(Section.document_id == doc.id).count()
            # Find download URL if exists
            epub_path = find_epub_file(doc.id)
            has_epub = epub_path is not None
            
            result.append({
                "id": doc.id,
                "title": doc.title,
                "author": doc.author or "Unknown",
                "created_at": doc.created_at.isoformat() + "Z" if doc.created_at else None,
                "section_count": sec_count,
                "has_epub": has_epub
            })
        return result
    finally:
        db_session.remove()

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str):
    db = db_session()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
            
        # Delete files on disk
        # 1. Source word file
        if doc.source_file and os.path.exists(doc.source_file):
            try:
                os.remove(doc.source_file)
            except Exception:
                pass
                
        # 2. EPUB file
        epub_path = find_epub_file(doc_id)
        if epub_path and epub_path.exists():
            try:
                os.remove(epub_path)
            except Exception:
                pass
                
        # Delete DB records
        db.delete(doc)
        db.commit()
        
        # Clean job record if any
        if doc_id in ACTIVE_JOBS:
            del ACTIVE_JOBS[doc_id]
            
        return {"status": "success", "message": f"Document {doc_id} deleted."}
    finally:
        db_session.remove()

@app.get("/api/documents/{doc_id}/sections")
def list_document_sections(doc_id: str):
    db = db_session()
    try:
        sections = db.query(Section)\
            .filter(Section.document_id == doc_id)\
            .order_by(Section.position)\
            .all()
        if not sections:
            raise HTTPException(status_code=404, detail="No sections found for this document.")
            
        return [{
            "id": sec.id,
            "parent_id": sec.parent_id,
            "title": sec.title,
            "level": sec.level,
            "position": sec.position,
            "section_type": sec.section_type,
            "validation_status": sec.validation_status,
            "processing_status": sec.processing_status
        } for sec in sections]
    finally:
        db_session.remove()

@app.get("/api/sections/{section_id}")
def get_section(section_id: str):
    db = db_session()
    try:
        sec = db.query(Section).filter(Section.id == section_id).first()
        if not sec:
            raise HTTPException(status_code=404, detail="Section not found.")
            
        # Return content with markdown
        content = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown or ""
        
        # Also render temporary html preview
        from app.epub.generator import MarkdownToHtmlConverter
        converter = MarkdownToHtmlConverter()
        html_preview = converter.convert(content)
        
        # Clean math and format classes for full preview fidelity
        generator = EpubGenerator(db)
        html_preview = generator.post_process_html(html_preview)
        
        return {
            "id": sec.id,
            "title": sec.title,
            "level": sec.level,
            "markdown": content,
            "html_preview": html_preview,
            "processing_status": sec.processing_status,
            "validation_status": sec.validation_status
        }
    finally:
        db_session.remove()

@app.put("/api/sections/{section_id}")
def update_section(section_id: str, data: SectionUpdate):
    db = db_session()
    try:
        sec = db.query(Section).filter(Section.id == section_id).first()
        if not sec:
            raise HTTPException(status_code=404, detail="Section not found.")
            
        # Update content in DB
        sec.validated_markdown = data.validated_markdown
        sec.formatted_markdown = data.validated_markdown
        sec.processing_status = "validated"
        sec.validation_status = "passed" # Manual override validation
        
        # Re-convert to HTML content column
        from app.epub.generator import MarkdownToHtmlConverter
        converter = MarkdownToHtmlConverter()
        sec.html_content = converter.convert(data.validated_markdown)
        
        db.add(sec)
        db.commit()
        
        # Generate new HTML preview
        generator = EpubGenerator(db)
        html_preview = generator.post_process_html(sec.html_content)
        
        return {
            "status": "success",
            "message": "Section updated successfully.",
            "html_preview": html_preview
        }
    finally:
        db_session.remove()

@app.post("/api/documents/{doc_id}/recompile")
def recompile_epub(doc_id: str, api_key: Optional[str] = Form(None)):
    db = db_session()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")
            
        # Compile filename and output path
        import re
        sanitized_title = re.sub(r'[\/:*?"<>|]', '', doc.title)
        sanitized_title = sanitized_title.lower().replace(' ', '_')
        epub_filename = f"{sanitized_title}_{doc.id[:8]}.epub"
        epub_output_path = settings.DATA_DIR / "epub" / epub_filename
        
        generator = EpubGenerator(db, api_key=api_key)
        compiled_epub_path = generator.generate_epub(doc.id, epub_output_path)
        
        # Also copy to root as reproduced.epub for immediate access
        root_epub = Path("d:/agentic_workflow/reproduced.epub")
        shutil.copy2(compiled_epub_path, root_epub)
        logger.info(f"Recompile: Copied EPUB to {root_epub}")
        
        return {
            "status": "success",
            "message": "EPUB recompiled successfully from database section edits.",
            "download_url": f"/api/documents/{doc_id}/download"
        }
    except Exception as e:
        logger.exception(f"Recompilation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Recompilation failed: {str(e)}")
    finally:
        db_session.remove()

@app.get("/api/documents/{doc_id}/download")
def download_epub(doc_id: str):
    epub_path = find_epub_file(doc_id)
    if not epub_path or not epub_path.exists():
        raise HTTPException(status_code=404, detail="Compiled EPUB file not found on disk. Please compile it first.")
    return FileResponse(
        path=epub_path,
        filename=epub_path.name,
        media_type="application/epub+zip"
    )

def find_epub_file(doc_id: str) -> Optional[Path]:
    """Helper to locate the generated EPUB file in the data/epub directory matching doc_id suffix."""
    epub_dir = settings.DATA_DIR / "epub"
    if not epub_dir.exists():
        return None
    doc_suffix = doc_id[:8]
    for path in epub_dir.glob("*.epub"):
        if path.name.endswith(f"_{doc_suffix}.epub"):
            return path
    return None

# ─────────────────────────────────────────────────────────────
# Batch Textbooks Endpoints
# ─────────────────────────────────────────────────────────────

TEXTBOOKS_DIR = settings.DATA_DIR / "textbooks"

def _get_processed_hashes() -> set:
    """Return SHA-256 hashes of all already-processed source files."""
    db = db_session()
    try:
        docs = db.query(Document).all()
        hashes = set()
        for doc in docs:
            src = doc.source_file
            if src:
                p = Path(src)
                if p.exists():
                    import hashlib
                    hashes.add(hashlib.sha256(p.read_bytes()).hexdigest())
        return hashes
    finally:
        db_session.remove()

@app.get("/api/textbooks/scan")
def scan_textbooks():
    """
    Scan data/textbooks/ for .docx files and return which ones are new
    (not yet converted) vs already processed.
    """
    TEXTBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    processed_hashes = _get_processed_hashes()
    result = []
    import hashlib
    for f in sorted(TEXTBOOKS_DIR.glob("*.docx")):
        file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
        result.append({
            "filename": f.name,
            "size_mb": round(f.stat().st_size / 1_048_576, 1),
            "already_processed": file_hash in processed_hashes,
        })
    return {"textbooks_dir": str(TEXTBOOKS_DIR), "files": result}

@app.post("/api/textbooks/batch")
def batch_convert_textbooks(background_tasks: BackgroundTasks, reprocess: bool = False):
    """
    Queue all unprocessed .docx files in data/textbooks/ for conversion.
    If reprocess=True, also re-converts files that already exist in the DB.
    Returns a list of job IDs for status polling.
    """
    TEXTBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    processed_hashes = _get_processed_hashes() if not reprocess else set()
    import hashlib

    queued = []
    skipped = []

    for f in sorted(TEXTBOOKS_DIR.glob("*.docx")):
        file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
        if file_hash in processed_hashes:
            skipped.append(f.name)
            continue

        doc_id = str(uuid.uuid4())
        # Copy to data/input/ for audit trail
        input_dir = settings.DATA_DIR / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        dest = input_dir / f"{doc_id}_{f.name}"
        shutil.copy2(f, dest)

        ACTIVE_JOBS[doc_id] = {"status": "queued", "progress": 0, "error": None, "filename": f.name}
        background_tasks.add_task(run_ingestion_job, doc_id=doc_id, docx_path=dest)
        queued.append({"filename": f.name, "document_id": doc_id, "status_url": f"/api/documents/{doc_id}/status"})
        logger.info(f"BatchConvert: Queued '{f.name}' as job {doc_id}")

    return {
        "queued": queued,
        "skipped_already_processed": skipped,
        "message": f"{len(queued)} file(s) queued for conversion, {len(skipped)} skipped."
    }

@app.get("/api/textbooks/batch/status")
def batch_status():
    """Return status of all active and recent conversion jobs."""
    jobs = []
    for doc_id, job in ACTIVE_JOBS.items():
        jobs.append({
            "document_id": doc_id,
            "filename": job.get("filename", "unknown"),
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "error": job.get("error"),
            "download_url": f"/api/documents/{doc_id}/download" if job.get("status") == "completed" else None
        })
    return {"jobs": sorted(jobs, key=lambda j: j["status"])}
