from __future__ import annotations
import io
from sqlalchemy.orm import Session
from app.models.document import Document, Section
from app.epub.generator import MarkdownToHtmlConverter
from xhtml2pdf import pisa
import re

class PdfGenerator:
    """
    Independent compiler that consolidates database sections into a single HTML document,
    strips embedded answers to build a structured Answer Key appendix, checks for unsupported
    video media to output printable error banners, and compiles to PDF via xhtml2pdf.
    """
    def __init__(self, db: Session):
        self.db = db
        self.converter = MarkdownToHtmlConverter()

    def generate(self, document_id: str, dest_file_obj, user=None) -> bool:
        doc_record = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc_record:
            raise ValueError("Document not found")
            
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
            
        html_parts = []
        answers_by_section = {}
        
        # Add Title Page
        title_page = f"""
        <div class="title-page" style="text-align: center; padding-top: 150px; page-break-after: always;">
            <h1 style="font-size: 32pt; margin-bottom: 20px; color: #0f172a;">{doc_record.title}</h1>
            <p style="font-size: 16pt; color: #475569;">Author: {doc_record.author or "Unknown"}</p>
        </div>
        """
        html_parts.append(title_page)
        
        # Add Section Contents
        for sec in sections:
            if not sec.title:
                continue
                
            md_content = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown or ""
            
            if md_content:
                # Extract answers if present: <!-- ANSWER: B -->
                answers = re.findall(r'<!-- ANSWER:\s*(.*?)\s*-->', md_content)
                if answers:
                    answers_by_section[sec.title] = answers
                
                # Check for Video tags / urls (Print Error banner in PDF HTML)
                video_error_html = ""
                if "<video" in md_content or re.search(r'\.(mp4|webm|mov|ogg)\b', md_content, re.IGNORECASE):
                    video_error_html = """
                    <div style="border: 2px solid #ef4444; background-color: #fef2f2; color: #ef4444; padding: 12px; margin: 15px 0; font-weight: bold; border-radius: 4px; font-size: 10pt;">
                        [ERROR: Static PDF document cannot display interactive video media]
                    </div>
                    """
                
                # Strip answer tags from content body
                cleaned_md = re.sub(r'<!-- ANSWER:\s*(.*?)\s*-->', '', md_content)
                html_body = self.converter.convert(cleaned_md, convert_math=False)
                
                # Prepend video error if present
                if video_error_html:
                    html_body = video_error_html + html_body
            else:
                html_body = ""
            
            page_break_style = 'page-break-before: always;' if sec.level == 1 else ''
            
            # If the markdown content already starts with a heading, do not duplicate it
            has_heading = False
            if md_content:
                has_heading = md_content.strip().startswith("#")
                
            header_html = ""
            if not has_heading and sec.title:
                header_html = f'<h{sec.level} style="color: #0f172a;">{sec.title}</h{sec.level}>'
                
            section_html = f"""
            <div class="section-container" style="{page_break_style}">
                {header_html}
                {html_body}
            </div>
            """
            html_parts.append(section_html)
            
        # Add Answer Key Page at the end
        if answers_by_section:
            ans_parts = []
            for sec_title, ans_list in answers_by_section.items():
                list_items = "".join(f"<li>Q{i}. {ans}</li>" for i, ans in enumerate(ans_list, 1))
                ans_parts.append(f"""
                <h2 style="font-size: 14pt; margin-top: 1.5em; color: #1e293b;">{sec_title}</h2>
                <ul style="list-style-type: none; padding-left: 0;">
                    {list_items}
                </ul>
                """)
                
            ans_page = f"""
            <div class="section-container" style="page-break-before: always;">
                <h1 style="color: #0f172a;">Answer Key</h1>
                {"".join(ans_parts)}
            </div>
            """
            html_parts.append(ans_page)
            
        # Add layout and typography CSS styles
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page {{
                    size: A4;
                    margin: 2cm;
                }}
                body {{
                    font-family: Helvetica, Arial, sans-serif;
                    color: #333333;
                    line-height: 1.6;
                    font-size: 11pt;
                }}
                h1, h2, h3, h4, h5 {{
                    font-family: Helvetica, Arial, sans-serif;
                    font-weight: bold;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                }}
                h1 {{ font-size: 22pt; margin-top: 0; }}
                h2 {{ font-size: 16pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
                h3 {{ font-size: 13pt; color: #2563eb; }}
                p {{ margin-top: 0; margin-bottom: 1em; text-align: justify; }}
                ul, ol {{ margin-top: 0; margin-bottom: 1em; padding-left: 20px; }}
                li {{ margin-bottom: 0.5em; }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 1.5em;
                    margin-bottom: 1.5em;
                }}
                th, td {{
                    border: 1px solid #cbd5e1;
                    padding: 8px;
                    font-size: 10pt;
                    text-align: left;
                }}
                th {{
                    background-color: #f8fafc;
                    font-weight: bold;
                }}
                .callout {{
                    border-left: 4px solid #3b82f6;
                    background-color: #eff6ff;
                    padding: 12px;
                    margin-top: 1.5em;
                    margin-bottom: 1.5em;
                    border-radius: 4px;
                }}
            </style>
        </head>
        <body>
            {"".join(html_parts)}
        </body>
        </html>
        """
        
        # Convert HTML to PDF
        pisa_status = pisa.CreatePDF(full_html, dest=dest_file_obj)
        return not pisa_status.err
