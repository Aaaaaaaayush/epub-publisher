import json
import re
from sqlalchemy.orm import Session
from app.agents.base import BaseAgent
from app.models.document import Section
from app.utils.logger import logger

from app.config.settings import settings

class GlobalDocumentAnalyzer(BaseAgent):
    """
    Agent responsible for analyzing the textbook's global structure and Syllabus/Contents
    to produce a structured JSON blueprint of modules, chapters, and appendixes.
    """
    
    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        # Use modular model set in settings
        self.model = settings.LLM_MODEL
        
    def analyze(self, db: Session, document_id: str) -> str:
        """
        Analyzes the SQLite database sections for a document and returns a JSON blueprint string.
        """
        logger.info(f"GlobalDocumentAnalyzer: Starting global analysis for document {document_id}...")
        
        # 1. Compile Heading Skeleton
        sections = db.query(Section)\
            .filter(Section.document_id == document_id)\
            .filter(Section.level > 0)\
            .order_by(Section.position)\
            .all()
            
        skeleton_lines = []
        syllabus_contents_list = []
        
        for sec in sections:
            hashes = "#" * sec.level
            skeleton_lines.append(f"{hashes} {sec.title} (Level {sec.level})")
            
            # Check if this section is Syllabus or TOC
            sec_title_lower = sec.title.lower() if sec.title else ""
            if any(kw in sec_title_lower for kw in ["syllabus", "contents", "table of contents", "course outcome"]):
                content = sec.raw_markdown or ""
                if content.strip():
                    syllabus_contents_list.append(f"### Section: {sec.title}\n{content}")
                    
        skeleton_text = "\n".join(skeleton_lines)
        syllabus_contents_text = "\n\n".join(syllabus_contents_list)
        
        # 2. Invoke LLM backend
        system_prompt = """You are an expert textbook publisher and editor.
Your task is to analyze the structure of the textbook based on its Heading Skeleton (all headings and their levels) and the full content of the Syllabus/Contents sections.

Based on this structural context, you must output a single, well-formed JSON object representing the Global Document Blueprint.
Do not output any markdown code blocks, backticks, comments, or intro/outro text. Output only the pure raw JSON string.

The JSON blueprint must strictly follow this schema:
{
  "modules": [
    {
      "module_number": 1,
      "module_title": "Module Title Here",
      "chapters": [
        {
          "chapter_number_in_module": 1,
          "chapter_title": "Chapter Title Here"
        }
      ]
    }
  ],
  "non_chapter_pages": [
    {
      "original_title": "Section Title Here",
      "desired_title": "DESIRED TITLE HERE",
      "type": "cheatsheet"
    }
  ]
}

Instructions:
1. Identify all modules and their respective chapters. Reset chapter numbers to start at 1 for each module.
2. Under "non_chapter_pages", identify any Level-1 headings that represent appendixes, cheatsheets, or general backmatter pages rather than real content chapters. Specify their original title, and under "desired_title" convert the title to UPPERCASE (e.g., "FORMAT FOR ACCOUNTING:") to match textbook backmatter capitalization conventions.
3. Do not include syllabus, copyright, author bio, or contents pages in "modules" or "non_chapter_pages".
"""

        user_content = f"""Here is the Heading Skeleton:
{skeleton_text}

Here is the content of Syllabus/Contents sections:
{syllabus_contents_text}
"""
        
        try:
            logger.info("GlobalDocumentAnalyzer: Querying Gemini API for global document blueprint...")
            response = self.generate_completion(system_prompt=system_prompt, user_content=user_content, temperature=0.1)
            
            # Clean LLM response to guarantee pure JSON
            cleaned_json = response.strip()
            if cleaned_json.startswith("```json"):
                cleaned_json = cleaned_json[7:]
            if cleaned_json.endswith("```"):
                cleaned_json = cleaned_json[:-3]
            cleaned_json = cleaned_json.strip()
            
            # Validate JSON parsing
            parsed = json.loads(cleaned_json)
            logger.info("GlobalDocumentAnalyzer: Successfully generated and verified global document blueprint.")
            return json.dumps(parsed, indent=2)
            
        except Exception as e:
            logger.error(f"GlobalDocumentAnalyzer: Failed to generate global document blueprint: {e}")
            # Return empty/default blueprint as safe fallback
            default_blueprint = {
                "modules": [],
                "non_chapter_pages": []
            }
            return json.dumps(default_blueprint)
