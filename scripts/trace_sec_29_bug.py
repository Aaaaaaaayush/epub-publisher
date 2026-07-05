import re

def trace_formatter_on_sec_29_lines():
    text = "2.** Setting the Right Level:** Incorrect pricing"
    print("Input:", repr(text))
    
    cleaned = text
    
    # 0a. Normalize non-breaking spaces and zero-width spaces
    cleaned = cleaned.replace('\xa0', ' ')
    cleaned = cleaned.replace('\u200b', '')
    print("0a:", repr(cleaned))
    
    # 0b. Fix spacing between manual list/bullet prefixes and bold/italic tags
    cleaned_0b = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*\*([^*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    print("0b:", repr(cleaned_0b))
    
    # 0c. Shift spaces
    cleaned_0c = re.sub(r'\*\* +([^*]+?)\*\*', r' **\1**', cleaned_0b)
    print("0c:", repr(cleaned_0c))

trace_formatter_on_sec_29_lines()
