from docx import Document

def main():
    doc = Document('data/input/Marketing Mix-1 -Formatted.docx')
    for idx in range(146, 155):
        p = doc.paragraphs[idx]
        numPr = p._element.xpath('.//*[local-name()="numPr"]')
        print(f"Paragraph {idx}: text={repr(p.text[:60])}, style={repr(p.style.name)}, has_numPr={bool(numPr)}")
        if numPr:
            numId = p._element.xpath('.//*[local-name()="numId"]/@*[local-name()="val"]')
            ilvl = p._element.xpath('.//*[local-name()="ilvl"]/@*[local-name()="val"]')
            print(f"  numId={numId}, ilvl={ilvl}")

if __name__ == "__main__":
    main()
