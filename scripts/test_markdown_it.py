from markdown_it import MarkdownIt

def main():
    md = MarkdownIt("commonmark").enable("table")
    
    text = """1. **Raw Materials**

    Raw materials are the **basic inputs or natural resources** required for industrial production. They form the foundation of the manufacturing process.

    They can be further divided into:

        - **Agricultural-based raw materials**  such as cotton, sugarcane, and timber.**Extractive-based raw materials** like coal, crude oil, iron ore, and minerals.

            **Example:** Cotton used by textile mills for producing fabric; crude oil processed by refineries into petroleum products."""
            
    print("=== COMMONMARK ===")
    print(md.render(text))
    
    print("=== GFM-LIKE (DEFAULT) ===")
    md_gfm = MarkdownIt().enable("table")
    print(md_gfm.render(text))

if __name__ == '__main__':
    main()
