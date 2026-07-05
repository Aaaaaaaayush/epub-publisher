import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.formatting.formatter import clean_markdown_formatting
import re

def clean_step_by_step(text):
    print("0. Input:")
    print(repr(text))
    
    cleaned = text
    # 1. Clean bolded colons, periods, dashes, or other standalone punctuation marks
    cleaned = re.sub(r'\*\*([.,;:!?\(\)\[\]\"\'\-\/\\&\$\#\@\-\+])\*\*', r'\1', cleaned)
    cleaned = re.sub(r'\*\*\:\*\*', ':', cleaned)
    cleaned = re.sub(r'\*\*\.\*\*', '.', cleaned)
    cleaned = re.sub(r'\*\*\:\-\*\*', ':-', cleaned)
    cleaned = re.sub(r'\*\*\-\*\*', '-', cleaned)
    print("1. After punctuation cleanup:")
    print(repr(cleaned))
    
    # 2. Merge contiguous bold blocks on the same line
    while True:
        next_text = re.sub(r'\*\*([^* \t\n][^*]*?)\*\*([ \t]*)\*\*([^* \t\n][^*]*?)\*\*', r'**\1\2\3**', cleaned)
        if next_text == cleaned:
            break
        cleaned = next_text
    print("2. After bold merge:")
    print(repr(cleaned))
    
    # 3. Merge bold boundary splits in digits/numbers
    cleaned = re.sub(r'\*\*([\d.]+)\*\*([.\d]+)', r'**\1\2**', cleaned)
    cleaned = re.sub(r'([\d.]+)\*\*([.\d]+)\*\*', r'**\1\2**', cleaned)
    print("3. After digits merge:")
    print(repr(cleaned))
    
    # 4. Clean up empty bold or italic markdown tags safely using lookarounds
    cleaned = re.sub(r'(?<!\S)\*\*+\s*\*\*+(?!\S)', '', cleaned)
    cleaned = re.sub(r'(?<!\S)\*+\s*\*+(?!\S)', '', cleaned)
    print("4. After empty tags cleanup:")
    print(repr(cleaned))
    
    # 5. Clean empty parentheses placeholders
    cleaned = re.sub(r'\(\s*\)', '', cleaned)
    print("5. After empty parens cleanup:")
    print(repr(cleaned))
    
    # 6. Clean bold-punctuation ordering
    cleaned = re.sub(r'\*\*([^*]+)\*\*\s*(\:\-|\:)', r'**\1\2**', cleaned)
    print("6. After bold-punctuation ordering:")
    print(repr(cleaned))
    
    return cleaned

def main():
    # Let's test the text that gets extracted
    text = "    - **Direct channels** (e.g., online sales, company-owned stores)"
    print("=== TESTING STANDARD FORMAT ===")
    clean_step_by_step(text)
    
    text2 = "    - *Direct channels** (e.g., online sales, company-owned stores)"
    print("\n=== TESTING SUSPECT FORMAT ===")
    clean_step_by_step(text2)

if __name__ == "__main__":
    main()
