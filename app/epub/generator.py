from __future__ import annotations
import uuid
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from ebooklib import epub
from sqlalchemy.orm import Session
from app.models.document import Document, Section
from app.utils.logger import logger
from app.config.settings import settings

class MarkdownToHtmlConverter:
    """
    Deterministic converter from Markdown to clean, semantic HTML.
    Uses markdown-it-py enabled with standard tables and hard line breaks support.
    """
    
    def __init__(self):
        # Initialize markdown-it-py and enable GFM-like tables, set breaks to True
        self.md = MarkdownIt("commonmark", {"breaks": True}).enable("table")
        
    def convert(self, markdown_text: str, convert_math: bool = True) -> str:
        if not markdown_text:
            return ""
            
        if convert_math:
            try:
                import latex2mathml.converter
                
                display_math_re = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
                inline_math_re = re.compile(r'(?<!\\)\$((?:[^\$\s])|(?:[^\$\s][^\$]*?[^\$\s]))(?<!\\)\$')
                
                def replace_display(match):
                    latex_str = match.group(1).strip()
                    if not latex_str:
                        return ""
                    latex_str = latex_str.replace('\\\\', '\\')
                    try:
                        mathml = latex2mathml.converter.convert(latex_str)
                        mathml = re.sub(r'<math[^>]*>', '<math display="inline" xmlns="http://www.w3.org/1998/Math/MathML" displaystyle="true">', mathml)
                        return f"\n<div class=\"math-display\">\n{mathml}\n</div>\n"
                    except Exception as e:
                        logger.error(f"latex2mathml failed on display math: {latex_str}. Error: {e}")
                        return match.group(0)
                        
                def replace_inline(match):
                    latex_str = match.group(1).strip()
                    if not latex_str:
                        return ""
                    latex_str = latex_str.replace('\\\\', '\\')
                    try:
                        mathml = latex2mathml.converter.convert(latex_str)
                        mathml = re.sub(r'<math[^>]*>', '<math display="inline" xmlns="http://www.w3.org/1998/Math/MathML" displaystyle="true">', mathml)
                        return mathml
                    except Exception as e:
                        logger.error(f"latex2mathml failed on inline math: {latex_str}. Error: {e}")
                        return match.group(0)
                        
                # Perform replacements
                markdown_text = display_math_re.sub(replace_display, markdown_text)
                markdown_text = inline_math_re.sub(replace_inline, markdown_text)
                
            except Exception as e:
                logger.error(f"Failed to run latex2mathml conversion: {e}")
                
        return self.md.render(markdown_text)



def is_exercise_title(title: str) -> bool:
    """
    Returns True if the section title looks like an exercise/question section.
    Covers patterns from all major Indian academic publishers.
    """
    t = title.lower().strip()
    # Exact keyword matches (substring)
    keywords = [
        # MCQ variants
        "multiple choice", "mcq", "choice question", "objective question",
        "objective type", "choose the correct", "choose correct", "select correct",
        "pick the correct", "choose the best",
        # True/False variants
        "true or false", "true/false", "state true", "state whether",
        "mark true", "write true",
        # Match variants
        "match the", "match following", "match column", "match the column",
        # Fill in the blanks variants
        "fill in the blank", "fill in blank", "fill in the blanks",
        "fill up", "fill the blank", "fill the blanks",
        # Short/Long answer
        "short answer", "short note", "short question",
        "brief answer", "brief question", "long answer", "long question",
        "descriptive question", "explain the following",
        # Review / Practice
        "review question", "practice question", "exercise", "exercises",
        "self test", "checkpoint", "activity", "assignment", "worksheet",
        "drill", "problems", "problem set",
        # Case study
        "case study", "case studies", "case analysis",
        # Misc exam types
        "quiz", "question paper", "sample paper", "model question",
        "examination question", "previous year", "past paper",
        # Generic question sections
        "practice questions", "question and answer", "q&a", "q & a",
    ]
    return any(kw in t for kw in keywords)


def parse_option_line(line):
    stripped = line.strip()
    
    # 1. Match alphabetical options: a), b., (c)
    alpha_match = re.match(r'^[*(\s]*([a-zA-Z])[\s*]*[).]+(.*)', stripped)
    if alpha_match:
        letter = alpha_match.group(1).lower()
        if letter == 'a' and stripped.lower().startswith(('answer', 'ans')):
            return None
        text = alpha_match.group(2).strip()
        text = re.sub(r'[*)]+$', '', text).strip()
        text = re.sub(r'^[*(\s]+', '', text).strip()
        text = text.replace('\\[', '[').replace('\\]', ']').replace('\\(', '(').replace('\\)', ')')
        return letter, text
        
    # 2. Match numerical options: 1., 2), (3)
    num_match = re.match(r'^[*(\s]*(\d+)[\s*]*[).]+(.*)', stripped)
    if num_match:
        val = int(num_match.group(1))
        if 1 <= val <= 8:
            letter = chr(ord('a') + val - 1)
            text = num_match.group(2).strip()
            text = re.sub(r'[*)]+$', '', text).strip()
            text = re.sub(r'^[*(\s]+', '', text).strip()
            text = text.replace('\\[', '[').replace('\\]', ']').replace('\\(', '(').replace('\\)', ')')
            return letter, text
            
    return None


def parse_mcq_markdown(text):
    # Preprocess same-line options to newlines
    text = re.sub(r'(\s|\\\]|\]|\))([a-hA-H])[\s]*[).]\s+', r'\1\n\2) ', text)
    
    questions = []
    lines = text.split('\n')
    current_q = None
    
    # Match standard question prefixes: 1. or (1) or 1)
    q_start_re = re.compile(r'^\s*(?:Q)?\(?(\d+)\)?[\s\.\)]+\s*(.*)', re.IGNORECASE)
    ans_re = re.compile(r'(?i)^\s*\*?\*?Ans(?:wer)?\b[*:\. \s-]*\(?([a-zA-Z0-9])\)?')
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        ans_match = ans_re.match(line_str)
        if ans_match and current_q:
            ans_val = ans_match.group(1).lower()
            if ans_val.isdigit():
                val = int(ans_val)
                if 1 <= val <= 8:
                    ans_val = chr(ord('a') + val - 1)
            current_q["answer"] = ans_val
            continue
            
        opt = parse_option_line(line_str)
        is_real_option = False
        if current_q and opt:
            opt_letter, opt_text = opt
            if line_str.lstrip('*( ').lower().startswith(('a', 'b', 'c', 'd', 'e', 'f', 'g', 'h')):
                is_real_option = True
            else:
                opt_num_match = re.match(r'^[*(\s]*(\d+)', line_str)
                if opt_num_match:
                    num_val = int(opt_num_match.group(1))
                    if num_val == len(current_q["options"]) + 1:
                        is_real_option = True
                        
        if is_real_option:
            current_q["options"].append(opt)
            continue
            
        q_match = q_start_re.match(line_str)
        if q_match:
            if current_q:
                questions.append(current_q)
            q_num = int(q_match.group(1))
            q_text = q_match.group(2).strip()
            q_text = q_text.replace('\\[', '[').replace('\\]', ']').replace('\\(', '(').replace('\\)', ')')
            current_q = {
                "number": q_num,
                "question": q_text,
                "options": [],
                "answer": None
            }
            continue
            
        if current_q and not current_q["options"] and current_q["answer"] is None:
            if not re.match(r'(?i)(?:answer|answers|answer\s+key)', line_str):
                line_clean = line_str.replace('\\[', '[').replace('\\]', ']').replace('\\(', '(').replace('\\)', ')')
                current_q["question"] += " " + line_clean
                
    if current_q:
        questions.append(current_q)
        
    # Extract grouped answers key if any questions have no answers
    grouped_answers = []
    comma_list_match = re.search(r'(?i)(?:answers|answer\s+key)\s*[:\-]\s*([a-zA-Z](?:\s*,\s*[a-zA-Z])*)', text)
    if comma_list_match:
        grouped_answers = [ans.strip().lower() for ans in comma_list_match.group(1).split(',')]
    else:
        key_matches = re.findall(r'(\d+)\s*[\s\-\–\—\.\:]+\s*([a-zA-Z])\b', text)
        if key_matches:
            sorted_keys = sorted(key_matches, key=lambda x: int(x[0]))
            grouped_answers_dict = {int(k): v.lower() for k, v in sorted_keys}
            if sorted_keys:
                max_q = max(grouped_answers_dict.keys())
                grouped_answers = [grouped_answers_dict.get(i, "a") for i in range(1, max_q + 1)]
                
    for idx, q in enumerate(questions):
        if not q["answer"]:
            if idx < len(grouped_answers):
                q["answer"] = grouped_answers[idx]
            else:
                q["answer"] = "a"
                
    return questions


