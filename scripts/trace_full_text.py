import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import re

raw_text = """2.** Setting the Right Level:** Incorrect pricing can negatively impact a business and, in extreme cases, even lead to closure due to insufficient revenue. Hence, conducting detailed market research is essential before finalizing prices."""

def trace(text):
    cleaned = text
    print("0. Input:", repr(cleaned))
    
    # 0a. Normalize non-breaking spaces and zero-width spaces
    cleaned = cleaned.replace('\xa0', ' ')
    cleaned = cleaned.replace('\u200b', '')
    print("0a:", repr(cleaned))
    
    # 0b. Prefix spacing
    cleaned = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*\*([^*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    print("0b:", repr(cleaned))
    
    # 0c. Space shifting opening bold
    cleaned = re.sub(r'\*\* +([^*]+?)\*\*', r' **\1**', cleaned)
    print("0c opening:", repr(cleaned))
    cleaned = re.sub(r'\*\*([^*]+?) +\*\*', r'**\1** ', cleaned)
    print("0c closing:", repr(cleaned))
    
    # 1. Clean bolded colons, periods, dashes, or other standalone punctuation marks
    cleaned = re.sub(r'\*\*([.,;:!?\(\)\[\]\"\'\-\/\\&\$\#\@\-\+])\*\*', r'\1', cleaned)
    print("1:", repr(cleaned))
    
    # 2. Merge contiguous bold blocks
    while True:
        next_text = re.sub(r'\*\*([^* \t\n][^*]*?)\*\*([ \t]*)\*\*([^* \t\n][^*]*?)\*\*', r'**\1\2\3**', cleaned)
        if next_text == cleaned:
            break
        cleaned = next_text
    print("2:", repr(cleaned))
    
    # 3. Merge digits
    cleaned = re.sub(r'\*\*([\d.]+)\*\*([.\d]+)', r'**\1\2**', cleaned)
    cleaned = re.sub(r'([\d.]+)\*\*([.\d]+)\*\*', r'**\1\2**', cleaned)
    print("3:", repr(cleaned))
    
    # 4. Clean up empty bold or italic markdown tags
    cleaned = re.sub(r'(?<!\*)\*\*+[ \t]*\*\*+(?!\*)', '', cleaned)
    cleaned = re.sub(r'(?<!\*)\*[ \t]+\*(?!\*)', '', cleaned)
    print("4:", repr(cleaned))
    
    # 5. Clean empty parentheses placeholders
    cleaned = re.sub(r'\(\s*\)', '', cleaned)
    print("5:", repr(cleaned))
    
    # 6. Clean bold-punctuation ordering
    # E.g. **Introduction** : -> **Introduction:** 
    cleaned = re.sub(
        r'\*\*([^*]+)\*\*\s*(\:\-|\:)\s*',
        lambda m: f"**{m.group(1).strip()}{m.group(2)}** ",
        cleaned
    )
    print("6:", repr(cleaned))
    
    # 6b. Merge/clean bold option prefixes
    cleaned = re.sub(
        r'([a-zA-Z0-9])\*\*+\s*\)\s*([^*]+)\*\*+',
        lambda m: f"{m.group(1)}) **{m.group(2).strip()}**",
        cleaned
    )
    print("6b:", repr(cleaned))
    
    # 6c. Add a space after closing bold tags if followed immediately by an alphanumeric character
    cleaned = re.sub(r'(?<!\*)\*\*([^*]+?)\*\*(?=[a-zA-Z0-9])', r'**\1** ', cleaned)
    print("6c:", repr(cleaned))
    
    # 6d. Shift leading/trailing spaces inside bold/italic tags to the outside
    cleaned = re.sub(r'\*\* +([^*]+?)\*\*', r' **\1**', cleaned)
    print("6d opening:", repr(cleaned))
    cleaned = re.sub(r'\*\*([^*]+?) +\*\*', r'**\1** ', cleaned)
    print("6d closing:", repr(cleaned))

trace(raw_text)
