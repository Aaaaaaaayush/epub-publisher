import sys
from pathlib import Path
from docx import Document

def test():
    docx_path = Path("d:/agentic_workflow/docs/Marketing Mix-1 -Formatted.docx")
    doc = Document(str(docx_path))
    num_part = doc.part.numbering_part
    
    class DummyExtractor:
        def __init__(self, doc):
            self.doc = doc
            
        def get_list_details(self, p):
            numPr = p._element.xpath('.//*[local-name()="numPr"]')
            if numPr:
                ilvl_el = p._element.xpath('.//*[local-name()="ilvl"]/@*[local-name()="val"]')
                level = int(ilvl_el[0]) if ilvl_el else 0
                
                numId_el = p._element.xpath('.//*[local-name()="numId"]/@*[local-name()="val"]')
                numId_val = numId_el[0] if numId_el else "0"
                
                list_type = 'bullet'
                try:
                    num_part = self.doc.part.numbering_part
                    if num_part:
                        nums = num_part.element.xpath(f'//*[local-name()="num" and @*[local-name()="numId"]="{numId_val}"]')
                        if nums:
                            abs_ids = nums[0].xpath('.//*[local-name()="abstractNumId"]/@*[local-name()="val"]')
                            if abs_ids:
                                abs_id = abs_ids[0]
                                abs_nums = num_part.element.xpath(f'//*[local-name()="abstractNum" and @*[local-name()="abstractNumId"]="{abs_id}"]')
                                if abs_nums:
                                    numFmts = abs_nums[0].xpath(f'.//*[local-name()="lvl" and @*[local-name()="ilvl"]="{level}"]/*[local-name()="numFmt"]/@*[local-name()="val"]')
                                    if numFmts:
                                        numFmt = numFmts[0].lower()
                                        if numFmt != 'bullet':
                                            list_type = 'number'
                except Exception as e:
                    pass
                return True, level, list_type
            return False, 0, ''

    ext = DummyExtractor(doc)
    blocks = []
    in_list = False
    active_level = 0
    active_list_type = ''

    for idx in range(1049, 1062):
        p = doc.paragraphs[idx]
        is_list, level, list_type = ext.get_list_details(p)
        style_name = p.style.name
        
        if p.style.name.startswith('Heading'):
            if in_list:
                blocks.append('')
                in_list = False
            blocks.append(f'#### {p.text}')
            continue
            
        if is_list:
            in_list = True
            active_level = level
            active_list_type = list_type
            indent = '  ' * level
            prefix = '- ' if list_type == 'bullet' else '1. '
            blocks.append(f'{indent}{prefix}**{p.text}**')
            continue
            
        if in_list and style_name == 'List Paragraph':
            indent = '  ' * active_level + '   '
            blocks.append(f'{indent}{p.text}')
            continue
            
        if in_list:
            blocks.append('')
            in_list = False
        blocks.append(p.text)

    print('\n'.join(blocks))

if __name__ == "__main__":
    test()