def parse_tf_markdown(text):
    """
    Robustly parse True/False questions from HTML. Handles four formats:
      1. (N) Statement...  with grouped answer key at bottom
      2. N. Statement... with inline Answer: True/False
      3. Numbered list <li> with embedded <strong>Answer:</strong> True/False
      4. Grouped answer key in <pre><code> or plain text
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")

    questions = []
    # --- Format 3: <li> items with embedded Answer ---
    ol = soup.find("ol")
    if ol:
        for li in ol.find_all("li", recursive=False):
            li_text = li.get_text(" ", strip=True)
            # Try to extract inline answer
            ans = None
            ans_match = re.search(r'(?i)Answer\s*:\s*(True|False)', li_text)
            if ans_match:
                val = ans_match.group(1).lower()
                ans = "a" if val == "true" else "b"
            # Question text is everything before "Answer:"
            q_text = re.sub(r'(?i)\s*Answer\s*:.*', '', li_text).strip()
            if q_text:
                questions.append({
                    "number": len(questions) + 1,
                    "question": q_text,
                    "options": [("a", "True"), ("b", "False")],
                    "answer": ans or "a"
                })
        if questions:
            return questions

    # --- Format 1 & 2: Plain paragraph or numbered list from text ---
    # Get all visible text lines (strips HTML tags)
    all_text = soup.get_text("\n", strip=False)
    # Also grab text from <pre><code> blocks (answer key may be there due to indent)
    for code in soup.find_all(["pre", "code"]):
        all_text += "\n" + code.get_text("\n", strip=False)

    lines = all_text.split('\n')

    # Regex for question starters: "1." or "(1)" or "1)" style
    q_start_re = re.compile(r'^\s*(?:\((\d+)\)|(\d+)[.)]\s*)\s*(.*)')
    # Inline answer after question text: "Answer: True" or just "True" / "False"
    inline_ans_re = re.compile(r'(?i)\b(true|false)\b')
    ans_line_re = re.compile(r'(?i)^\s*(?:answer\s*[:\-]\s*)?(true|false)\s*$')

    current_q = None
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        # Skip heading lines
        if re.match(r'^#+\s', line_str) or re.match(r'(?i)^true\s+or\s+false', line_str):
            continue

        q_match = q_start_re.match(line_str)
        if q_match:
            # Save previous
            if current_q:
                questions.append(current_q)
            q_num = int(q_match.group(1) or q_match.group(2))
            q_text = q_match.group(3).strip()
            # Check if answer is on same line (e.g. Answer: True or just ... True at end of line)
            ans = None
            ans_inline_re = re.compile(r'(?i)\b(?:Answer\s*:\s*)?(True|False)\s*$')
            ans_inline = ans_inline_re.search(q_text)
            if ans_inline:
                val = ans_inline.group(1).lower()
                ans = "a" if val == "true" else "b"
                q_text = ans_inline_re.sub('', q_text).strip()
            current_q = {
                "number": q_num,
                "question": q_text,
                "options": [("a", "True"), ("b", "False")],
                "answer": ans
            }
            continue

        if current_q:
            # Check for standalone answer line
            ans_match = ans_line_re.match(line_str)
            if ans_match:
                val = ans_match.group(1).lower()
                current_q["answer"] = "a" if val == "true" else "b"
                continue
            # Skip lines that look like grouped answer keys (True - 2, 6, 8)
            if re.match(r'(?i)^(answer|true|false|answers)\b', line_str):
                continue
            # Skip lines that contain the grouped answer key pattern
            if re.search(r'(?i)(true|false)\s*[-–]\s*[\d,\s]+', line_str):
                continue
            # Continuation of question text
            current_q["question"] += " " + line_str

    if current_q:
        questions.append(current_q)

    # --- Extract grouped answer key (True - 2,6,8 / False - 1,3,5) ---
    clean_text = re.sub(r'<[^>]+>', ' ', text)  # strip HTML tags
    # Also check code blocks text
    for code in soup.find_all(["pre", "code"]):
        clean_text += " " + code.get_text(" ", strip=True)
    clean_text = re.sub(r'[*_]', '', clean_text)

    tf_match = re.search(
        r'(?i)true\s*[\-\–\—\.\:\s]+\s*([\d\s,]+)\s+false\s*[\-\–\—\.\:\s]+\s*([\d\s,]+)',
        clean_text
    )
    if tf_match:
        true_qs = [int(x.strip()) for x in re.findall(r'\d+', tf_match.group(1))]
        false_qs = [int(x.strip()) for x in re.findall(r'\d+', tf_match.group(2))]
        for q in questions:
            if not q["answer"]:
                if q["number"] in true_qs:
                    q["answer"] = "a"
                elif q["number"] in false_qs:
                    q["answer"] = "b"

    # Default unanswered to "a" (True)
    for q in questions:
        if not q["answer"]:
            q["answer"] = "a"
        # Strip any answer-key text that leaked into question text
        q["question"] = re.sub(r'(?i)\s*\*?\*?Answer\s*:.*', '', q["question"]).strip()
        q["question"] = re.sub(r'(?i)\s*(True|False)\s*[-–]\s*[\d,\s]+', '', q["question"]).strip()
        q["question"] = re.sub(r'\*+', '', q["question"]).strip()

    return questions


def parse_fitb_markdown(text):
    questions = []
    lines = text.split('\n')
    current_q = None
    
    q_start_re = re.compile(r'^\s*(?:Q)?(?:\((\d+)\)|(\d+)[.)]\s*)\s*(.*)')
    ans_comment_re = re.compile(r'(?i)<!--\s*ANSWER\s*:\s*(.*?)\s*-->')
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        q_match = q_start_re.match(line_str)
        if q_match:
            if current_q:
                questions.append(current_q)
            q_num = int(q_match.group(1) or q_match.group(2))
            q_text = q_match.group(3).strip()
            current_q = {
                "number": q_num,
                "question": q_text,
                "answer": None
            }
            continue
            
        ans_match = ans_comment_re.search(line_str)
        if ans_match and current_q:
            current_q["answer"] = ans_match.group(1).strip()
            continue
            
        if current_q and current_q["answer"] is None:
            ans_inline = ans_comment_re.search(line_str)
            if ans_inline:
                current_q["answer"] = ans_inline.group(1).strip()
                line_str = ans_comment_re.sub('', line_str).strip()
            if line_str:
                current_q["question"] += " " + line_str
                
    if current_q:
        questions.append(current_q)
        
    return questions


def parse_mtc_markdown(text):
    lines = text.split('\n')
    
    left_items = []
    right_items = []
    
    row_re = re.compile(r'^\s*(\d+)\.?\s*(.*?)\s*\|\s*([a-zA-Z])\.?\s*(.*)')
    ans_comment_re = re.compile(r'(?i)<!--\s*ANSWER\s*:\s*(.*?)\s*-->')
    
    mappings = {}
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
            
        row_match = row_re.match(line_str)
        if row_match:
            num = int(row_match.group(1))
            left_text = row_match.group(2).strip()
            letter = row_match.group(3).lower()
            right_text = row_match.group(4).strip()
            
            left_items.append((num, left_text))
            right_items.append((letter, right_text))
            continue
            
        ans_match = ans_comment_re.search(line_str)
        if ans_match:
            ans_str = ans_match.group(1).strip()
            pairs = re.findall(r'(\d+)\s*[\-\:]\s*([a-zA-Z])', ans_str)
            for num_str, let_str in pairs:
                mappings[int(num_str)] = let_str.lower()
                
    if not mappings:
        for idx, (num, _) in enumerate(left_items):
            letter = chr(ord('a') + idx)
            mappings[num] = letter
            
    left_options = []
    for num, text in left_items:
        left_options.append({
            "match_id": num,
            "text": text
        })
        
    right_options = []
    rev_mappings = {v: k for k, v in mappings.items()}
    for letter, text in right_items:
        match_id = rev_mappings.get(letter, 1)
        right_options.append({
            "match_id": match_id,
            "text": text
        })
        
    return {
        "left": left_options,
        "right": right_options
    }


def format_case_studies(text: str) -> str:
    lines = text.split('\n')
    case_study_header_pat = re.compile(r'^\s*#*\s*(?:CASE\s+STUDY|CASE)\s+(\d+)\s*[:\-]?\s*(.*)', re.IGNORECASE)
    
    cases = []
    current_case = None
    header_lines = []
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            if current_case:
                current_case["raw_lines"].append("")
            continue
            
        m = case_study_header_pat.match(line_str)
        if m:
            if current_case:
                cases.append(current_case)
            num = int(m.group(1))
            title = m.group(2).strip()
            current_case = {
                "number": num,
                "title": title,
                "raw_lines": [],
                "questions": [],
                "body_lines": []
            }
        else:
            if current_case:
                current_case["raw_lines"].append(line_str)
            else:
                is_skip = False
                if line_str.startswith("#"):
                    low_line = line_str.lower()
                    if "case" in low_line or "chapter" in low_line or "module" in low_line:
                        is_skip = True
                if not is_skip and not re.match(r'^\s*#+\s*case\s+stud(ies|y)\b', line_str, re.IGNORECASE):
                    header_lines.append(line_str)
                    
    if current_case:
        cases.append(current_case)
        
    md = MarkdownIt("commonmark", {"breaks": True}).enable("table")
    html_blocks = []
    
    if header_lines:
        header_text = "\n".join(header_lines).strip()
        if header_text:
            html_blocks.append(md.render(header_text))
            
    for c in cases:
        body_lines = []
        questions = []
        in_questions = False
        q_pat = re.compile(r'^\s*(\d+)[\s.)\-]+\s*(.*)')
        
        for line in c["raw_lines"]:
            line_str = line.strip()
            if not line_str:
                continue
            if re.match(r'^\s*[\s*]*Questions[\s*:]*$', line_str, re.IGNORECASE):
                in_questions = True
                continue
            q_match = q_pat.match(line_str)
            if q_match:
                questions.append(q_match.group(2).strip())
            else:
                if not in_questions:
                    body_lines.append(line)
                else:
                    body_lines.append(line)
                    
        body_markdown = "\n\n".join(body_lines).strip()
        case_title_html = f'<p class="subtopic_header">CASE STUDY {c["number"]}: {c["title"]}</p>'
        body_html = md.render(body_markdown).strip()
        
        case_html = '<div class="border_box">\n'
        case_html += case_title_html + '\n'
        case_html += body_html + '\n'
        
        if questions:
            case_html += '<p><strong>Questions:</strong></p>\n'
            case_html += '<ol style="list-style-type: decimal">\n'
            for q in questions:
                case_html += f'<li><span><p>{q}</p></span></li>\n'
            case_html += '</ol>\n'
            
        case_html += '</div>\n'
        html_blocks.append(case_html)
        
    return "\n".join(html_blocks)


class EpubGenerator:
    """
    Packages hierarchical database section records into standard reference-quality EPUB3 books.
    """
    
    def __init__(self, db: Session, api_key: str = None):
        self.db = db
        self.converter = MarkdownToHtmlConverter()
        self.api_key = api_key
        self.dynamic_images = []
        self.generated_css_classes = {}
        
    def _get_descendant_sections(self, parent_id: str) -> list[Section]:
        descendants = []
        children = self.db.query(Section)\
            .filter(Section.parent_id == parent_id)\
            .order_by(Section.position)\
            .all()
        for child in children:
            if child.level == 1:
                continue
            descendants.append(child)
            descendants.extend(self._get_descendant_sections(child.id))
        return descendants

    def clean_math_in_html(self, html: str) -> str:
        if not html:
            return ""
        # 1. Replace \times with ×
        html = html.replace("\\times", "×")
        # 2. Strip curly braces around words in math formulas
        html = re.sub(r"\{([a-zA-Z0-9\s%]+)\}", r"\1", html)
        # 3. Deduplicate the duplicated formula in example:
        pattern = r"Selling\s*Price\s*=\s*1000\s*\+\s*\(1000\s*×\s*0\.20\)\s*=\s*₹1\s*,\s*200\s*Selling\s*Price\s*=\s*1000\s*\+\s*\(1000\s*×\s*0\.20\)\s*=\s*₹1\s*,\s*200"
        html = re.sub(pattern, "Selling Price = 1000 + (1000 × 0.20) = ₹1,200", html, flags=re.IGNORECASE)
        # 4. Fix missing multiplication sign in the plain text formula:
        html = re.sub(r"Total\s+Cost\s+Profit\s+Margin\s*%", "Total Cost × Profit Margin %", html, flags=re.IGNORECASE)
        # 5. Standardize spaces around operators in math formulas
        html = re.sub(r"Total\s*Cost\s*\+\s*\(", "Total Cost + (", html, flags=re.IGNORECASE)
        html = re.sub(r"Selling\s*Price\s*=\s*", "Selling Price = ", html, flags=re.IGNORECASE)
        return html

    def post_process_html(self, html_content: str) -> str:
        if not html_content:
            return ""
        
        # Clean math equations first
        html_content = self.clean_math_in_html(html_content)
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Helper to parse inline styles into a dict
        def parse_inline_style(style_str):
            if not style_str:
                return {}
            styles = {}
            for item in style_str.split(";"):
                if ":" in item:
                    try:
                        k, v = item.split(":", 1)
                        styles[k.strip().lower()] = v.strip()
                    except Exception:
                        pass
            return styles

        # 0. Format inline bold paragraphs starting with letter prefixes (e.g., A., B., C.) as blue underlines
        for p in list(soup.find_all("p")):
            strong = p.find("strong", recursive=False)
            if strong and len(list(p.children)) == 1:
                strong_text = strong.get_text().strip()
                is_letter_heading = re.match(r'^[A-Z]\.\s+[A-Za-z]', strong_text)
                if is_letter_heading and len(strong_text) < 120:
                    p["class"] = "subtopic_header"
                    p.string = strong_text
                    
        # 1. Remove index table if any
        for table in list(soup.find_all("table")):
            th_texts = [cell.get_text().strip().lower() for cell in table.find_all(["th", "td"])]
            if any("page no" in txt or "page_no" in txt for txt in th_texts) and any("sr" in txt or "particulars" in txt for txt in th_texts):
                table.decompose()
                logger.info("EpubGenerator: Removed index table from HTML content.")
        
        # 2. Post-process single column tables into clean paragraphs
        for table in list(soup.find_all("table")):
            rows = table.find_all("tr")
            is_single_col = True
            for row in rows:
                cells = row.find_all(["th", "td"])
                if len(cells) > 1:
                    is_single_col = False
                    break
            if is_single_col and len(rows) > 0:
                div = soup.new_tag("div")
                for row in rows:
                    cells = row.find_all(["th", "td"])
                    for cell in cells:
                        children = list(cell.children)
                        if not children:
                            continue
                        has_block = any(getattr(c, 'name', None) in ['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'ul', 'ol'] for c in children)
                        if has_block:
                            for child in children:
                                div.append(child)
                        else:
                            p_tag = soup.new_tag("p")
                            for child in children:
                                p_tag.append(child)
                            if p_tag.get_text().strip():
                                div.append(p_tag)
                table.replace_with(div)
                logger.info("EpubGenerator: Replaced single-column layout table with paragraphs.")

        # 3. Table styling compilation & inline attribute stripping
        def compile_styles_to_class(tag, category):
            style_str = tag.get("style", "")
            styles = parse_inline_style(style_str)
            
            # Read presentation attributes
            if tag.get("bgcolor"):
                styles["background-color"] = tag.get("bgcolor")
            if tag.get("width"):
                styles["width"] = tag.get("width")
            if tag.get("height"):
                styles["height"] = tag.get("height")
            if tag.get("align"):
                styles["text-align"] = tag.get("align")
            if tag.get("valign"):
                styles["vertical-align"] = tag.get("valign")
            if tag.get("border"):
                styles["border"] = f"{tag.get('border')}px solid black"
                
            # Filter out font name/size and line spacing
            filtered_styles = {}
            for k, v in styles.items():
                if k not in ["font-family", "font-size", "line-height", "font-name", "line-spacing"]:
                    filtered_styles[k] = v
                    
            if not filtered_styles:
                return None
                
            sorted_style = tuple(sorted(filtered_styles.items()))
            
            # Check if this exact style combination already exists
            for cls_name, cls_style in self.generated_css_classes.items():
                if cls_style == sorted_style:
                    return cls_name
                    
            # Generate new class
            idx = len(self.generated_css_classes) + 1
            cls_name = f"epub-{category}-{idx}"
            self.generated_css_classes[cls_name] = sorted_style
            return cls_name

        for table in soup.find_all("table"):
            # Keep table custom classes (like tb-table-blue, table_)
            cls_list = table.get("class", [])
            if isinstance(cls_list, str):
                cls_list = [cls_list]
            tb_custom_classes = [c for c in cls_list if c.startswith("tb-table-")]
            
            cls_name = compile_styles_to_class(table, "table")
            table.attrs = {} # Strip all attributes
            
            new_classes = ["table_"]
            new_classes.extend(tb_custom_classes)
            if cls_name:
                new_classes.append(cls_name)
            table["class"] = new_classes
            
            rows = table.find_all("tr")
            for r_idx, row in enumerate(rows):
                cls_name = compile_styles_to_class(row, "row")
                row.attrs = {} # Strip all attributes
                if cls_name:
                    row["class"] = [cls_name]
                    
                cells = row.find_all(["th", "td"])
                for cell in cells:
                    cell_name = cell.name
                    cls_name = compile_styles_to_class(cell, "cell")
                    
                    # Keep original formatting classes (td_1, cell-blue, row-blue, row-alt-grey)
                    orig_cls = cell.get("class", [])
                    if isinstance(orig_cls, str):
                        orig_cls = [orig_cls]
                    keep_cls = [c for c in orig_cls if c.startswith("row-") or c.startswith("cell-") or c == "td_1"]
                    if r_idx == 0 and "td_1" not in keep_cls:
                        # Fallback for first row header highlight
                        keep_cls.append("td_1")
                    elif r_idx > 0 and "td_" not in keep_cls:
                        keep_cls.append("td_")
                        
                    cell.attrs = {} # Strip all attributes
                    cell.name = cell_name
                    
                    cell_classes = []
                    if cls_name:
                        cell_classes.append(cls_name)
                    cell_classes.extend(keep_cls)
                    if cell_classes:
                        cell["class"] = cell_classes

        # 4. Remove spans from table cells unless customized
        for table in soup.find_all("table"):
            for cell in table.find_all(["td", "th"]):
                for span in list(cell.find_all("span")):
                    has_custom_class = any(c for c in span.get("class", []) if c not in ["MsoNormal", "Apple-converted-space"])
                    style_str = span.get("style", "")
                    has_custom_style = False
                    if style_str:
                        styles = parse_inline_style(style_str)
                        custom_keys = [k for k in styles if k in ["color", "background-color", "border", "font-weight", "font-style", "text-decoration"]]
                        if custom_keys:
                            has_custom_style = True
                    if not has_custom_class and not has_custom_style:
                        span.unwrap()

        # 5. Clean style attributes from spans and list items, mapping customized properties to classes
        for tag in list(soup.find_all(["span", "li"])):
            style_str = tag.get("style", "")
            if style_str:
                styles = parse_inline_style(style_str)
                keep_styles = {}
                for k, v in styles.items():
                    if k in ["color", "background-color", "font-weight", "font-style", "text-decoration", "border"]:
                        keep_styles[k] = v
                
                # Delete style attribute
                if "style" in tag.attrs:
                    del tag.attrs["style"]
                
                if keep_styles:
                    sorted_style = tuple(sorted(keep_styles.items()))
                    cls_name = None
                    for name, cls_style in self.generated_css_classes.items():
                        if cls_style == sorted_style:
                            cls_name = name
                            break
                    if not cls_name:
                        idx = len(self.generated_css_classes) + 1
                        category = "span" if tag.name == "span" else "li"
                        cls_name = f"epub-{category}-{idx}"
                        self.generated_css_classes[cls_name] = sorted_style
                    
                    classes = tag.get("class", [])
                    if isinstance(classes, str):
                        classes = [classes]
                    if cls_name not in classes:
                        classes.append(cls_name)
                    tag["class"] = classes
            else:
                # Ensure no empty style attributes
                if "style" in tag.attrs:
                    del tag.attrs["style"]

        # 6. Extract raw base64 image data and update references
        for img in soup.find_all("img"):
            img["class"] = "img_class"
            if not img.get("alt"):
                img["alt"] = "image"
                
            src = img.get("src", "")
            if src.startswith("data:image/"):
                try:
                    header, base64_data = src.split(",", 1)
                    mime_type = header.split(";")[0].split(":")[1]
                    ext = ".png"
                    if "jpeg" in mime_type or "jpg" in mime_type:
                        ext = ".jpg"
                    elif "gif" in mime_type:
                        ext = ".gif"
                    
                    import base64
                    import hashlib
                    img_data = base64.b64decode(base64_data)
                    h = hashlib.md5(img_data).hexdigest()[:8]
                    filename = f"base64_img_{h}{ext}"
                    
                    # Store image bytes for registration in generator spine
                    self.dynamic_images.append((filename, img_data, mime_type))
                    img["src"] = f"images/{filename}"
                except Exception as e:
                    logger.error(f"EpubGenerator: Failed to extract base64 image: {e}")
            elif src.startswith("media/"):
                img["src"] = src.replace("media/", "images/")

        # 7. Smart post-process h3/h4 headers
        for h3 in list(soup.find_all("h3")):
            if not h3.get_text().strip():
                h3.decompose()
                continue
            if h3.find_parent(class_="question") or h3.find_parent(id="quiz"):
                continue
            
            h3_text = h3.get_text().strip()
            header_class = "topic_header"
            if re.match(r'^[A-Z]\b', h3_text):
                header_class = "subtopic_header"
            else:
                m = re.match(r'^(\d+(?:\.\d+)+)', h3_text)
                if m:
                    prefix = m.group(1)
                    dots_count = prefix.count('.')
                    if dots_count >= 2:
                        header_class = "subtopic_header"
            
            p = soup.new_tag("p", attrs={"class": header_class})
            p.extend(list(h3.children))
            h3.replace_with(p)

        for h4 in list(soup.find_all("h4")):
            if not h4.get_text().strip():
                h4.decompose()
                continue
            if h4.find_parent(class_="question") or h4.find_parent(id="quiz"):
                continue
            p = soup.new_tag("p", attrs={"class": "subtopic_header"})
            p.extend(list(h4.children))
            h4.replace_with(p)
            
        # 8. Identify formula paragraphs
        last_text = None
        for p in list(soup.find_all("p")):
            text = p.get_text().strip()
            is_formula = False
            if "selling price" in text.lower() and "=" in text and ("+" in text or "×" in text or "profit margin" in text):
                is_formula = True
                
            if is_formula:
                normalized_text = re.sub(r'\s+', ' ', text).strip()
                if normalized_text == last_text:
                    p.decompose()
                    continue
                last_text = normalized_text
                p["class"] = "formula"
                
        # 9. Post-process stray Q&A or metadata code blocks
        for pre in list(soup.find_all("pre")):
            code = pre.find("code")
            if code:
                text = code.get_text().strip()
                if "answer" in text.lower() or "q:" in text.lower() or re.match(r'^Q\d+', text) or len(text.split('\n')) <= 3:
                    div = soup.new_tag("div")
                    for line in text.split('\n'):
                        p_tag = soup.new_tag("p")
                        p_tag.string = line.strip()
                        div.append(p_tag)
                    pre.replace_with(div)
                    logger.info("EpubGenerator: Replaced stray code block with clean paragraphs.")

        # 10. Unwrap spans that contain <br> tags to make splitting paragraphs easy
        for span in list(soup.find_all("span")):
            if span.find("br"):
                span.unwrap()

        # 11. Replace line breaks '<br/>' with </p><p> tags safely inside <p> elements
        for p in list(soup.find_all("p")):
            if p.find("br") and p.parent:
                current_p = soup.new_tag("p")
                if p.get("class"):
                    current_p["class"] = p["class"]
                for child in list(p.contents):
                    if child.name == "br":
                        p.insert_before(current_p)
                        current_p = soup.new_tag("p")
                        if p.get("class"):
                            current_p["class"] = p["class"]
                    else:
                        current_p.append(child)
                p.insert_before(current_p)
                p.decompose()

        # 12. Enforce list items content inside a paragraph
        for li in list(soup.find_all("li")):
            for inner_p in list(li.find_all("p")):
                inner_p.unwrap()
                
            nested_lists = []
            for sub_list in list(li.find_all(["ul", "ol"], recursive=False)):
                sub_list.extract()
                nested_lists.append(sub_list)
                
            contents = list(li.contents)
            if contents:
                has_visible_content = any(not isinstance(c, str) or c.strip() for c in contents)
                if has_visible_content:
                    p_tag = soup.new_tag("p")
                    li.clear()
                    li.append(p_tag)
                    p_tag.extend(contents)
            
            for nl in nested_lists:
                li.append(nl)
                
        return str(soup)

    def compile_section_html(self, sec: Section, module_num: int, doc_title: str, doc_author: str, ch_num: str = None) -> str:
        title = sec.title
        title_lower = title.lower()
        
        is_mcq = "mcq" in title_lower or "choice question" in title_lower or "true or false" in title_lower or "true/false" in title_lower
        is_cs = "case studies" in title_lower or "case study" in title_lower
        is_frontmatter = any(x in title_lower for x in ["about author", "about the book", "about book", "acknowledg", "syllabus", "copyright", "contents", "author"])
        
        # Check if this section is a generic exercise (excluding frontmatter and case studies)
        exercise_keywords = ["match the", "match following", "quiz", "questions", "sample question paper", "fill in the blank", "fill in blank", "fill in the blanks"]
        is_exercise = (is_mcq or any(kw in title_lower for kw in exercise_keywords)) and not is_frontmatter and not is_cs
        
        combined_md = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown or ""
        descendants = self._get_descendant_sections(sec.id)
        for d in descendants:
            d_md = d.validated_markdown or d.formatted_markdown or d.raw_markdown or ""
            if d_md:
                combined_md += "\n\n" + d_md
                
        if is_mcq:
            # Detect actual True/False questions dynamically based on content context
            is_tf = "true or false" in title_lower or "true/false" in title_lower
            if not is_tf:
                # If title says MCQ but content has no option prefixes like a) b) c) d) and contains True/False
                has_mcq_options = re.search(r'(?m)^[ \t]*[a-dA-D][\s).]+', combined_md)
                if not has_mcq_options and re.search(r'(?i)\b(true|false)\b', combined_md):
                    is_tf = True
                    logger.info(f"EpubGenerator: Dynamically detected True/False questions in section '{title}'")
            
            if is_tf:
                questions = parse_tf_markdown(combined_md)
                # If we dynamically detected it as True/False, let's update title for the yellow banner
                if not ("true or false" in title_lower or "true/false" in title_lower):
                    title = "True or False"
            else:
                questions = parse_mcq_markdown(combined_md)
                
            q_blocks = []
            answers_dict = {}
            for idx, q in enumerate(questions, 1):
                q_num = str(idx)
                answers_dict[q_num] = q["answer"] or "a"
                
                # Render question text using markdown inline
                q_text_html = self.converter.md.renderInline(q["question"]).strip()
                
                options_html = []
                for opt in q["options"]:
                    opt_letter, opt_text = opt
                    # Render option text using markdown inline
                    opt_text_html = self.converter.md.renderInline(opt_text).strip()
                    # Add img_class to image elements
                    opt_text_html = opt_text_html.replace('<img src="media/', '<img class="img_class" src="media/')
                    options_html.append(f"""        <input type="radio" name="q{q_num}" value="{opt_letter}" onchange="highlightCorrectAnswer(this)"/>
        <label>{opt_text_html}</label><br/>""")
                options_str = "\n".join(options_html)
                
                q_blocks.append(f"""    <div class="question" data-questionNumber="{q_num}">
        <h3>Question {q_num}</h3>
        <p>{q_text_html}</p>
{options_str}
        <p class="answer" id="answer{q_num}"></p>
    </div>""")
            
            q_blocks_str = "\n".join(q_blocks)
            answers_json = json.dumps(answers_dict)
            
            header_text = title.strip().upper()
            html_body = f"""<p>&#160;</p>
