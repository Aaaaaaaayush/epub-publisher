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
        
    def convert(self, markdown_text: str) -> str:
        if not markdown_text:
            return ""
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
            return letter, text
            
    return None


def parse_mcq_markdown(text):
    questions = []
    lines = text.split('\n')
    current_q = None
    
    # Match standard question prefixes: 1. or (1) or 1)
    q_start_re = re.compile(r'^\s*\(?(\d+)\)?[\s\.\)]+\s*(.*)')
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
            current_q = {
                "number": q_num,
                "question": q_text,
                "options": [],
                "answer": None
            }
            continue
            
        if current_q and not current_q["options"] and current_q["answer"] is None:
            if not re.match(r'(?i)(?:answer|answers|answer\s+key)', line_str):
                current_q["question"] += " " + line_str
                
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
        html = re.sub(r"Total\s*Cost\s*(?:×|\*|\\times)?\s*Profit\s*Margin\s*%", "Total Cost × Profit Margin %", html, flags=re.IGNORECASE)
        html = re.sub(r"Selling\s*Price\s*=\s*", "Selling Price = ", html, flags=re.IGNORECASE)
        return html

    def post_process_html(self, html_content: str) -> str:
        if not html_content:
            return ""
        
        # Clean math equations first
        html_content = self.clean_math_in_html(html_content)
        soup = BeautifulSoup(html_content, "html.parser")
        
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

        # 3. Add table classes
        for table in soup.find_all("table"):
            table["class"] = "table_"
            
            # Highlight only the first header row, make rest white
            rows = table.find_all("tr")
            for r_idx, row in enumerate(rows):
                cells = row.find_all(["th", "td"])
                for cell in cells:
                    cell.name = "td"
                    if r_idx == 0:
                        cell["class"] = "td_1"
                    else:
                        cell["class"] = "td_"
                    
        # 4. Post-process images
        for img in soup.find_all("img"):
            img["class"] = "img_class"
            if not img.get("alt"):
                img["alt"] = "image"
                
        # 5. Smart post-process h3 → topic_header (yellow panel) or subtopic_header (blue underline if letter prefix)
        for h3 in list(soup.find_all("h3")):
            if not h3.get_text().strip():
                h3.decompose()
                continue
            if h3.find_parent(class_="question") or h3.find_parent(id="quiz"):
                continue
            
            h3_text = h3.get_text().strip()
            # If starts with lettered prefix like A., B., C.
            if re.match(r'^[A-Z]\.\s', h3_text):
                p = soup.new_tag("p", attrs={"class": "subtopic_header"})
            else:
                p = soup.new_tag("p", attrs={"class": "topic_header"})
            p.extend(list(h3.children))
            h3.replace_with(p)

        # 6. Smart post-process h4 → subtopic_header (blue underline)
        for h4 in list(soup.find_all("h4")):
            if not h4.get_text().strip():
                h4.decompose()
                continue
            if h4.find_parent(class_="question") or h4.find_parent(id="quiz"):
                continue
            p = soup.new_tag("p", attrs={"class": "subtopic_header"})
            p.extend(list(h4.children))
            h4.replace_with(p)
            
        # 7. Identify formula paragraphs, assign class "formula", and deduplicate consecutive duplicates
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
                
        # 8. Post-process stray Q&A or metadata code blocks back to plain text
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
            # Other exercises (Match the column, Quiz, sample question paper, etc.)
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
            
            # Check if this is a Fill in the Blanks section, and dynamically generate an answer key using LLM
            is_fib = "fill in the blank" in title_lower or "fill in blank" in title_lower or "fill in the blanks" in title_lower
            if is_fib:
                try:
                    from app.agents.base import BaseAgent
                    agent = BaseAgent(api_key=self.api_key)
                    agent.model = settings.LLM_MODEL
                    prompt = """You are an educational textbook editor. 
Your task is to solve the given Fill in the Blanks questions based on textbook contents.
Format the output as a simple numbered list of answers (one per line, just the answered phrase/word, no question text).
For example:
1. Blueprint for a Green Economy
2. low-carbon

Do not output any introductory or concluding text. Just the numbered answers."""
                    
                    logger.info(f"EpubGenerator: Dynamically generating FIB answers using LLM for '{title}'...")
                    answers_text = agent.generate_completion(system_prompt=prompt, user_content=combined_md, temperature=0.1)
                    
                    answers_list = []
                    for line in answers_text.split("\n"):
                        line_clean = line.strip()
                        if line_clean:
                            line_clean = re.sub(r'^\d+[\.\s\-\)]+\s*', '', line_clean).strip()
                            if line_clean:
                                answers_list.append(line_clean)
                    
                    if answers_list:
                        fib_answers_html = '\n<p class="level_1">&#160;</p>\n<p><strong>Answer Key:</strong></p>\n'
                        fib_answers_html += '<ol class="list_">\n'
                        for ans in answers_list:
                            fib_answers_html += f'  <li>{ans}</li>\n'
                        fib_answers_html += '</ol>\n'
                        html_body += fib_answers_html
                        logger.info(f"EpubGenerator: Successfully appended dynamic answer key (count={len(answers_list)}) to FIB section '{title}'")
                except Exception as e:
                    logger.error(f"EpubGenerator: Failed to generate dynamic FIB answer key: {e}")
            
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
                clean_title = re.sub(r'(?i)^chapter\s*\d+\s*[:\-]?\s*', '', title).strip()
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
                logger.info(f"EpubGenerator: Copied cover image {cover_path.name} to media/cover2.jpg")
                book.set_cover("media/cover2.jpg", media_cover.read_bytes())
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
                            file_name=f"media/{img_path.name}",
                            media_type=media_type,
                            content=img_content
                        )
                        book.add_item(img_item)
                        logger.info(f"EpubGenerator: Added media image: media/{img_path.name}")
                    except Exception as e:
                        logger.error(f"EpubGenerator: Failed to add image {img_path.name} to EPUB: {e}")

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
<img src="media/cover2.jpg" alt="cover image" class="img_class"/>
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

        # spine_items already initialized above (with cover if image exists)
        spine_items.append(copyright_html)
        toc_items = []
        
        # State trackers
        module_num = 1
        last_seen_module = 1
        real_chapter_index = 0
        
        # Blacklist of titles that are NOT real content chapters
        non_chapter_keywords = [
            'author', 'about author', 'about book', 'about the book', 'acknowledg',
            'syllabus', 'copyright', 'contents', 'table of contents', 'sample question paper',
            'question paper', 'study notes', 'true or false', 'true/false', 'match the',
            'multiple choice', 'mcq', 'choice question', 'quiz', 'case study', 'case studies',
            'fill in the blank', 'fill in blank', 'fill in the blanks', 'answers', 'practice questions',
            'brief answer', 'short notes'
        ]
        
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
                # Fallback to stateful chapter parsing if syllabus match not found
                if "chapter" in title_lower:
                    match = re.search(r'\d+', title)
                    if match:
                        ch_idx = int(match.group(0))
                        max_mod = max(chapter_module_map.values()) if chapter_module_map else 2
                        module_num = 1 if ch_idx <= 4 else max_mod
                elif "module" in title_lower:
                    match = re.search(r'module\s*(\d+)', title_lower)
                    if match:
                        module_num = int(match.group(1))
                        
            # Reset chapter index if module changes
            if module_num != last_seen_module:
                logger.info(f"EpubGenerator: Module changed from {last_seen_module} to {module_num}. Resetting chapter index from {real_chapter_index} to 0.")
                last_seen_module = module_num
                real_chapter_index = 0
                    
            # Check if this Level-1 section is a real content chapter
            is_real_chapter = False
            if not any(kw in title_lower for kw in non_chapter_keywords) and not is_exercise_title(title):
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
                    is_real_chapter = bool(re.match(r'(?i)^(?:chapter|unit|module)\s*\d+', title.strip()))
            
            if is_real_chapter:
                real_chapter_index += 1
                ch_num = str(real_chapter_index)
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

            file_name = get_file_name_for_section(title, ch_sec.position, module_num)
            
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


def get_file_name_for_section(title: str, position: int, module_num: int) -> str:
    title_lower = title.lower()
    if "about author" in title_lower:
        return "About_Author.xhtml"
    elif "about the book" in title_lower or "about book" in title_lower:
        return "About_Book.xhtml"
    elif "acknowledg" in title_lower:
        return "Acknowledgement.xhtml"
    elif "syllabus" in title_lower:
        return "Syllabus.xhtml"
    elif "copyright" in title_lower:
        return "Copyright.xhtml"
    elif "mcq" in title_lower or "choice question" in title_lower:
        return f"M{module_num}_MCQ_{position}.xhtml"
    elif "case studies" in title_lower or "case study" in title_lower:
        return f"M{module_num}_Case_Studies_{position}.xhtml"
    elif "chapter" in title_lower:
        match = re.search(r'\d+', title)
        ch_num = match.group(0) if match else str(position)
        return f"M{module_num}_Chapter{ch_num}.xhtml"
    else:
        sanitized = re.sub(r'[^a-zA-Z0-9]', '_', title).strip('_')
        return f"section_{position}_{sanitized}.xhtml"
