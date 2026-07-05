import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.formatting.formatter import clean_markdown_formatting

examples = [
    "** Meaning:**",
    "** Philip Kotler**",
    "1.** First Impression:**",
    "2.** Setting the Right Level:**",
    "####** 5.3.1 Importance of Price Decision**",
    "###** 5.4 Pricing Policies**",
]

for ex in examples:
    cleaned = clean_markdown_formatting(ex)
    print(f"Original: {repr(ex)}")
    print(f"Cleaned : {repr(cleaned)}")
    print("-" * 40)