<p class="exercise_header_yellow">{header_text}</p>
<p></p>
<div id="quiz">
{q_blocks_str}
</div>
<script type="text/javascript">
    var correctAnswers = {answers_json};

    function highlightCorrectAnswer(selected) {{
        var questionDiv = selected.closest('.question');
        if (!questionDiv) return;
        
        var qNumber = questionDiv.getAttribute('data-questionNumber') || questionDiv.getAttribute('data-questionnumber');
        var feedback = questionDiv.querySelector('.answer');
        
        if (!feedback) {{
            console.error('Feedback element not found!');
            return;
        }}
        
        if (selected.value === correctAnswers[qNumber]) {{
            feedback.textContent = "Correct!";
            feedback.className = 'answer correct';
            var inputs = questionDiv.querySelectorAll('input');
            inputs.forEach(function(input) {{
                input.disabled = true;
            }});
        }} else {{
            feedback.textContent = "Incorrect!";
            feedback.className = 'answer incorrect';
        }}
    }}
</script>"""
            
        elif is_exercise and sec.level == 1:
            is_fib = "fill in the blank" in title_lower or "fill in blank" in title_lower or "fill in the blanks" in title_lower
            is_mtc = "match the" in title_lower or "match column" in title_lower or "match following" in title_lower
            if is_fib:
                questions = parse_fitb_markdown(combined_md)
                q_blocks = []
                for q in questions:
                    q_num = q["number"]
                    correct_ans = q["answer"] or ""
                    
                    raw_q_html = self.converter.md.renderInline(q["question"]).strip()
                    blank_input = f'<input type="text" id="blank{q_num}-0" class="blank" placeholder="Answer {q_num}" />'
                    q_text_html = re.sub(r'_{3,}', blank_input, raw_q_html, count=1)
                    if blank_input not in q_text_html:
                        q_text_html += " " + blank_input
                        
                    q_blocks.append(f"""    <div class="question">
        <h3>Question {q_num}</h3>
        <p>{q_text_html}</p>
        <p id="feedback{q_num}-0" class="feedback" data-correct="{correct_ans}"></p>
    </div>""")
                q_blocks_str = "\n".join(q_blocks)
                
                header_text = title.strip()
                html_body = f"""<style>
        .feedback {{ margin-top: 10px; min-height: 20px; }}
        .feedback-correct {{ color: green; }}
        .feedback-incorrect {{ color: red; }}
        .feedback-answer {{ color: blue; }}
        .controls {{ margin: 20px 0; }}
        .blank {{ margin: 5px; }}
        .blank:focus {{
            border-color: #007BFF;
            outline: none;
            background-color: #f0f8ff;
        }}
        .question {{ margin-bottom: 10px; padding: 15px; border: 1px solid #ddd; }}
</style>
<p>&#160;</p>
<p class="topic_header">{header_text}</p>
<p></p>
<div id="questionsContainer">
{q_blocks_str}
</div>
<p>&#160;</p>
<div class="controls" style="text-align:center;">
    <button onclick="showCorrectAnswers()">Show Answers</button>
</div>
<script type="text/javascript">
    function validateAnswer(questionIndex, blankIndex) {{
        var input = document.getElementById('blank' + questionIndex + '-' + blankIndex);
        var feedback = document.getElementById('feedback' + questionIndex + '-' + blankIndex);
        if (!input || !feedback) return;
        var correctAnswer = feedback.getAttribute('data-correct').toLowerCase().trim();
        var userAnswer = input.value.toLowerCase().trim();

        if (userAnswer === correctAnswer) {{
            feedback.textContent = 'Correct!';
            feedback.className = 'feedback feedback-correct';
        }} else {{
            feedback.textContent = 'Incorrect. Try again.';
            feedback.className = 'feedback feedback-incorrect';
        }}
    }}

    function showCorrectAnswers() {{
        var feedbacks = document.querySelectorAll('.feedback');
        feedbacks.forEach(function(feedback) {{
            var correct = feedback.getAttribute('data-correct');
            feedback.textContent = 'Correct answer: ' + correct;
            feedback.className = 'feedback feedback-answer';
        }});
    }}

    // Initialize validation for all inputs
    document.querySelectorAll('input[type="text"]').forEach(function(input) {{
        var idParts = input.id.replace('blank', '').split('-');
        if (idParts.length === 2) {{
            var qIndex = idParts[0];
            var bIndex = idParts[1];
            input.onblur = function() {{ validateAnswer(qIndex, bIndex); }};
        }}
    }});
</script>"""
            elif is_mtc:
                mtc_data = parse_mtc_markdown(combined_md)
                left_html = []
                for item in mtc_data["left"]:
                    left_html.append(f'  <div class="option" data-match="{item["match_id"]}">{item["text"]}</div>')
                left_str = "\n".join(left_html)
                
                right_html = []
                for item in mtc_data["right"]:
                    right_html.append(f'  <div class="option" data-match="{item["match_id"]}">{item["text"]}</div>')
                right_str = "\n".join(right_html)
                
                header_text = title.strip()
                html_body = f"""<style>
        .quiz-container {{ display:flex; justify-content:space-between; padding:20px; max-width:100%; margin:30px auto; background:#ffffff; border-radius:12px; border:1px solid #ddd; overflow:hidden; }}
        .column {{ width:45%; }}
        .option {{ padding:15px; margin:25px 0; border:2px solid #0288d1; border-radius:12px; background:#ffffff; cursor:pointer; user-select:none; transition:background-color .3s, transform .3s, box-shadow .3s; font-weight:600; text-align:center; box-shadow:0 4px 8px rgba(0,0,0,0.1); }}
        .option:hover {{ background:#e1f5fe; transform:scale(1.02); }}
        .option.selected {{ background:#0288d1; color:#fff; }}
        .option.matched {{ background:#4caf50; color:#fff; cursor:default; pointer-events:none; }}
        .feedback {{ margin-top:20px; font-weight:700; text-align:center; color:#d32f2f; min-height: 20px; }}
</style>
<p>&#160;</p>
<p class="topic_header">{header_text}</p>
<p id="feedback" class="feedback"></p>
<div class="quiz-container">
    <div class="column" id="left-column">
        <p style="text-align:center;"><b>Group A</b></p>
{left_str}
    </div>
    <div class="column" id="right-column">
        <p style="text-align:center;"><b>Group B</b></p>
{right_str}
    </div>
</div>
<script type="text/javascript">
document.addEventListener('DOMContentLoaded', function() {{
    var selectedOption = null;
    var feedbackElement = document.getElementById('feedback');
    
    function showFeedback(message, success) {{
        feedbackElement.textContent = message;
        feedbackElement.style.color = success ? '#388e3c' : '#d32f2f';
    }}

    function handleOptionClick(event) {{
        var clickedOption = event.target;
        if (!clickedOption.classList.contains('option') || clickedOption.classList.contains('matched')) return;
        
        if (selectedOption) {{
            if (selectedOption !== clickedOption) {{
                var parent1 = selectedOption.closest('.column');
                var parent2 = clickedOption.closest('.column');
                if (parent1 === parent2) {{
                    selectedOption.classList.remove('selected');
                    selectedOption = clickedOption;
                    selectedOption.classList.add('selected');
                    return;
                }}
                
                if (selectedOption.getAttribute('data-match') === clickedOption.getAttribute('data-match')) {{
                    selectedOption.classList.add('matched');
                    clickedOption.classList.add('matched');
                    selectedOption.classList.remove('selected');
                    selectedOption = null;
                    showFeedback('Correct match!', true);
                }} else {{
                    selectedOption.classList.remove('selected');
                    clickedOption.classList.remove('selected');
                    selectedOption = null;
                    showFeedback('Wrong match. Please try again!', false);
                }}
            }}
        }} else {{
            selectedOption = clickedOption;
            selectedOption.classList.add('selected');
            showFeedback('', false);
        }}
    }}

    document.querySelectorAll('.column').forEach(function(c) {{
        c.addEventListener('click', handleOptionClick);
    }});
}});
</script>"""
            else:
                raw_html = self.converter.convert(combined_md)
                soup = BeautifulSoup(raw_html, "html.parser")
                first_h = soup.find(["h1", "h2", "h3", "h4", "h5", "h6"])
                if first_h:
                    first_h.decompose()
                body_contents = soup.decode_contents().strip()
                
                header_text = title.strip().upper()
                html_body = f"""<p>&#160;</p>
<p class="exercise_header_yellow">{header_text}</p>
{body_contents}"""
            
        elif is_cs:
            html_body = format_case_studies(combined_md)
            
        elif is_frontmatter and "syllabus" in title_lower:
            html_body = f"""<div class="rounded_div">
    <p class="syllabus_header">F. Y.</p>
    <p class="level_1">&#160;</p>
    <p class="syllabus_header">Semester - 1</p>
    <p class="level_1">&#160;</p>
    <p class="syllabus_header">{doc_title}</p>
    <p class="level_1">&#160;</p>
    <p class="syllabus_header">Open Elective</p>
    <p class="level_1">&#160;</p>
    <p class="syllabus_header">2 Credits</p>
    <p class="level_1">&#160;</p>
    <p class="syllabus_header">{doc_author}</p>
</div>
<p class="level_1">&#160;</p>"""
            desc_raw_html = self.converter.convert("\n\n".join([d.validated_markdown or d.formatted_markdown or d.raw_markdown or "" for d in descendants]))
            html_body += desc_raw_html

        elif is_frontmatter:
            if "author" in title_lower:
                raw_html = self.converter.convert(combined_md)
                soup = BeautifulSoup(raw_html, "html.parser")
                for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                    h.decompose()
                    break
                body_contents = soup.decode_contents().strip()
                soup_author = BeautifulSoup(body_contents, "html.parser")
                children = list(soup_author.children)
                
                authors = []
                current_author = None
                in_bio_section = False
                current_bio_author = None
                title_prefixes = ("mr", "mrs", "dr", "prof", "ms")
                
                for child in children:
                    child_str = str(child).strip()
                    if not child_str:
                        continue
                        
                    child_text = child.get_text().strip()
                    child_text_lower = child_text.lower()
                    
                    if "author" in child_text_lower and "profile" in child_text_lower:
                        in_bio_section = True
                        continue
                        
                    if not in_bio_section:
                        is_new_name = False
                        if child.name == 'p':
                            clean_text_for_prefix = child_text_lower.replace(".", "").strip()
                            starts_with_prefix = clean_text_for_prefix.startswith(title_prefixes) or (
                                child.find("strong") and 
                                child.find("strong").get_text().lower().replace(".", "").strip().startswith(title_prefixes)
                            )
                            if starts_with_prefix:
                                is_new_name = True
                                
                        if is_new_name:
                            name_clean = child_text
                            clean_lower_name = name_clean.lower().replace(".", "").strip()
                            for prefix in title_prefixes:
                                if clean_lower_name.startswith(prefix):
                                    name_clean = name_clean[len(prefix):].strip()
                                    if name_clean.startswith("."):
                                        name_clean = name_clean[1:].strip()
                                    break
                            norm_key = re.sub(r'[^a-z0-9]', '', name_clean.lower())
                            current_author = {
                                "full_name": child_text,
                                "norm_key": norm_key,
                                "qualifications": [],
                                "bio": []
                            }
                            authors.append(current_author)
                        elif current_author:
                            current_author["qualifications"].append(child_str)
                    else:
                        matched = False
                        for auth in authors:
                            if auth["norm_key"] in re.sub(r'[^a-z0-9]', '', child_text_lower)[:len(auth["norm_key"])+10]:
                                auth["bio"].append(child_str)
                                current_bio_author = auth
                                matched = True
                                break
                        if not matched:
                            if current_bio_author:
                                current_bio_author["bio"].append(child_str)
                            elif authors:
                                authors[-1]["bio"].append(child_str)
                            
                formatted_blocks = []
                for auth in authors:
                    quals_html = "\n".join(auth["qualifications"])
                    bio_html = "\n".join(auth["bio"])
                    divider = '<hr style="border: 1px dashed #3579D5; margin: 15px 0;"/>' if bio_html else ''
                    formatted_blocks.append(f"""<div class="rounded_div">
    <p class="syllabus_header">{auth['full_name']}</p>
    <br/>
    {quals_html}
    {divider}
    {bio_html}
</div>""")
                if formatted_blocks:
                    html_body = "\n<p class=\"level_1\">&#160;</p>\n".join(formatted_blocks)
                else:
                    html_body = f"""<div class="rounded_div">
    <p class="syllabus_header">{title}</p>
    {body_contents}
</div>"""
            else:
                # For non-author frontmatter, render parent and each descendant section in its own rounded_div card
                blocks = []
                
                # 1. Parent section block
                parent_md = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown or ""
                parent_raw_html = self.converter.convert(parent_md)
                soup_parent = BeautifulSoup(parent_raw_html, "html.parser")
                
                parent_heading = title
                for h in soup_parent.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                    parent_heading = h.get_text()
                    h.decompose()
                    break
                parent_body = soup_parent.decode_contents().strip()
                if parent_body:
                    blocks.append(f"""<div class="rounded_div">
    <p class="syllabus_header">{parent_heading}</p>
    {parent_body}
</div>""")
                
                # 2. Descendant section blocks
                descendants = self._get_descendant_sections(sec.id)
                for d in descendants:
                    d_md = d.validated_markdown or d.formatted_markdown or d.raw_markdown or ""
                    if d_md:
                        d_raw_html = self.converter.convert(d_md)
                        soup_d = BeautifulSoup(d_raw_html, "html.parser")
                        
                        d_heading = d.title
                        for h in soup_d.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                            d_heading = h.get_text()
                            h.decompose()
                            break
                        d_body = soup_d.decode_contents().strip()
                        if d_body:
                            blocks.append(f"""<div class="rounded_div">
    <p class="syllabus_header">{d_heading}</p>
    {d_body}
</div>""")
                
                if blocks:
                    html_body = "\n<p class=\"level_1\">&#160;</p>\n".join(blocks)
                else:
                    html_body = ""
            
        else:
            raw_html = self.converter.convert(combined_md)
            soup = BeautifulSoup(raw_html, "html.parser")
            first_h = soup.find(["h1", "h2"])
            if ch_num:
                if first_h:
                    first_h.decompose()
            else:
                if first_h:
                    first_h.string = title
            html_body = str(soup)
            
        html_body = self.post_process_html(html_body)
        
        if is_frontmatter:
            html_body += '\n<p class="level_1">&#160;</p>\n<p class="chapter_end">**************************</p>\n<p class="level_1">&#160;</p>'
        elif is_mcq or is_exercise:
            html_body += '\n<p class="level_1">&#160;</p>\n<p class="chapter_end">**************************</p>\n<p class="level_1">&#160;</p>'
        elif is_cs:
            header_table = f"""<p>&#160;</p>
<table class="exercise_header_grey">
  <tbody>
    <tr>
      <td class="left">Module {module_num}</td>
      <td class="center">Case Studies</td>
    </tr>
  </tbody>
</table>
<p>&#160;</p>"""
            html_body = header_table + "\n" + html_body
            html_body += '\n<p class="level_1">&#160;</p>\n<p class="chapter_end">**************************</p>\n<p class="level_1">&#160;</p>'
        else:
            if ch_num:
                clean_title = re.sub(r'(?i)^(?:chapter|unit|module)\s*\d+\s*[:\-]?\s*', '', title).strip()
                header_table = f"""<p>&#160;</p>
<table class="chapter_header" id="chapter">
  <tbody>
    <tr>
      <td class="td_unit_no"><p class="unit_no_text"><b>Module {module_num}</b></p></td>
      <td class="td_unit_no"><p class="unit_no_text"><b>Chapter {ch_num} </b></p></td>
    </tr>
    <tr>
      <td class="td_chap_name" colspan="2"><p class="chap_name"> {clean_title}</p></td>
    </tr>
  </tbody>
</table>"""
                html_body = header_table + "\n" + html_body
            html_body += '\n<p class="level_1">&#160;</p>\n<p class="chapter_end">**************************</p>\n<p class="level_1">&#160;</p>'
            
        return html_body

    def generate_epub(self, document_id: str, output_path: Path) -> Path:
        """
        Retrieves sections of the document, compiles XHTML chapters, creates
        a structured TOC, links stylesheet, and packages the final .epub.
        """
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document with ID {document_id} not found.")
            
        logger.info(f"EpubGenerator: Compiling EPUB for document: {doc.title} at {output_path}")
        
        # Load global structure blueprint from Document model if available
        import json
        blueprint = {}
        if doc.structure_blueprint:
            try:
                blueprint = json.loads(doc.structure_blueprint)
                logger.info("EpubGenerator: Loaded global structure blueprint from database.")
            except Exception as e:
                logger.error(f"EpubGenerator: Failed to parse structure blueprint JSON: {e}")
        
        # 1. Create EbookLib EpubBook object
        book = epub.EpubBook()
        book.set_identifier(f"urn:uuid:{doc.id}")
        book.set_title(doc.title)
        book.set_language("en")
        
        doc_author = doc.author or "Dr. Laxmikant R.Kanojiya, Dr. Krati Sharma"
        if not doc.author or "Educational Board" in doc.author or "Semantic Publishing" in doc.author:
            doc_author = "Dr. Laxmikant R.Kanojiya, Dr. Krati Sharma"
            
        book.add_author(doc_author)
            
        # 2. Define Reference Custom CSS
        css_content = """/* This defines styles and classes used in the book */
body {
  margin: 10px;
  text-align: justify;
}
p {
  text-align: justify;
}
li {
  text-align: justify;
}
img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 1em auto;
}
figure {
  display: block;
  margin: 1.5em auto;
  text-align: center;
}
figcaption {
  font-size: 0.9em;
  color: #555;
  margin-top: 4px;
  font-style: italic;
  text-align: center;
}
h1 {
  display: block;
  text-align: left;
}
h2 {
  display: block;
  text-align: left;
}
h3 {
  display: block;
  text-align: left;
}
h4 {
  display: block;
  text-align: left;
}
h5 {
  text-align: left;
}
h6 {
  text-align: left;
}
ol.toc {
  padding: 0;
  margin-left: 7px;
}
ol.toc li {
  list-style-type: none;
  margin: 0;
  padding: 0;
}
ul {
  list-style-type: disc;
  list-style-position: outside;
}
ul ul {
  list-style-type: circle;
  list-style-position: outside;
}
tr:nth-child(even) {
  background-color: #f2f2f2;
}
ol, ul {
  margin-left: 7px !important;
  padding-left: 15px;
}
a.footnoteRef {
  vertical-align: super;
}
em, em em em, em em em em em {
  font-style: italic;
}
em em, em em em em {
  font-style: normal;
}
.img_class {
  height: auto;
  max-width: 100%;
  display: block;
  margin: 0 auto;
}
img {
  height: auto;
  max-width: 100%;
  display: block;
  margin: 0 auto;
}
.level_1 {
  text-align: justify;
  line-height: 1.2;
  text-indent: 0;
  margin-top: 10px;
}
.level_1_bold {
  text-align: justify;
  line-height: 1.2;
  text-indent: 0;
  margin-top: 10px;
  font-weight: bold;
  color: #0070C0;
}
.subtopic_header {
  text-align: left;
  line-height: 1.2;
  text-indent: 0;
  margin-top: 10px;
  font-weight: bold;
  color: #0070C0;
  border-bottom: 4px solid #FFC000;
  padding-bottom: 4px;
  margin-bottom: 20px;
}
.center_underline {
  line-height: 1.2;
  text-align: center;
  color: #0070C0;
  text-underline-offset: 8px;
  text-decoration: underline;
  text-decoration-color: #FFC000;
  text-decoration-thickness: 4px;
  padding-bottom: 4px;
  margin-bottom: 30px;
}
.chapter_header {
  border-collapse: collapse;
  border-spacing: 2px;
  display: table;
  margin-bottom: 0;
  margin-left: 0;
  margin-top: 0;
  text-indent: 0;
  width: 100%;
  padding: 0;
}
.td_unit_no {
  background-color: #a1a8b3;
  border-left-style: black solid 1pt;
  border-top-style: black solid 1pt;
  text-align: left;
  text-indent: 0;
  padding: 5px;
}
.unit_no_text {
  display: block;
  font-size: 1.66667em;
  line-height: 1.2;
  text-align: left;
  text-indent: 0;
  padding: 0;
  margin: 0;
}
.chap_name {
  display: block;
  font-size: 1.29167em;
  font-weight: bold;
  line-height: 1.5;
  padding: 10px;
  margin: 0;
  text-transform: uppercase;
  text-align: center;
  background-color: none;
}
.td_chap_name {
  border-right-style: hidden;
  border-top-style: hidden;
  border-bottom-style: hidden;
  display: table-cell;
  text-align: left;
  vertical-align: center;
  padding: 0;
}
.topic_header {
  background-color: #FFE599;
  display: block;
  font-weight: bold;
  line-height: 1.2;
  margin: 0 0 10px 0;
  text-align: left;
  box-sizing: border-box;
  padding-left: 5px;
  padding-top: 10px;
  padding-right: 10px;
  padding-bottom: 10px;
  text-transform: uppercase;
}
.level_2 {
  text-align: justify;
  margin-left: 7pt;
  margin-top: 10px;
  text-indent: 0;
}
.level_2_bold {
  text-align: justify;
  margin-left: 7pt;
  margin-top: 10px;
  text-indent: 0;
  font-weight: bold;
}
.border_box {
  border: 1px solid #0070C0;
  padding: 10px;
  margin-bottom: 15px;
}
.level_3 {
  text-align: justify;
  margin-left: 14pt;
  margin-top: 10px;
  text-indent: 0;
}
.syllabus_header {
  color: black;
  display: block;
  font-size: 2em;
  font-weight: bold;
  line-height: 1.5;
  text-align: center;
  padding: 0;
  margin: 0;
}
.rounded_div {
  border-radius: 45px;
  border: 3px solid #3579D5;
  padding: 20px;
  max-width: 100%;
  height: auto;
  margin-top: 30px;
  margin-bottom: 30px;
  margin-right: 5px;
  margin-left: 0;
}
.about_author {
  font-size: 1.15em;
  text-align: center;
}
.table_ {
  border-collapse: collapse;
  border-spacing: 2px;
  display: table;
  line-height: 1.2;
  margin-bottom: 20px;
  margin-left: 2pt;
  margin-top: 20px;
  text-indent: 0;
  padding: 10pt;
  width: 100%;
  border: black solid 1pt;
}
.td_ {
  background-color: transparent;
  display: table-cell;
  line-height: 1.2;
  text-align: left;
  vertical-align: center;
  padding: 5px;
  border-right: black solid 1pt;
  border-bottom: black solid 1pt;
  border-top: black solid 1pt;
  border-left: black solid 1pt;
}
.chapter_end {
  text-align: center;
  font-weight: bold;
  margin-top: 20px;
  margin-bottom: 20px;
}
.incorrect {
  color: red;
  font-weight: bold;
}
.td_1 {
  font-weight: bold;
  background-color: #B7DEE8;
  display: table-cell;
  line-height: 1.2;
  text-align: inherit;
  vertical-align: middle;
  padding: 5px;
  border-right: black solid 1pt;
  border-bottom: black solid 1pt;
  border-left: black solid 1pt;
  border-top: black solid 1pt;
}
.author_qualification {
  margin-top: 5px;
  display: block;
  font-size: 1em;
  font-weight: bold;
  line-height: 1.2;
  text-align: center;
}
.correct {
  color: green;
  font-weight: bold;
}
li span {
  position: relative;
  left: 0;
}
figcaption {
  background-color: black;
  color: white;
  font-style: italic;
  padding: 2px;
  text-align: center;
}
/* MCQ styles */
.question {
  margin-bottom: 15px;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background-color: #fcfcfc;
}
.question h3 {
  margin-top: 0;
  color: #0070C0;
}
.answer {
  margin-top: 10px;
  font-weight: bold;
  min-height: 1.2em;
}
input[type="radio"] {
  margin-right: 8px;
  transform: scale(1.1);
  vertical-align: middle;
}
label {
  vertical-align: middle;
  line-height: 1.5;
}
.formula {
  text-align: center;
  font-family: inherit;
  font-weight: bold;
  margin: 12px 0;
  display: block;
}
.exercise_header_grey {
  width: 100%;
  border-collapse: collapse;
  margin-top: 15px;
  margin-bottom: 20px;
  background-color: #a1a8b3 !important;
  border-top: 1.5pt solid black;
  border-bottom: 1.5pt solid black;
}
.exercise_header_grey tr {
  background-color: #a1a8b3 !important;
}
.exercise_header_grey td {
  padding: 8px 12px;
  vertical-align: middle;
  color: black;
  font-size: 1.3em;
  border: none !important;
  background-color: #a1a8b3 !important;
}
.exercise_header_grey td.left {
  text-align: left;
  font-weight: bold;
}
.exercise_header_grey td.center {
  text-align: center;
  font-weight: bold;
}
.exercise_header_yellow {
  background-color: #FFE599 !important;
  display: block;
  font-weight: bold;
  font-size: 1.25em;
  line-height: 1.2;
  margin: 15px 0 20px 0;
  text-align: left;
  box-sizing: border-box;
  padding: 10px 12px;
  text-transform: uppercase;
  color: black;
}
"""
        # Append dynamic/custom textbook styles to css_content
        css_content += """
/* textbook component block styles */
.tb-box {
  background: var(--box-bg);
  border: 1px solid var(--box-border);
  border-left: 4px solid var(--box-accent);
  border-radius: 12px;
  padding: 16px 18px;
  margin: 1.5rem 0;
}
.tb-box__label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--box-text);
  margin-bottom: 8px;
}
.tb-box__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 6px;
  background: var(--box-accent);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}
.tb-box__body {
  font-size: 15.5px;
  line-height: 1.65;
}
.tb-box__body p { margin: 0 0 0.6em; }
.tb-box__body p:last-child { margin-bottom: 0; }
.tb-box__body ul, .tb-box__body ol { margin: 0.4em 0 0; padding-left: 1.3em; }
.tb-box__body li { margin-bottom: 0.35em; }

.key-term {
  font-weight: 700;
  color: #7A2951;
  background: #FCEAF1;
  border: 1.5px solid #F0B9D2;
  border-left: 4px solid #C2427A;
  border-radius: 4px;
  padding: 2px 9px 2px 8px;
  white-space: nowrap;
}
.key-term-block {
  --box-bg: #FCEAF1;
  --box-border: #F0B9D2;
  --box-accent: #C2427A;
  --box-text: #7A2951;
}
.key-term-block__term {
  display: inline-block;
  font-weight: 700;
  color: #7A2951;
  background: #ffffff;
  border: 1px solid #F0B9D2;
  border-radius: 5px;
  padding: 1px 8px;
  margin-right: 8px;
}
.key-term-block__def {
  font-size: 15.5px;
  line-height: 1.65;
}

.definition-box  { --box-bg: #F3F1FB; --box-border: #DAD3F2; --box-accent: #6D53C7; --box-text: #3B2C82; }
.note-box        { --box-bg: #EEF1F3; --box-border: #D7DEE3; --box-accent: #5B6B7A; --box-text: #33414D; }
.example-box     { --box-bg: #E9F6F1; --box-border: #C3E7D9; --box-accent: #1F9D77; --box-text: #0F5C46; }
.activity-box    { --box-bg: #FFF3E7; --box-border: #F7DCB8; --box-accent: #D97C1F; --box-text: #8A4C0C; }
.important-box   { --box-bg: #FDECEC; --box-border: #F6C8C8; --box-accent: #C4302B; --box-text: #7E1E1B; }
.warning-box     { --box-bg: #FFF8E1; --box-border: #F3E0A0; --box-accent: #B8860B; --box-text: #7A5A06; }
.fact-box        { --box-bg: #E8F6FA; --box-border: #C2E7F0; --box-accent: #1090B0; --box-text: #0A5D73; }
.case-box        { --box-bg: #F2F0EC; --box-border: #DEDAD0; --box-accent: #74695A; --box-text: #4A4136; }
.summary-box     { --box-bg: #EDF6E9; --box-border: #CBE7C0; --box-accent: #4E9A34; --box-text: #2E5E1F; }
.learning-box    { --box-bg: #EEF0FC; --box-border: #D2D6F3; --box-accent: #4C5BC9; --box-text: #2C3585; }
.exam-tip        { --box-bg: #F7EEF9; --box-border: #E7CFEE; --box-accent: #9A3FAE; --box-text: #6A2678; }
.realworld-box   { --box-bg: #E7F0FB; --box-border: #C6DBF2; --box-accent: #2563C7; --box-text: #163E7E; }
.formula-box     { --box-bg: #F5F5F3; --box-border: #DEDCD4; --box-accent: #40403A; --box-text: #232320; text-align: center; }
.formula-box .tb-box__label { justify-content: center; }
.formula-box__expr { font-family: monospace; font-size: 17px; font-weight: 600; padding: 6px 0; }
.formula-box__note { font-size: 13px; color: #5b5a53; margin-top: 6px; }

.flow-box        { --box-bg: #FAFAF8; --box-border: #E2E0D7; --box-accent: #6B6A61; --box-text: #232320; }
.flow-box__steps { display: flex; flex-wrap: wrap; align-items: stretch; gap: 0; }
.flow-box__step  { display: flex; align-items: center; gap: 10px; background: #ffffff; border: 1px solid #E2E0D7; border-radius: 8px; padding: 10px 14px; font-size: 14px; margin: 4px 8px 4px 0; }
.flow-box__num   { display: inline-flex; align-items: center; justify-content: center; width: 20px; height: 20px; border-radius: 50%; background: #6B6A61; color: #fff; font-size: 11px; font-weight: 700; flex-shrink: 0; }
.flow-box__arrow { display: inline-flex; align-items: center; color: #6B6A61; font-size: 16px; margin: 4px 2px; }

.timeline-box    { --box-bg: #EEF5F3; --box-border: #CDE2DB; --box-accent: #4F7A78; --box-text: #2B4E4B; }
.timeline-box__list { position: relative; margin: 4px 0 0; padding-left: 20px; border-left: 2px solid #CDE2DB; }
.timeline-box__event { position: relative; padding: 0 0 16px 16px; }
.timeline-box__event:last-child { padding-bottom: 0; }
.timeline-box__event::before { content: ""; position: absolute; left: -25px; top: 4px; width: 10px; height: 10px; border-radius: 50%; background: #4F7A78; border: 2px solid #ffffff; }
.timeline-box__date { display: block; font-size: 12px; font-weight: 700; color: #4F7A78; margin-bottom: 2px; }
.timeline-box__desc { font-size: 14.5px; line-height: 1.55; }

/* Custom row/cell highlights */
.row-blue { background-color: #dbeafe !important; }
.row-green { background-color: #dcfce7 !important; }
.row-orange { background-color: #ffedd5 !important; }
.row-purple { background-color: #f3e8ff !important; }
.row-red { background-color: #fee2e2 !important; }
.row-alt-grey { background-color: #f3f4f6 !important; }

.cell-blue { background-color: #dbeafe !important; }
.cell-green { background-color: #dcfce7 !important; }
.cell-orange { background-color: #ffedd5 !important; }
.cell-purple { background-color: #f3e8ff !important; }
.cell-red { background-color: #fee2e2 !important; }
"""
        # Append compiled dynamic table/span classes
        generated_css_str = "\n/* Dynamically generated classes for clean inline styling */\n"
        for class_name, declarations in self.generated_css_classes.items():
            decls_str = " ".join(f"{k}: {v};" for k, v in declarations)
            generated_css_str += f".{class_name} {{ {decls_str} }}\n"
        css_content += generated_css_str

        style_item = epub.EpubItem(
            uid="style",
            file_name="style/style.css",
            media_type="text/css",
            content=css_content
        )
        book.add_item(style_item)

        # 3. Add Cover image and cover.xhtml
        media_cover = settings.DATA_DIR / "extracted" / "media" / "cover2.jpg"
        if media_cover.exists():
            try:
                media_cover.unlink()
                logger.info("EpubGenerator: Cleared cached cover2.jpg to prevent leakage.")
            except Exception as e:
                logger.warning(f"EpubGenerator: Could not clear cached cover2.jpg: {e}")
                
        # Look for a document-specific cover image first
        cover_path = None
        
        # Check in the same directory as source docx
        if doc.source_file:
            src_path = Path(doc.source_file)
            for ext in ['.jpg', '.jpeg', '.png']:
                potential_cover = src_path.with_suffix(ext)
                if potential_cover.exists():
                    cover_path = potential_cover
                    break
                    
        # Check in docs/ directory for a filename matching the cleaned title
        if not cover_path:
            cleaned_title = re.sub(r'[^a-zA-Z0-9]', '_', doc.title.lower()).strip('_')
            docs_dir = settings.WORKSPACE_DIR / "docs"
            if docs_dir.exists():
                for f in docs_dir.glob("*"):
                    f_name = f.name.lower()
                    if f.suffix.lower() in ['.jpg', '.jpeg', '.png'] and (cleaned_title in f_name or f_name.startswith(cleaned_title)):
                        cover_path = f
                        break
                        
        # If compiling the original "Marketing Mix" and cover.jpg exists, fallback to it
        if not cover_path and "marketing mix" in doc.title.lower():
            fallback_cover = settings.WORKSPACE_DIR / "docs" / "cover.jpg"
            if fallback_cover.exists():
                cover_path = fallback_cover

        # Copy and register cover if found
        cover_image_added = False
        if cover_path:
            media_cover.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            try:
                shutil.copy2(cover_path, media_cover)
                logger.info(f"EpubGenerator: Copied cover image {cover_path.name} to images/cover2.jpg")
                book.set_cover("images/cover2.jpg", media_cover.read_bytes())
                cover_image_added = True
                logger.info("EpubGenerator: Registered cover image with EbookLib")
            except Exception as e:
                logger.error(f"EpubGenerator: Failed to copy or register cover image: {e}")

        # 4. Add any media files from this document's isolated extraction folder
        doc_media_dir = settings.DATA_DIR / "extracted" / document_id / "media"
        # Fallback to legacy shared media dir if doc-scoped dir doesn't exist
        if not doc_media_dir.exists():
            doc_media_dir = settings.DATA_DIR / "extracted" / "media"
        media_dir = doc_media_dir
        if media_dir.exists():
            for img_path in media_dir.glob("*"):
                if img_path.is_file() and img_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif']:
                    if img_path.name == "cover2.jpg" and cover_image_added:
                        continue
                    ext = img_path.suffix.lower()
                    media_type = "image/png" if ext == ".png" else "image/jpeg"
                    if ext == ".gif":
                        media_type = "image/gif"
                    
                    try:
                        img_content = img_path.read_bytes()
                        img_item = epub.EpubImage(
                            uid=f"img_{img_path.stem}",
                            file_name=f"images/{img_path.name}",
                            media_type=media_type,
                            content=img_content
                        )
                        book.add_item(img_item)
                        logger.info(f"EpubGenerator: Added media image: images/{img_path.name}")
                    except Exception as e:
                        logger.error(f"EpubGenerator: Failed to add image {img_path.name} to EPUB: {e}")

        # Add dynamically extracted base64 images
        for filename, img_data, media_type in self.dynamic_images:
            try:
                img_item = epub.EpubImage(
                    uid=f"dyn_img_{filename.split('.')[0]}",
                    file_name=f"images/{filename}",
                    media_type=media_type,
                    content=img_data
                )
                book.add_item(img_item)
                logger.info(f"EpubGenerator: Added dynamically extracted base64 image: images/{filename}")
            except Exception as e:
                logger.error(f"EpubGenerator: Failed to add dynamic image {filename} to EPUB: {e}")

        # 5. Compile the Cover page XHTML — only if a cover image was found in the docx
        spine_items = []
        toc_items = []
        if cover_image_added:
            cover_html = epub.EpubHtml(
                title="Cover",
                file_name="cover.xhtml",
                lang="en"
            )
            cover_html.content = """<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <meta http-equiv="Content-Style-Type" content="text/css"/>
  <link rel="stylesheet" type="text/css" href="style/style.css"/>
</head>
<body id="cover">
<div id="cover-image">
<img src="images/cover2.jpg" alt="cover image" class="img_class"/>
</div>
</body></html>"""
            cover_html.add_item(style_item)
            book.add_item(cover_html)
            spine_items.append(cover_html)

        # 6. Add synthesized Copyright page
        copyright_html = epub.EpubHtml(
            title="Copyright",
            file_name="Copyright.xhtml",
            lang="en"
        )
        copyright_html.content = f"""<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Copyright</title>
  <link type="text/css" rel="stylesheet" href="style/style.css"/>
</head>
<body>
<div class="rounded_div">
<p class="syllabus_header">COPYRIGHT</p>
<p class="level_1">&#160;</p>
    <p class="level_1" style="text-align:center;"><b>All rights reserved. </b></p>
    <p class="level_1">&#160;</p>
    <p class="level_1" style="text-align:center;">No part of this publication may be reproduced, distributed, or transmitted in any form or by any means, including photocopying, recording, or other electronic or mechanical methods, without the prior written permission of the publisher, except in the case of brief quotations embodied in critical reviews and certain other non commercial uses permitted by copyright law. </p>
    <p class="level_1">&#160;</p>
    <p class="level_1">&#160;</p>
<p class="level_1">ISBN : <b>978-81-994103-6-7</b> ebook</p>
<p class="level_1">Author : <b>{doc_author} </b></p>
<p class="level_1">Special Thanks : <b>Bindiya B.,</b></p>
<p class="level_1">Published by :<b> Digilearning Tech Pvt. Ltd.</b></p>
<p class="level_1">Contact : <b> digilearningtech@gmail.com</b></p>
    <p class="level_1">&#160;</p>
    <p class="level_1">&#160;</p>
    <p class="level_1" style="text-align:center;"><b>Copyright © 2025, Digilearning Tech Pvt. Ltd.</b></p>
</div>
<p class="level_1">&#160;</p><p class="chapter_end">**************************</p><p class="level_1">&#160;</p></body></html>"""
        copyright_html.add_item(style_item)
        book.add_item(copyright_html)

        # 7. Retrieve section nodes ordered by position
        sections = self.db.query(Section)\
            .filter(Section.document_id == document_id)\
            .order_by(Section.position)\
            .all()
            
        # Dynamically synthesize a single Syllabus page if there isn't one already
        has_explicit_syllabus = any("syllabus" in s.title.lower() for s in sections)
        if not has_explicit_syllabus:
            syllabus_keywords = ["course objective", "course outcome", "continuous assessment", "end examination", "continuous evaluation", "semester end"]
            syllabus_secs = [s for s in sections if any(kw in s.title.lower() for kw in syllabus_keywords)]
            if syllabus_secs:
                first_syllabus_sec = syllabus_secs[0]
                first_syllabus_sec.title = "Syllabus"
                first_syllabus_sec.level = 1
                first_syllabus_sec.parent_id = None
                self.db.add(first_syllabus_sec)
                logger.info(f"EpubGenerator: Dynamically promoted '{first_syllabus_sec.title}' at position {first_syllabus_sec.position} to unified Syllabus page.")
                
                for other_sec in syllabus_secs[1:]:
                    other_sec.parent_id = first_syllabus_sec.id
                    other_sec.level = 3
                    self.db.add(other_sec)
                    logger.info(f"EpubGenerator: Nested '{other_sec.title}' under synthesized Syllabus.")
                self.db.commit()
                # Re-query sections to ensure updated state
                sections = self.db.query(Section)\
                    .filter(Section.document_id == document_id)\
                    .order_by(Section.position)\
                    .all()
            
        # Dynamically promote exercise sections to Level-1 and correct mislabeled titles (e.g. MCQ -> True or False)
        for sec in sections:
            if sec.level > 1 and is_exercise_title(sec.title):
                sec.level = 1
                self.db.add(sec)
                logger.info(f"EpubGenerator: Dynamically promoted section '{sec.title}' at position {sec.position} to Level-1 exercise.")
                
            # Rename mislabeled MCQ titles if they actually contain True/False questions
            if is_exercise_title(sec.title) and any(kw in sec.title.lower() for kw in ["mcq", "multiple choice", "choice question"]):
                md_content = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown or ""
                descendants = self._get_descendant_sections(sec.id)
                for d in descendants:
                    d_md = d.validated_markdown or d.formatted_markdown or d.raw_markdown or ""
                    if d_md:
                        md_content += "\n\n" + d_md
                has_mcq_options = re.search(r'(?m)^[ \t]*[a-dA-D][\s).]+', md_content)
                if not has_mcq_options and re.search(r'(?i)\b(true|false)\b', md_content):
                    sec.title = "True or False"
                    self.db.add(sec)
                    logger.info(f"EpubGenerator: Mislabeled MCQ section at position {sec.position} renamed to 'True or False' based on content context.")
        self.db.commit()
            
        # Update HTML contents in database
        for sec in sections:
            if sec.level == 0:
                continue
            md_to_render = sec.validated_markdown or sec.formatted_markdown or sec.raw_markdown
            if not md_to_render:
                continue
            html_body = self.converter.convert(md_to_render)
            sec.html_content = html_body
            sec.processing_status = "html_generated"
            self.db.add(sec)
        # Force specific casing from blueprint non_chapter_pages if matching
        non_chapter_pages = blueprint.get("non_chapter_pages", [])
        for sec in sections:
            sec_title_lower = sec.title.lower() if sec.title else ""
            for ncp in non_chapter_pages:
                orig_title = ncp.get("original_title", "")
                desired_title = ncp.get("desired_title", "")
                if orig_title and desired_title and orig_title.lower() == sec_title_lower:
                    logger.info(f"EpubGenerator: Updating casing of non-chapter page '{sec.title}' to '{desired_title}' based on blueprint.")
                    sec.title = desired_title
                    self.db.add(sec)
        self.db.commit()

        # 8. Compile book spine pages
        level1_sections = [s for s in sections if s.level == 1]
        
        # Dynamically extract valid chapter titles from Contents and Syllabus sections
        valid_chapter_titles = set()
        contents_and_syllabus_secs = [
            s for s in sections 
            if any(kw in s.title.lower() for kw in ["contents", "syllabus", "course outcome", "course outcomes"])
        ]
        for s_sec in contents_and_syllabus_secs:
            s_md = s_sec.validated_markdown or s_sec.formatted_markdown or s_sec.raw_markdown or ""
            if s_md:
                # Add descendants of these sections
                s_descendants = self._get_descendant_sections(s_sec.id)
                for d in s_descendants:
                    d_md = d.validated_markdown or d.formatted_markdown or d.raw_markdown or ""
                    if d_md:
                        s_md += "\n\n" + d_md
                
                # Check lines for chapter patterns
                lines = s_md.split("\n")
                for line in lines:
                    line_clean = line.strip()
                    # Pattern 1: Chapter 1: Green Economy
                    m = re.match(r'(?i)^(?:chapter|unit|module)\s*\d+[:\s\-\.]*\s*(.*)', line_clean)
                    if m:
                        title_part = m.group(1).split("\t")[0].split("..")[0].strip()
                        title_part = re.sub(r'\s*\d+$', '', title_part).strip()
                        title_part = re.sub(r'[\s·\.]+$', '', title_part).strip()
                        clean_title = re.sub(r'[^a-zA-Z0-9\s]', '', title_part).lower().strip()
                        if clean_title:
                            valid_chapter_titles.add(clean_title)
                    
                    # Pattern 2: Table rows with Module 1 | Green Economy
                    if "|" in line_clean:
                        parts = [p.strip() for p in line_clean.split("|") if p.strip()]
                        if len(parts) >= 2:
                            m_table = re.search(r'(?i)(?:module|chapter|unit)\s*\d+', parts[0])
                            if m_table:
                                details = parts[1]
                                sub_lines = re.split(r'<br\s*/?>|\n', details)
                                first_line = sub_lines[0].replace("**", "").replace("*", "").strip()
                                clean_title = re.sub(r'[^a-zA-Z0-9\s]', '', first_line).lower().strip()
                                if clean_title:
                                    valid_chapter_titles.add(clean_title)
                                    
        logger.info(f"EpubGenerator: Dynamically extracted valid chapter titles: {valid_chapter_titles}")
        
        # Build dynamic module mapping from syllabus table details if available
        module_mapping = {}
        for s_sec in contents_and_syllabus_secs:
            s_md = s_sec.validated_markdown or s_sec.formatted_markdown or s_sec.raw_markdown or ""
            if s_md:
                s_descendants = self._get_descendant_sections(s_sec.id)
                for d in s_descendants:
                    d_md = d.validated_markdown or d.formatted_markdown or d.raw_markdown or ""
                    if d_md:
                        s_md += "\n\n" + d_md
                
                rows = s_md.split("\n")
                for row in rows:
                    if "|" not in row:
                        continue
                    parts = [p.strip() for p in row.split("|") if p.strip()]
                    if len(parts) >= 2:
                        m = re.search(r'(?i)module\s*(\d+)', parts[0])
                        if m:
                            mod_num = int(m.group(1))
                            details = parts[1]
                            lines = re.split(r'<br\s*/?>|\n', details)
                            first_line = lines[0].replace("**", "").replace("*", "").strip()
                            clean_title = re.sub(r'[^a-zA-Z0-9\s]', '', first_line).lower().strip()
                            if clean_title:
                                module_mapping[clean_title] = mod_num
        # Build chapter-to-module mapping from blueprint
        chapter_module_map = {}
        blueprint_modules = blueprint.get("modules", [])
        for mod in blueprint_modules:
            mod_num = mod.get("module_number", 1)
            chapters = mod.get("chapters", [])
            for ch in chapters:
                ch_title = ch.get("chapter_title", "")
                if ch_title:
                    chapter_module_map[ch_title.lower().strip()] = mod_num
        logger.info(f"EpubGenerator: Built chapter-to-module map from blueprint: {chapter_module_map}")

        # Blacklist of titles that are NOT real content chapters
        non_chapter_keywords = [
            'author', 'about author', 'about book', 'about the book', 'acknowledg',
            'syllabus', 'copyright', 'contents', 'table of contents', 'sample question paper',
            'question paper', 'study notes', 'true or false', 'true/false', 'match the',
            'multiple choice', 'mcq', 'choice question', 'quiz', 'case study', 'case studies',
            'fill in the blank', 'fill in blank', 'fill in the blanks', 'answers', 'practice questions',
            'brief answer', 'short notes'
        ]

        # Dynamically promote real content chapters (even if Level-2 in DB) to Level-1
        for sec in sections:
            if sec.level > 1 and not any(kw in sec.title.lower() for kw in non_chapter_keywords) and not is_exercise_title(sec.title):
                # Check regex: if it explicitly starts with Chapter, Unit, or Module
                if bool(re.match(r'(?i)^(?:chapter|unit|module)\b', sec.title.strip())):
                    sec.level = 1
                    self.db.add(sec)
                else:
                    # Check blueprint
                    in_blueprint = False
                    for mod in blueprint_modules:
                        for ch in mod.get("chapters", []):
                            if ch.get("chapter_title", "").lower().strip() in sec.title.lower():
                                in_blueprint = True
                                break
                    if in_blueprint:
                        sec.level = 1
                        self.db.add(sec)
                    elif valid_chapter_titles:
                        clean_sec_title = re.sub(r'[^a-zA-Z0-9\s]', '', sec.title).lower().strip()
                        if clean_sec_title in valid_chapter_titles or any(kw in sec.title.lower() for kw in valid_chapter_titles):
                            sec.level = 1
                            self.db.add(sec)
        self.db.commit()
        
        # Re-query sections to ensure updated level state is reflected in level1_sections
        sections = self.db.query(Section)\
            .filter(Section.document_id == document_id)\
            .order_by(Section.position)\
            .all()
        level1_sections = [s for s in sections if s.level == 1]

        # spine_items already initialized above (with cover if image exists)
        spine_items.append(copyright_html)
        toc_items = []
        
        # State trackers
        module_num = 1
        last_seen_module = 1
        real_chapter_index = 0
        last_real_chapter_num = None
        
        for ch_sec in level1_sections:
            title = ch_sec.title
            title_lower = title.lower()
            
            # Skip copyright if it is already manually in DB (we synthesize it)
            if "copyright" in title_lower:
                continue
                
            # Skip static TOC contents page to prevent ugly dot formatting pages in EPUB
            if "contents" in title_lower or "table of contents" in title_lower:
                continue
                
            # Skip empty parent sections (e.g. "Practice Questions" wrappers that have no own content and no non-promoted children)
            md_content = ch_sec.validated_markdown or ch_sec.formatted_markdown or ch_sec.raw_markdown or ""
            clean_md = re.sub(r'(?m)^#+.*$', '', md_content).strip()
            descendants = self._get_descendant_sections(ch_sec.id)
            has_descendant_content = False
            for d in descendants:
                d_md = d.validated_markdown or d.formatted_markdown or d.raw_markdown or ""
                if re.sub(r'(?m)^#+.*$', '', d_md).strip():
                    has_descendant_content = True
                    break
            if not clean_md and not has_descendant_content:
                logger.info(f"EpubGenerator: Skipping empty parent section page '{title}' at position {ch_sec.position}")
                continue
                
            # Update module count statefully from blueprint chapter mapping first
            matched_module = None
            for key, mod_val in chapter_module_map.items():
                if key in title_lower:
                    matched_module = mod_val
                    break
            
            # If blueprint mapping failed, try dynamic syllabus mapping as fallback
            if matched_module is None:
                for key, mod_val in module_mapping.items():
                    if key in title_lower:
                        matched_module = mod_val
                        break
            
            if matched_module is not None:
                module_num = matched_module
                logger.info(f"EpubGenerator: Section '{title}' mapped to Module {module_num} via blueprint/syllabus.")
            else:
                # Extract module number directly from title if explicitly present, e.g. "Module 2"
                m_mod = re.search(r'(?i)module\s*(\d+)', title)
                if m_mod:
                    module_num = int(m_mod.group(1))
                        
            # Reset chapter index if module changes
            if module_num != last_seen_module:
                logger.info(f"EpubGenerator: Module changed from {last_seen_module} to {module_num}. Resetting chapter index from {real_chapter_index} to 0.")
                last_seen_module = module_num
                real_chapter_index = 0
                    
            # Check if this Level-1 section is a real content chapter
            is_real_chapter = False
            if not any(kw in title_lower for kw in non_chapter_keywords) and not is_exercise_title(title):
                if bool(re.match(r'(?i)^(?:chapter|unit|module)\b', title.strip())):
                    is_real_chapter = True
                else:
                    # Try blueprint chapter matching first
                    in_blueprint_chapters = False
                    for mod in blueprint_modules:
                        for ch in mod.get("chapters", []):
                            ch_title = ch.get("chapter_title", "")
                            if ch_title and ch_title.lower().strip() in title_lower:
                                in_blueprint_chapters = True
                                break
                    if in_blueprint_chapters:
                        is_real_chapter = True
                    elif valid_chapter_titles:
                        is_real_chapter = any(kw in title_lower for kw in valid_chapter_titles)
                    else:
                        is_real_chapter = bool(re.match(r'(?i)^(?:chapter|unit|module)\b', title.strip()))
            
            if is_real_chapter:
                num_match = re.search(r'(?i)^(?:chapter|unit|module)\s*(\d+)', title.strip())
                if num_match:
                    ch_num = num_match.group(1)
                else:
                    real_chapter_index += 1
                    ch_num = str(real_chapter_index)
                last_real_chapter_num = ch_num
            else:
                ch_num = None
                
            display_title = title
            if not is_real_chapter:
                display_title = re.sub(r'(?i)^chapter\s*\d+\s*[:\-]?\s*', '', title).strip()
                display_title_lower = display_title.lower()
                if "case studies" in display_title_lower or "case study" in display_title_lower:
                    display_title = "Case Studies"
                elif "mcq" in display_title_lower or "choice question" in display_title_lower:
                    display_title = "MCQs"
                elif "true or false" in display_title_lower or "true/false" in display_title_lower:
                    display_title = "True or False"
                elif "match the" in display_title_lower:
                    display_title = display_title
                else:
                    display_title = display_title

            file_name = get_file_name_for_section(title, ch_sec.position, module_num, last_real_chapter_num)
            
            ch_html = epub.EpubHtml(
                title=display_title,
                file_name=file_name,
                lang="en"
            )
            
            body_html = self.compile_section_html(ch_sec, module_num, doc.title, doc_author, ch_num)
            
            ch_html.content = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
    <meta http-equiv="Content-Style-Type" content="text/css"/>
    <title>{display_title}</title>
    <link rel="stylesheet" type="text/css" href="style/style.css" />
</head>
<body>
{body_html}
</body>
</html>"""
            ch_html.add_item(style_item)
            book.add_item(ch_html)
            spine_items.append(ch_html)
            
            # Add to TOC
            toc_items.append(epub.Link(file_name, display_title, f"sec_{ch_sec.position}"))

        # Clean any automatically generated cover page items from set_cover to prevent duplicates in spine
        clean_spine = []
        for item in spine_items:
            if item not in clean_spine:
                clean_spine.append(item)
                
        # 9. Set Navigation & Spine
        book.toc = tuple(toc_items)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Explicit spine order
        book.spine = ["nav"] + clean_spine
        
        # 10. Write the EPUB file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        non_duplicate_items = []
        seen_filenames = set()
        for item in book.items:
            if item.file_name not in seen_filenames:
                seen_filenames.add(item.file_name)
                non_duplicate_items.append(item)
        book.items = non_duplicate_items
        
        epub.write_epub(str(output_path), book, {})
        logger.info(f"EpubGenerator: Successfully written EPUB3 package to {output_path}")
        return output_path


def get_file_name_for_section(title: str, position: int, module_num: int, ch_num: str = None) -> str:
    title_lower = title.lower()
    if "title page" in title_lower or "cover" in title_lower:
        return "cover.xhtml"
    elif "about author" in title_lower:
        return "About_Author.xhtml"
    elif "about the book" in title_lower or "about book" in title_lower:
        return "About_Book.xhtml"
    elif "acknowledg" in title_lower:
        return "Acknowledgement.xhtml"
    elif "syllabus" in title_lower:
        return "Syllabus.xhtml"
    elif "copyright" in title_lower:
        return "Copyright.xhtml"
    elif "fill in the blank" in title_lower or "fill in blank" in title_lower or "fill in the blanks" in title_lower:
        ch_part = f"_Chapter{ch_num}" if ch_num else f"_{position}"
        return f"M{module_num}{ch_part}_FITB.xhtml"
    elif "mcq" in title_lower or "choice question" in title_lower:
        ch_part = f"_Chapter{ch_num}" if ch_num else f"_{position}"
        return f"M{module_num}{ch_part}_MCQ.xhtml"
    elif "true or false" in title_lower or "true/false" in title_lower:
        ch_part = f"_Chapter{ch_num}" if ch_num else f"_{position}"
        return f"M{module_num}{ch_part}_TOF.xhtml"
    elif "match the" in title_lower or "match column" in title_lower or "match following" in title_lower:
        ch_part = f"_Chapter{ch_num}" if ch_num else f"_{position}"
        return f"M{module_num}{ch_part}_MTC.xhtml"
    elif "case studies" in title_lower or "case study" in title_lower:
        ch_part = f"_Chapter{ch_num}" if ch_num else f"_{position}"
        return f"M{module_num}{ch_part}_Case_Studies.xhtml"
    elif "chapter" in title_lower:
        match = re.search(r'\d+', title)
        ch_idx = match.group(0) if match else str(position)
        return f"M{module_num}_Chapter{ch_idx}.xhtml"
    else:
        sanitized = re.sub(r'[^a-zA-Z0-9]', '_', title).strip('_')
        sanitized = '_'.join(w for w in sanitized.split('_') if w)
        if not sanitized:
            sanitized = f"section_{position}"
        return f"{sanitized}.xhtml"
