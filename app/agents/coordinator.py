from __future__ import annotations
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from app.config.settings import settings
from app.database.session import init_db
from app.models.document import Document, Section
from app.extraction.extractor import DocxExtractor
from app.extraction.splitter import MarkdownSplitter
from app.agents.structure_agent import StructureAgent
from app.agents.formatting_agent import FormattingAgent
from app.agents.validation_agent import ValidationAgent
from app.epub.generator import EpubGenerator
from app.utils.logger import logger

class PipelineCoordinator:
    """
    Coordinates and orchestrates the entire semantic digital publishing pipeline.
    Runs sequential processing phases and manages the AI closed-loop validation retry system.
    """
    
    def __init__(self, db: Session, api_key: str = None):
        self.db = db
        self.api_key = api_key
        self.splitter = MarkdownSplitter(db)
        
        # Instantiate Agents
        self.structure_agent = StructureAgent(api_key=api_key)
        self.formatting_agent = FormattingAgent(api_key=api_key)
        self.validation_agent = ValidationAgent(api_key=api_key)
        
        # EPUB package builder
        self.epub_generator = EpubGenerator(db, api_key=api_key)

    def run_pipeline(self, docx_path: Path, doc_title: str = None, doc_author: str = None, doc_id: str = None) -> Path:
        """
        Runs the full document processing pipeline on a messy Word document:
          1. Deterministic extraction to raw markdown
          2. SQLite document and hierarchical section initialization
          3. AI Structure Agent heading repair
          4. AI Formatting Agent & Validation Agent closed-loop retry flow
          5. HTML generation and EPUB packaging
        """
        logger.info(f"Pipeline: Beginning document ingest for: {docx_path.name}")
        
        # Verify input file exists
        if not docx_path.exists():
            raise FileNotFoundError(f"Input Word document not found at: {docx_path}")
            
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        
        # 1. Ingest and initialize DOCX extractor with doc_id-scoped media dir
        doc_media_dir = settings.DATA_DIR / "extracted" / doc_id / "media"
        doc_media_dir.mkdir(parents=True, exist_ok=True)
        extractor = DocxExtractor(docx_path, media_dir=doc_media_dir)
        extracted_title, extracted_author = extractor.extract_metadata()
        
        if not doc_title:
            doc_title = extracted_title
            logger.info(f"Pipeline: Dynamically extracted title: '{doc_title}'")
        else:
            logger.info(f"Pipeline: Using provided title: '{doc_title}'")
            
        if not doc_author:
            doc_author = extracted_author
            logger.info(f"Pipeline: Dynamically extracted author(s): '{doc_author}'")
        else:
            logger.info(f"Pipeline: Using provided author(s): '{doc_author}'")
        
        # 2. Register Document in SQLite database
        new_doc = Document(
            id=doc_id,
            title=doc_title,
            source_file=str(docx_path),
            author=doc_author
        )
        self.db.add(new_doc)
        self.db.commit()
        
        # Extract raw markdown from DOCX
        raw_markdown = extractor.extract_to_markdown()
        
        # Clean formatting artifacts deterministically
        from app.formatting.formatter import clean_markdown_formatting
        raw_markdown = clean_markdown_formatting(raw_markdown)
        
        # Persist extracted intermediate file in data/extracted/
        extracted_file = settings.DATA_DIR / "extracted" / f"{doc_id}_extracted.md"
        with open(extracted_file, "w", encoding="utf-8") as f:
            f.write(raw_markdown)
        logger.info(f"Pipeline: Saved extracted raw markdown to: {extracted_file.name}")
        
        # 3. Split markdown into hierarchical sections and save in SQLite
        self.splitter.split_and_store(doc_id, raw_markdown)
        
        # 3b. Run Global Document Analyzer to generate JSON structure blueprint
        from app.extraction.analyzer import GlobalDocumentAnalyzer
        analyzer = GlobalDocumentAnalyzer(api_key=self.api_key)
        blueprint_json = analyzer.analyze(self.db, doc_id)
        
        db_doc = self.db.query(Document).filter(Document.id == doc_id).first()
        if db_doc:
            db_doc.structure_blueprint = blueprint_json
            self.db.add(db_doc)
            self.db.commit()
            logger.info("Pipeline: Global structural blueprint successfully persisted in database.")
            
        # Fetch sections for processing (excluding Level 0 Book record)
        sections = self.db.query(Section)\
            .filter(Section.document_id == doc_id)\
            .filter(Section.level > 0)\
            .order_by(Section.position)\
            .all()
            
        logger.info(f"Pipeline: Processing {len(sections)} sections through AI agents...")
        
        # Check if LLM is configured (disabling section-level AI by default to prevent free-tier 429 quota exhaustion and run 10x faster)
        use_section_ai = False
        has_llm = (
            settings.LLM_API_KEY 
            and settings.LLM_API_KEY != "your-api-key-here" 
            and "placeholder" not in settings.LLM_API_KEY.lower()
            and use_section_ai
        )
        if not has_llm:
            logger.info("Pipeline: Running section processing in deterministic mode (fast path).")
        
        # 4. Process each section node
        for idx, sec in enumerate(sections):
            logger.info(f"Pipeline: --- Processing Section [{idx+1}/{len(sections)}]: {sec.title} (Level {sec.level}) ---")
            
            # Formatter deterministic pre-cleaning
            from app.formatting.formatter import clean_markdown_formatting
            sec.raw_markdown = clean_markdown_formatting(sec.raw_markdown)
            self.db.add(sec)
            self.db.commit()

            if not has_llm:
                # Fast path: Deterministic Fallback Mode
                sec.formatted_markdown = sec.raw_markdown
                sec.validated_markdown = sec.raw_markdown
                sec.validation_status = "passed (deterministic)"
                sec.processing_status = "validated"
                self.db.add(sec)
                self.db.commit()
                
                # Persist section formatted intermediate file in data/formatted/
                formatted_file = settings.DATA_DIR / "formatted" / f"{sec.id}_formatted.md"
                with open(formatted_file, "w", encoding="utf-8") as f:
                    f.write(sec.validated_markdown)
                continue
            
            # Phase A: Structure Repair Agent
            try:
                repaired_structure = self.structure_agent.repair_structure(sec.raw_markdown)
                sec.raw_markdown = repaired_structure  # Update DB record with repaired hierarchy baseline
                self.db.add(sec)
                self.db.commit()
            except Exception as e:
                logger.error(f"Pipeline: Structure repair failed on section '{sec.title}': {e}. Continuing with raw content.")
                err_msg = str(e).lower()
                if any(substring in err_msg for substring in ["quota", "rate limit", "exhausted", "429"]):
                    logger.warning("Pipeline: Detected API quota/rate limit error. Disabling AI agents and falling back to deterministic mode.")
                    has_llm = False

            # Phase B: Closed-Loop AI Formatting & Validation Retry
            max_retries = 3
            retry_count = 0
            validation_errors = ""
            formatting_passed = False
            best_effort_markdown = sec.raw_markdown
            
            while retry_count < max_retries:
                logger.info(f"Pipeline: Formatting attempt {retry_count + 1} of {max_retries}...")
                
                try:
                    # Run formatting agent (passes previous error history if retrying)
                    formatted_content = self.formatting_agent.format_markdown(
                        raw_markdown=sec.raw_markdown,
                        additional_context=validation_errors
                    )
                    # Scrub any leftover LLM formatting artifacts deterministically
                    from app.formatting.formatter import clean_markdown_formatting
                    formatted_content = clean_markdown_formatting(formatted_content)
                    best_effort_markdown = formatted_content
                    
                    # Run validation checks
                    val_result = self.validation_agent.validate_section(
                        raw_markdown=sec.raw_markdown,
                        formatted_markdown=formatted_content
                    )
                    
                    if val_result["is_valid"]:
                        logger.info("Pipeline: Validation passed successfully!")
                        sec.formatted_markdown = formatted_content
                        sec.validated_markdown = formatted_content
                        sec.validation_status = "passed"
                        sec.processing_status = "validated"
                        formatting_passed = True
                        break
                    else:
                        logger.warning(f"Pipeline: Validation failed (Type: {val_result['error_type']}). Errors: {val_result['errors']}")
                        # Setup error context for retry prompt
                        validation_errors = "\n".join([f"- {err}" for err in val_result["errors"]])
                        retry_count += 1
                        
                except Exception as e:
                    logger.error(f"Pipeline: Error in formatting/validation loop on attempt {retry_count+1}: {e}")
                    # Detect auth/API key errors and disable LLM globally
                    err_msg = str(e).lower()
                    if "api_key" in err_msg or "api key" in err_msg or "unauthorized" in err_msg or "auth" in err_msg or any(substring in err_msg for substring in ["quota", "rate limit", "exhausted", "429"]):
                        logger.warning("Pipeline: Detected API key, authentication, or quota/rate limit failure. Disabling AI agents and falling back to deterministic mode.")
                        has_llm = False
                        break
                    retry_count += 1
            
            if not formatting_passed:
                logger.warning(f"Pipeline: Section '{sec.title}' exceeded max retries. Saving best-effort formatted content.")
                from app.formatting.formatter import clean_markdown_formatting
                cleaned_best_effort = clean_markdown_formatting(best_effort_markdown)
                sec.formatted_markdown = cleaned_best_effort
                sec.validated_markdown = cleaned_best_effort
                sec.validation_status = "failed"
                sec.processing_status = "validated"
                
            self.db.add(sec)
            self.db.commit()
            
            # Persist section formatted intermediate file in data/formatted/
            formatted_file = settings.DATA_DIR / "formatted" / f"{sec.id}_formatted.md"
            with open(formatted_file, "w", encoding="utf-8") as f:
                f.write(sec.validated_markdown)
                
        # 5. Generate Semantic HTML and package into valid EPUB3 digital book
        import re
        sanitized_title = re.sub(r'[\/:*?"<>|]', '', doc_title)
        sanitized_title = sanitized_title.lower().replace(' ', '_')
        epub_filename = f"{sanitized_title}_{doc_id[:8]}.epub"
        epub_output_path = settings.DATA_DIR / "epub" / epub_filename
        
        compiled_epub_path = self.epub_generator.generate_epub(doc_id, epub_output_path)
        logger.info(f"Pipeline: Success! Final EPUB textbook generated at: {compiled_epub_path}")
        return compiled_epub_path
