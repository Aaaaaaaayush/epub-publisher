import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import re

def clean_step_by_step(text: str) -> str:
    cleaned = text
    print("0. Input:", repr(cleaned))
    
    # 0a. Normalize non-breaking spaces and zero-width spaces
    cleaned = cleaned.replace('\xa0', ' ')
    cleaned = cleaned.replace('\u200b', '')
    print("0a. Whitespace normalization:", repr(cleaned))
    
    # 0b. Fix spacing between manual list/bullet prefixes and bold/italic tags
    cleaned = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*\*([^*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    print("0b. Prefix spacing:", repr(cleaned))
    
    # 0c. Shift leading/trailing spaces inside bold/italic tags to the outside *early*
    cleaned = re.sub(r'\*\* +([^*]+?)\*\*', r' **\1**', cleaned)
    print("0c. Space shifting opening bold:", repr(cleaned))
    cleaned = re.sub(r'\*\*([^*]+?) +\*\*', r'**\1** ', cleaned)
    print("0c. Space shifting closing bold:", repr(cleaned))
    cleaned = re.sub(r'(?<!\*)\* +([^*]+?)\*(?!\*)', r' *\1*', cleaned)
    print("0c. Space shifting opening italic:", repr(cleaned))
    cleaned = re.sub(r'(?<!\*)\*([^*]+?) +\*(?!\*)', r'*\1* ', cleaned)
    print("0c. Space shifting closing italic:", repr(cleaned))
    
    # 1. Clean bolded colons, periods, dashes, or other standalone punctuation marks
    cleaned = re.sub(r'\*\*([.,;:!?\(\)\[\]\"\'\-\/\\&\$\#\@\-\+])\*\*', r'\1', cleaned)
    print("1. Standalone punctuation:", repr(cleaned))
    
    # 2. Merge contiguous bold blocks on the same line
    while True:
        next_text = re.sub(r'\*\*([^* \t\n][^*]*?)\*\*([ \t]*)\*\*([^* \t\n][^*]*?)\*\*', r'**\1\2\3**', cleaned)
        if next_text == cleaned:
            break
        cleaned = next_text
    print("2. Merge bold blocks:", repr(cleaned))
    
    # 3. Merge bold boundary splits in digits/numbers
    cleaned = re.sub(r'\*\*([\d.]+)\*\*([.\d]+)', r'**\1\2**', cleaned)
    cleaned = re.sub(r'([\d.]+)\*\*([.\d]+)\*\*', r'**\1\2**', cleaned)
    print("3. Merge digits:", repr(cleaned))
    
    # 4. Clean up empty bold or italic markdown tags safely using lookarounds
    cleaned = re.sub(r'(?<!\*)\*\*+[ \t]*\*\*+(?!\*)', '', cleaned)
    cleaned = re.sub(r'(?<!\*)\*[ \t]+\*(?!\*)', '', cleaned)
    print("4. Clean empty tags:", repr(cleaned))
    
    return cleaned

clean_step_by_step("2.** Setting the Right Level:** Incorrect pricing")
