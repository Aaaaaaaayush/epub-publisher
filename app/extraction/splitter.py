import re
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.document import Document, Section
from app.utils.logger import logger

class MarkdownSplitter:
    """
    Splits raw document Markdown into hierarchical parent-child sections
    based on heading levels:
      #   -> Chapter (Level 1)
      ##  -> Topic (Level 2)
      ### -> Subtopic (Level 3)
    Persists the structured tree nodes in SQLite.
    """
    
    def __init__(self, db: Session):
        self.db = db

    def split_and_store(self, document_id: str, markdown_text: str) -> None:
        """
        Parses Markdown, splits it into structured nodes, assigns hierarchy levels,
        and saves them to the sections table in SQLite.
        """
        logger.info(f"Splitting document {document_id} into hierarchical sections...")
        
        # Verify document exists
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID {document_id} not found in database.")

        lines = markdown_text.split("\n")
        flat_sections = []
        
        # Capture any text prior to the first heading as "Introduction" or "Frontmatter"
        current_section = {
            "title": "Frontmatter",
            "level": 1,
            "section_type": "chapter",
            "lines": []
        }
        
        for line in lines:
            # Check for standard markdown headers
            match = re.match(r'^(#{1,6})\s+(.*)', line)
            if match and match.group(2).strip():
                # Save previous section if it has content
                if current_section["lines"] and any(l.strip() for l in current_section["lines"]):
                    flat_sections.append(current_section)
                
                hashes = match.group(1)
                level = len(hashes)
                title = match.group(2).strip()
                
                # Normalize types
                section_type = "chapter"
                if level == 2:
                    section_type = "topic"
                elif level >= 3:
                    section_type = "subtopic"
                    
                current_section = {
                    "title": title,
                    "level": level,
                    "section_type": section_type,
                    "lines": [line]
                }
            else:
                current_section["lines"].append(line)
                
        # Append the final section
        if current_section["lines"] and any(l.strip() for l in current_section["lines"]):
            flat_sections.append(current_section)

        # Clear existing sections for this document to allow rerunability/idempotency
        self.db.query(Section).filter(Section.document_id == document_id).delete()
        self.db.commit()

        # Insert Root Book/Document Section (Level 0)
        book_section_id = str(uuid.uuid4())
        book_section = Section(
            id=book_section_id,
            document_id=document_id,
            parent_id=None,
            section_type="book",
            level=0,
            position=0,
            title=doc.title,
            raw_markdown=markdown_text,
            formatted_markdown=None,
            validated_markdown=None,
            html_content=None,
            validation_status="pending",
            processing_status="split"
        )
        self.db.add(book_section)
        self.db.flush() # Flush to database to make available for relations

        # Stack to track the active parent ID at each level
        # Level 0 (Book) is the root parent
        active_parents = {0: book_section_id}
        
        position_counter = 1
        for sec in flat_sections:
            level = sec["level"]
            raw_md = "\n".join(sec["lines"]).strip()
            
            # If the raw markdown is empty, skip storing empty heading blocks
            if not raw_md:
                continue
                
            # Find parent_id by looking up the stack for L-1, L-2 etc.
            parent_id = None
            for p_level in range(level - 1, -1, -1):
                if p_level in active_parents:
                    parent_id = active_parents[p_level]
                    break
                    
            sec_id = str(uuid.uuid4())
            new_section = Section(
                id=sec_id,
                document_id=document_id,
                parent_id=parent_id,
                section_type=sec["section_type"],
                level=level,
                position=position_counter,
                title=sec["title"],
                raw_markdown=raw_md,
                formatted_markdown=None,
                validated_markdown=None,
                html_content=None,
                validation_status="pending",
                processing_status="split"
            )
            
            self.db.add(new_section)
            
            # Update parent tracking stack
            active_parents[level] = sec_id
            
            # Evict deeper levels from active stack
            levels_to_clear = [k for k in active_parents.keys() if k > level]
            for k in levels_to_clear:
                del active_parents[k]
                
            position_counter += 1
            
        self.db.commit()
        logger.info(f"Successfully stored {position_counter - 1} sections for document: {doc.title}")
