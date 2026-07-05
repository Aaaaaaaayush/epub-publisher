import re
from app.utils.logger import logger

def clean_markdown_formatting(text: str) -> str:
    """
    Scrubs messy formatting artifacts commonly extracted from messy DOCX files.
    Applies deterministic narrow-agent processing:
      - Shifts leading/trailing spaces inside bold/italic tags to the outside safely using a split-and-shift span parser.
      - Pads spaces bordering bold/italic tags and alphanumeric characters (e.g. word**bold** -> word **bold**).
      - Cleans bolded colons/dots (e.g. **:** -> :, **.** -> .) and stand-alone punctuation.
      - Strips empty formatting tags (e.g. ** ** -> "") and empty parentheses.
      - Normalizes non-breaking and zero-width spaces.
      - Standardizes heading and option spacing.
    """
    if not text:
        return ""
        
    cleaned = text
    
    # 0a. Normalize non-breaking spaces and zero-width spaces
    cleaned = cleaned.replace('\xa0', ' ')
    cleaned = cleaned.replace('\u200b', '')
    
    # 0b. Fix spacing between manual list/bullet prefixes and bold/italic tags
    # E.g., 1.** First -> 1. **First
    # E.g., 1.* First -> 1. *First
    cleaned = re.sub(r'^([ \t]*\d+\.|[ \t]*[a-zA-Z]\.|[ \t]*\d+\)|[ \t]*[a-zA-Z]\))\*\*([^\n\r*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^([ \t]*\d+\.|[ \t]*[a-zA-Z]\.|[ \t]*\d+\)|[ \t]*[a-zA-Z]\))\*([^\n\r*]+?)\*', r'\1 *\2*', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^([ \t]*[-•▪o])\*\*([^\n\r*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'^([ \t]*[-•▪o])\*([^\n\r*]+?)\*', r'\1 *\2*', cleaned, flags=re.MULTILINE)

    # 1. Clean bolded colons, periods, dashes, or other standalone punctuation marks *early*
    cleaned = re.sub(r'\*\*([.,;:!?\(\)\[\]\"\'\-\/\\&\$\#\@\-\+])\*\*', r'\1', cleaned)
    cleaned = re.sub(r'\*\*\:\*\*', ':', cleaned)
    cleaned = re.sub(r'\*\*\.\*\*', '.', cleaned)
    cleaned = re.sub(r'\*\*\:\-\*\*', ':-', cleaned)
    cleaned = re.sub(r'\*\*\-\*\*', '-', cleaned)
    
    # 2. Pad spaces for alphanumeric adjacencies bordering bold/italic tags
    # E.g. word**bold** -> word **bold**
    # E.g. **bold**word -> **bold** word
    cleaned = re.sub(r'(?<=[a-zA-Z0-9])\*\*([^\n\r*]+?)\*\*(?!\*)', r' **\1**', cleaned)
    cleaned = re.sub(r'(?<!\*)\*\*([^\n\r*]+?)\*\*(?=[a-zA-Z0-9])', r'**\1** ', cleaned)
    cleaned = re.sub(r'(?<=[a-zA-Z0-9])\*([^\n\r*]+?)\*(?!\*)', r' *\1*', cleaned)
    cleaned = re.sub(r'(?<!\*)\*([^\n\r*]+?)\*(?=[a-zA-Z0-9])', r'*\1* ', cleaned)

    # 3. Bulletproof Split-and-Shift Span Parser
    # Recursively shifts leading/trailing spaces inside bold/italic tags to the outside
    lines = cleaned.split('\n')
    processed_lines = []
    
    for line in lines:
        # Bold space shifting
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
            
        # Italic space shifting
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
    
    # 4. Merge contiguous bold blocks on the same line
    # E.g., **word1** **word2** -> **word1 word2**
    while True:
        next_text = re.sub(r'\*\*([^\n\r* \t][^\n\r*]*?)\*\*([ \t]*)\*\*([^\n\r* \t][^\n\r*]*?)\*\*', r'**\1\2\3**', cleaned)
        if next_text == cleaned:
            break
        cleaned = next_text
        
    # 5. Clean up empty bold or italic markdown tags safely
    cleaned = re.sub(r'(?<!\*)\*\*+[ \t]*\*\*+(?!\*)', '', cleaned)
    cleaned = re.sub(r'(?<!\*)\*[ \t]+\*(?!\*)', '', cleaned)
    
    # 6. Clean empty parentheses placeholders
    cleaned = re.sub(r'\([ \t]*\)', '', cleaned)
    
    # 7. Clean bold-punctuation ordering
    # E.g. **Introduction** : -> **Introduction:** 
    cleaned = re.sub(
        r'\*\*([^\n\r*]+)\*\*([ \t]*)(\:\-|\:)([ \t]*)',
        lambda m: f"**{m.group(1).strip()}{m.group(3)}** ",
        cleaned
    )
    
    # 7b. Merge/clean bold option prefixes like d**) -> d) **
    cleaned = re.sub(
        r'([a-zA-Z0-9])\*\*+[ \t]*\)[ \t]*([^\n\r*]+)\*\*+',
        lambda m: f"{m.group(1)}) **{m.group(2).strip()}**",
        cleaned
    )
    
    # 8. Clean double colons
    cleaned = re.sub(r'[ \t]*\:\:[ \t]*', ': ', cleaned)
    
    # 9. Clean trailing hyphens or dashes inside bold headers
    cleaned = re.sub(
        r'\*\*([^\n\r*]+)[ \t]*\-[ \t]*\*\*',
        lambda m: f"**{m.group(1).strip()}**",
        cleaned
    )
    
    # 10. Clean up redundant bolding inside headers
    # E.g. # **Header** -> # Header
    cleaned = re.sub(r'^(#{1,6})[ \t]+\*\*([^\n\r*]+)\*\*([ \t]*)$', r'\1 \2', cleaned, flags=re.MULTILINE)
    
    return cleaned
