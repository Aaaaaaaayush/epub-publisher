import sys
from pathlib import Path
sys.path.append("d:/agentic_workflow")

from app.extraction.extractor import DocxExtractor
from app.formatting.formatter import clean_markdown_formatting
import re

def clean_step_by_step_traced(text):
    print("0. Input length:", len(text))
    
    cleaned = text
    cleaned = cleaned.replace('\xa0', ' ')
    cleaned = cleaned.replace('\u200b', '')
    
    # Trace specific target string "Hindustan"
    def find_target(stage, val):
        for line in val.split('\n'):
            if "Hindustan" in line:
                print(f"[{stage}] Found: {repr(line)}")
                
    find_target("0a", cleaned)
    
    cleaned = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*\*([^\n\r*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*([^\n\r*]+?)\*', r'\1 *\2*', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^(\s*[-•▪o])\*\*([^\n\r*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^(\s*[-•▪o])\*([^\n\r*]+?)\*', r'\1 *\2*', cleaned, flags=re.MULTILINE)
    find_target("0b", cleaned)

    cleaned = re.sub(r'\*\*([.,;:!?\(\)\[\]\"\'\-\/\\&\$\#\@\-\+])\*\*', r'\1', cleaned)
    cleaned = re.sub(r'\*\*\:\*\*', ':', cleaned)
    cleaned = re.sub(r'\*\*\.\*\*', '.', cleaned)
    cleaned = re.sub(r'\*\*\:\-\*\*', ':-', cleaned)
    cleaned = re.sub(r'\*\*\-\*\*', '-', cleaned)
    find_target("1", cleaned)
    
    cleaned = re.sub(r'(?<=[a-zA-Z0-9])\*\*([^\n\r*]+?)\*\*(?!\*)', r' **\1**', cleaned)
    cleaned = re.sub(r'(?<!\*)\*\*([^\n\r*]+?)\*\*(?=[a-zA-Z0-9])', r'**\1** ', cleaned)
    cleaned = re.sub(r'(?<=[a-zA-Z0-9])\*([^\n\r*]+?)\*(?!\*)', r' *\1*', cleaned)
    cleaned = re.sub(r'(?<!\*)\*([^\n\r*]+?)\*(?=[a-zA-Z0-9])', r'*\1* ', cleaned)
    find_target("2", cleaned)

    lines = cleaned.split('\n')
    processed_lines = []
    for line in lines:
        parts = re.split(r'(?<!\*)\*\*(?!\*)', line)
        if len(parts) % 2 == 1 and len(parts) > 1:
            for i in range(1, len(parts), 2):
                content = parts[i]
                if content:
                    stripped_l = content.lstrip()
                    leading_spaces = content[:len(content) - len(stripped_l)]
                    parts[i-1] += leading_spaces
                    
                    stripped_r = stripped_l.rstrip()
                    trailing_spaces = stripped_l[len(stripped_r):]
                    parts[i] = stripped_r
                    parts[i+1] = trailing_spaces + parts[i+1]
            line = "**".join(parts)
            
        parts = re.split(r'(?<!\*)\*(?!\*)', line)
        if len(parts) % 2 == 1 and len(parts) > 1:
            for i in range(1, len(parts), 2):
                content = parts[i]
                if content:
                    stripped_l = content.lstrip()
                    leading_spaces = content[:len(content) - len(stripped_l)]
                    parts[i-1] += leading_spaces
                    
                    stripped_r = stripped_l.rstrip()
                    trailing_spaces = stripped_l[len(stripped_r):]
                    parts[i] = stripped_r
                    parts[i+1] = trailing_spaces + parts[i+1]
            line = "*".join(parts)
        processed_lines.append(line)
    cleaned = '\n'.join(processed_lines)
    find_target("3", cleaned)

    while True:
        next_text = re.sub(r'\*\*([^\n\r* \t][^\n\r*]*?)\*\*([ \t]*)\*\*([^\n\r* \t][^\n\r*]*?)\*\*', r'**\1\2\3**', cleaned)
        if next_text == cleaned:
            break
        cleaned = next_text
    find_target("4", cleaned)
        
    cleaned = re.sub(r'(?<!\*)\*\*+[ \t]*\*\*+(?!\*)', '', cleaned)
    cleaned = re.sub(r'(?<!\*)\*[ \t]+\*(?!\*)', '', cleaned)
    find_target("5", cleaned)
    
    cleaned = re.sub(r'\(\s*\)', '', cleaned)
    find_target("6", cleaned)
    
    cleaned = re.sub(
        r'\*\*([^\n\r*]+)\*\*\s*(\:\-|\:)\s*',
        lambda m: f"**{m.group(1).strip()}{m.group(2)}** ",
        cleaned
    )
    find_target("7", cleaned)
    
    cleaned = re.sub(
        r'([a-zA-Z0-9])\*\*+\s*\)\s*([^\n\r*]+)\*\*+',
        lambda m: f"{m.group(1)}) **{m.group(2).strip()}**",
        cleaned
    )
    find_target("7b", cleaned)
    
    cleaned = re.sub(r'\s*\:\:\s*', ': ', cleaned)
    find_target("8", cleaned)
    
    cleaned = re.sub(
        r'\*\*([^\n\r*]+)\s*\-\s*\*\*',
        lambda m: f"**{m.group(1).strip()}**",
        cleaned
    )
    find_target("9", cleaned)
    
    cleaned = re.sub(r'^(#{1,6})\s+\*\*([^\n\r*]+)\*\*\s*$', r'\1 \2', cleaned, flags=re.MULTILINE)
    find_target("10", cleaned)
    
    return cleaned

def main():
    extractor = DocxExtractor(Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx"))
    raw_markdown = extractor.extract_to_markdown()
    clean_step_by_step_traced(raw_markdown)

if __name__ == '__main__':
    main()
