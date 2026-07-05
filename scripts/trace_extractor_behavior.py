import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.extraction.extractor import DocxExtractor

docx_path = Path("d:/agentic_workflow/data/input/Marketing Mix-1 -Formatted.docx")
extractor = DocxExtractor(docx_path)

# find paragraphs around 1247
for idx in range(1245, 1260):
    p = extractor.doc.paragraphs[idx]
    is_list, level, list_type, prefix = extractor.get_list_details(p)
    text = p.text.strip()
    style_name = p.style.name if p.style else ""
    
    # Check for headings
    is_heading = False
    heading_level = 0
    if style_name.startswith("Heading"):
        is_heading = True
    
    print(f"\n[{idx}] Text: {repr(text)}")
    print(f"  Style: '{style_name}'")
    print(f"  is_heading: {is_heading}")
    print(f"  is_list: {is_list}, level: {level}, list_type: {repr(list_type)}, prefix: {repr(prefix)}")
    
    # Check continuation
    has_indent = False
    try:
        if p.paragraph_format.left_indent is not None:
            indent_val = p.paragraph_format.left_indent.inches
            if indent_val and indent_val > 0.1:
                has_indent = True
    except Exception:
        pass
    has_literal_indent = False
    if p.text and p.text.startswith("   "):
        has_literal_indent = True
        
    is_continuation = False
    # Let's mock the in_list = True check
    if style_name == 'List Paragraph' or has_indent or has_literal_indent:
        is_continuation = True
    elif re := extractor.get_list_details(p):
        import re
        if re.search(r'^([a-zA-Z0-9]\.|\([0-9a-zA-Z]+\)|[a-zA-Z0-9]\))\s+', text) or text.lower().startswith('answer'):
            is_continuation = True
    print(f"  Mock is_continuation (assuming in_list=True): {is_continuation}")
