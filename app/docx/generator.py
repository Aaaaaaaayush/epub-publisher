from __future__ import annotations
from pathlib import Path
from docx import Document as PyDocxDocument
from docx.shared import Inches, Pt, RGBColor
from sqlalchemy.orm import Session
from app.models.document import Document, Section
import re
import io
import requests

class DocxGenerator:
    """
    Independent compiler that packages structured database sections
    back into a professionally styled Word document (.docx) with dynamic Answer Key generation,
    image support, and video-compatibility checks.
    """
    def __init__(self, db: Session):
        self.db = db

    def generate(self, document_id: str, user=None) -> PyDocxDocument:
        doc_record = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc_record:
            raise ValueError("Document not found")
            
        doc = PyDocxDocument()
        
        # Add Title Page Content
        title_p = doc.add_paragraph()
        title_p.paragraph_format.space_before = Pt(100)
        title_p.paragraph_format.space_after = Pt(24)
        title_run = title_p.add_run(doc_record.title)
        title_run.bold = True
        title_run.font.size = Pt(28)
        title_p.alignment = 1  # Center
        
        if doc_record.author:
            author_p = doc.add_paragraph()
            author_run = author_p.add_run(f"Author: {doc_record.author}")
            author_run.font.size = Pt(14)
            author_p.alignment = 1  # Center
            
        doc.add_page_break()
        
        # Get all sections ordered by position
        sections = self.db.query(Section)\
            .filter(Section.document_id == document_id)\
            .order_by(Section.position)\
            .all()
            
        if user:
            def is_section_readable(u, d, s, db_session) -> bool:
                if u.is_admin or d.owner_id == u.id:
                    return True
                if not d.is_collaborative:
                    return d.owner_id == u.id
                from app.models.document import BookAccess, UserPermission
                has_access = db_session.query(BookAccess).filter(BookAccess.document_id == d.id, BookAccess.user_id == u.id).first() is not None
                if not has_access:
                    return False
                frontmatter_titles = ["Title Page", "Copyright", "About the Book", "About the Author", "Key Features", "Acknowledgement", "Course Outcomes", "Syllabus"]
                curr = s
                visited = set()
                while curr and curr.parent_id and curr.id not in visited:
                    visited.add(curr.id)
                    curr = db_session.query(Section).filter(Section.id == curr.parent_id).first()
                if not curr:
                    return False
                if curr.title in frontmatter_titles:
                    return True
                perm = db_session.query(UserPermission).filter(
                    (UserPermission.document_id == d.id) &
                    (UserPermission.section_id == curr.id) &
                    ((UserPermission.user_id == u.id) | (UserPermission.user_id == -1))
                ).first()
                return perm is not None
            sections = [sec for sec in sections if is_section_readable(user, doc_record, sec, self.db)]
            
        answers_by_section = {}
        
        for sec in sections:
            if not sec.title:
                continue
                
            # Add section title as heading
            h_level = min(max(sec.level, 1), 5)
            doc.add_heading(sec.title or "", level=h_level)
            
            md_content = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown or ""
            
            if md_content:
                # Extract answers if present: <!-- ANSWER: B -->
                answers = re.findall(r'<!-- ANSWER:\s*(.*?)\s*-->', md_content)
                if answers:
                    answers_by_section[sec.title] = answers
                
                # Strip answer tags from content body
                cleaned_md = re.sub(r'<!-- ANSWER:\s*(.*?)\s*-->', '', md_content)
                self._write_markdown_to_docx(doc, cleaned_md)
                
            doc.add_paragraph()  # Spacer
            
        # Append Answer Key Appendix at the end
        if answers_by_section:
            doc.add_page_break()
            doc.add_heading("Answer Key", level=1)
            for sec_title, ans_list in answers_by_section.items():
                doc.add_heading(sec_title, level=2)
                for idx, ans in enumerate(ans_list, 1):
                    doc.add_paragraph(f"Q{idx}. {ans}")
            
        return doc

    def _write_markdown_to_docx(self, doc, md_text: str):
        lines = md_text.split("\n")
        in_table = False
        table_rows = []
        
        for line in lines:
            line_strip = line.strip()
            
            # Check for Video tags / urls (Print Error)
            if "<video" in line_strip or re.search(r'\.(mp4|webm|mov|ogg)\b', line_strip, re.IGNORECASE):
                p = doc.add_paragraph()
                run = p.add_run("[ERROR: Static Word document cannot display interactive video media]")
                run.bold = True
                run.font.color.rgb = RGBColor(239, 68, 68)
                continue
            
            # Check for Image tags: ![Alt](url)
            m_img = re.match(r'^!\[(.*?)\]\((.*?)\)', line_strip)
            if m_img:
                self._add_image_to_docx(doc, m_img.group(2), m_img.group(1))
                continue
            
            # Table handling
            if line_strip.startswith("|"):
                in_table = True
                table_rows.append(line_strip)
                continue
            elif in_table:
                self._add_table(doc, table_rows)
                table_rows = []
                in_table = False
                if not line_strip:
                    continue
            
            # List item handling
            m_bullet = re.match(r'^[\*\-\+]\s+(.*)', line_strip)
            if m_bullet:
                p = doc.add_paragraph(style='List Bullet')
                self._add_formatted_text(p, m_bullet.group(1))
                continue
                
            m_num = re.match(r'^(\d+)\.\s+(.*)', line_strip)
            if m_num:
                p = doc.add_paragraph(style='List Number')
                self._add_formatted_text(p, m_num.group(2))
                continue
                
            # Blockquote
            if line_strip.startswith(">"):
                content = line_strip.lstrip(">").strip()
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(0.5)
                self._add_formatted_text(p, content)
                continue
                
            if re.match(r'^[\-\*_=]{3,}$', line_strip):
                continue
            if not line_strip:
                continue
                
            p = doc.add_paragraph()
            self._add_formatted_text(p, line_strip)

        if in_table and table_rows:
            self._add_table(doc, table_rows)

    def _add_image_to_docx(self, doc, img_path_or_url: str, alt_text: str):
        try:
            # Check if it is a web URL
            if img_path_or_url.startswith("http://") or img_path_or_url.startswith("https://"):
                response = requests.get(img_path_or_url, timeout=5)
                if response.status_code == 200:
                    image_stream = io.BytesIO(response.content)
                    doc.add_picture(image_stream, width=Inches(4.5))
                else:
                    raise Exception(f"HTTP status {response.status_code}")
            else:
                # Local file
                local_path = Path(img_path_or_url)
                if local_path.exists():
                    doc.add_picture(str(local_path), width=Inches(4.5))
                else:
                    # Try workspace relative
                    ws_path = Path("d:/agentic_workflow") / img_path_or_url
                    if ws_path.exists():
                        doc.add_picture(str(ws_path), width=Inches(4.5))
                    else:
                        raise FileNotFoundError(f"Local file not found: {img_path_or_url}")
        except Exception as e:
            p = doc.add_paragraph()
            run = p.add_run(f"[Warning: Image '{alt_text}' ({img_path_or_url}) could not be loaded: {str(e)}]")
            run.font.color.rgb = RGBColor(245, 158, 11)  # Orange warning

    def _add_formatted_text(self, p, text: str):
        tokens = re.split(r'(\*\*.*?\*\*|\*.*?\*)', text)
        for token in tokens:
            if token.startswith("**") and token.endswith("**"):
                run = p.add_run(token[2:-2])
                run.bold = True
            elif token.startswith("*") and token.endswith("*"):
                run = p.add_run(token[1:-1])
                run.italic = True
            else:
                p.add_run(token)

    def _add_table(self, doc, rows_text: list[str]):
        cleaned_rows = []
        for r in rows_text:
            cells = [c.strip() for c in r.split("|")[1:-1]]
            if all(re.match(r'^[\-:\s]+$', c) for c in cells):
                continue
            cleaned_rows.append(cells)
            
        if not cleaned_rows:
            return
            
        num_cols = max(len(row) for row in cleaned_rows)
        num_rows = len(cleaned_rows)
        
        table = doc.add_table(rows=num_rows, cols=num_cols)
        table.style = 'Table Grid'
        
        for r_idx, row in enumerate(cleaned_rows):
            for c_idx, val in enumerate(row):
                if c_idx < len(table.rows[r_idx].cells):
                    cell = table.cell(r_idx, c_idx)
                    cell.text = val
