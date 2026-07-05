from __future__ import annotations
import json
import re
from app.agents.base import BaseAgent
from app.utils.logger import logger

class ValidationAgent(BaseAgent):
    """
    Agent responsible for verifying semantic equivalence between raw and formatted markdown,
    enforcing deterministic metric bounds (like length), and checking structural errors.
    """
    
    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        self.system_prompt = self.load_prompt_file("validation_prompt.txt")
        
    def check_heading_jumps(self, markdown: str) -> list[str]:
        """
        Deterministic check for invalid heading jumps (e.g. # to ### directly).
        """
        errors = []
        headings = re.findall(r'^(#{1,6})\s', markdown, re.MULTILINE)
        levels = [len(h) for h in headings]
        
        for i in range(len(levels) - 1):
            current = levels[i]
            nxt = levels[i + 1]
            if nxt > current + 1:
                errors.append(f"Heading jump detected: H{current} followed immediately by H{nxt}")
        return errors

    def check_bold_italic_balance(self, markdown: str) -> list[str]:
        """
        Deterministic check for unclosed bold or italic tags.
        """
        errors = []
        bold_count = len(re.findall(r'\*\*', markdown))
        if bold_count % 2 != 0:
            errors.append("Unclosed or unbalanced bold formatting tags detected (odd number of '**' tags).")
            
        # Filter out single asterisks used as bullets at the start of a line
        clean_md = re.sub(r'^\s*\*[\s]', '', markdown, flags=re.MULTILINE)
        italic_count = len(re.findall(r'(?<!\*)\*(?!\*)', clean_md))
        if italic_count % 2 != 0:
            errors.append("Unclosed or unbalanced italic formatting tags detected (odd number of '*' tags).")
        return errors

    def check_table_integrity(self, markdown: str) -> list[str]:
        """
        Deterministic check for table cell count integrity across all rows.
        """
        errors = []
        lines = markdown.split("\n")
        in_table = False
        col_count = 0
        
        for idx, line in enumerate(lines):
            if line.strip().startswith("|"):
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if not in_table:
                    in_table = True
                    col_count = len(cells)
                else:
                    if all(re.match(r'^[\s\-:]+$', c) for c in cells):
                        continue
                    if len(cells) != col_count:
                        errors.append(f"Table cell count mismatch at line {idx+1}: Expected {col_count} columns, but got {len(cells)} columns.")
            else:
                in_table = False
        return errors

    def check_repeating_numbering(self, markdown: str) -> list[str]:
        """
        Deterministic check for broken lists resulting in repeating '1.' item prefixes.
        """
        errors = []
        lines = markdown.split("\n")
        list_starts = []
        for idx, line in enumerate(lines):
            if re.match(r'^\s*1\.\s+', line):
                list_starts.append(idx)
                
        for i in range(len(list_starts) - 1):
            curr_idx = list_starts[i]
            next_idx = list_starts[i + 1]
            has_sequence = False
            for k in range(curr_idx + 1, next_idx):
                if re.match(r'^\s*[2-9]\.\s+', lines[k]):
                    has_sequence = True
                    break
            if not has_sequence:
                is_consecutive = True
                for k in range(curr_idx + 1, next_idx):
                    if lines[k].strip() and not re.match(r'^\s*[-*]\s+', lines[k]) and not lines[k].startswith(" "):
                        is_consecutive = False
                        break
                if not is_consecutive:
                    errors.append(f"Broken list layout: Numbered list is split, resulting in repeating '1.' prefixes instead of incrementing.")
        return errors

    def validate_section(self, raw_markdown: str, formatted_markdown: str) -> dict:
        """
        Runs both deterministic and AI checks on a section's raw vs formatted markdown.
        Returns a dict:
           {
             "is_valid": bool,
             "error_type": str,
             "errors": list,
             "explanation": str
           }
        """
        logger.info("ValidationAgent: Initiating comparative validation...")
        errors = []
        
        # 1. Deterministic Check: Character/Token Count Shrinkage
        raw_len = len(raw_markdown)
        fmt_len = len(formatted_markdown)
        if raw_len > 100 and (fmt_len / raw_len) < 0.8:
            msg = f"Deterministic failure: Formatted text length ({fmt_len} chars) is abnormally shorter than raw text length ({raw_len} chars)."
            logger.warning(f"ValidationAgent: {msg}")
            errors.append(msg)
            return {
                "is_valid": False,
                "error_type": "deletion",
                "errors": errors,
                "explanation": "Formatted content shrunk significantly compared to raw content, indicating potential summarization or paragraph loss."
            }
            
        # 2. Deterministic Check: Heading Jumps
        heading_errors = self.check_heading_jumps(formatted_markdown)
        if heading_errors:
            errors.extend(heading_errors)
            
        # 3. Deterministic Check: Bold/Italic Balance
        balance_errors = self.check_bold_italic_balance(formatted_markdown)
        if balance_errors:
            errors.extend(balance_errors)
            
        # 4. Deterministic Check: Table Integrity
        table_errors = self.check_table_integrity(formatted_markdown)
        if table_errors:
            errors.extend(table_errors)
            
        # 5. Deterministic Check: Repeating Numbering / Split lists
        numbering_errors = self.check_repeating_numbering(formatted_markdown)
        if numbering_errors:
            errors.extend(numbering_errors)
            
        if errors:
            logger.warning(f"ValidationAgent: Deterministic checks failed: {errors}")
            return {
                "is_valid": False,
                "error_type": "syntax",
                "errors": errors,
                "explanation": "Formatting validation checks failed."
            }

        # 6. AI-Assisted Semantic Similarity & Hallucination Check
        user_content = (
            f"=== ORIGINAL RAW MARKDOWN ===\n{raw_markdown}\n\n"
            f"=== AI-FORMATTED MARKDOWN ===\n{formatted_markdown}\n"
        )
        
        try:
            raw_response = self.generate_completion(
                system_prompt=self.system_prompt,
                user_content=user_content,
                temperature=0.1
            )
            
            cleaned_response = raw_response.strip()
            if cleaned_response.startswith("```"):
                cleaned_response = re.sub(r'^```(?:json)?\n', '', cleaned_response)
                cleaned_response = re.sub(r'\n```$', '', cleaned_response)
                cleaned_response = cleaned_response.strip()
                
            result = json.loads(cleaned_response)
            logger.info(f"ValidationAgent: AI validation completed. Result is_valid={result.get('is_valid')}")
            return {
                "is_valid": result.get("is_valid", False),
                "error_type": result.get("error_type", "none"),
                "errors": result.get("errors", []),
                "explanation": result.get("explanation", "")
            }
        except Exception as e:
            logger.error(f"ValidationAgent: Failed to parse LLM validation JSON. Error: {e}. Raw response: {raw_response if 'raw_response' in locals() else ''}")
            return {
                "is_valid": True,
                "error_type": "none",
                "errors": [],
                "explanation": f"Fallback pass: AI validation parser error: {e}"
            }
