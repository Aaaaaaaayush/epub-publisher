import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import re
from app.formatting.formatter import clean_markdown_formatting

raw_text = """### 5.1 Importance of Pricing

Pricing plays a crucial role in business and commerce, as it directly affects an organizations operations, financial stability, and long-term success. Its significance can be highlighted in the following ways:

1.** First Impression:** Price is often the first factor customers consider when evaluating a product or service. Even if buyers are influenced by the overall benefits of the offering, they tend to compare prices with similar alternatives. If the price exceeds what customers are willing or able to pay, they may lose interest altogether.

2.** Setting the Right Level:** Incorrect pricing can negatively impact a business and, in extreme cases, even lead to closure due to insufficient revenue. Hence, conducting detailed market research is essential before finalizing prices.

3.** Boosting Sales:** Reducing prices is a common strategy to increase sales volume. Sales managers may recommend lowering prices to attract more buyers and generate higher demand.

4.** Flexibility in Marketing Mix:** Compared to product, place, and promotion, price is the most adaptable element of the marketing mix. It can be adjusted quickly in response to factors such as consumer perception, inflation, market conditions, and production costs.

5.** Profitability:** Pricing directly affects revenue streams and profit margins. By setting an optimal price, businesses can ensure that sales revenues exceed overall costs, thereby strengthening profitability.

6.** Competitive Advantage:** Effective pricing strategies allow businesses to stand out in the market. Whether through affordability, perceived value, or premium quality, the right pricing can create a distinct competitive edge."""

cleaned = raw_text
print("0. Input '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = cleaned.replace('\xa0', ' ')
cleaned = cleaned.replace('\u200b', '')
print("0a '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*\*([^*]+?)\*\*', r'\1 **\2**', cleaned, flags=re.MULTILINE)
print("0b '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'\*\* +([^*]+?)\*\*', r' **\1**', cleaned)
print("0c opening '2.':", [line for line in cleaned.split("\n") if "Setting" in line])
cleaned = re.sub(r'\*\*([^*]+?) +\*\*', r'**\1** ', cleaned)
print("0c closing '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'\*\*([.,;:!?\(\)\[\]\"\'\-\/\\&\$\#\@\-\+])\*\*', r'\1', cleaned)
cleaned = re.sub(r'\*\*\:\*\*', ':', cleaned)
cleaned = re.sub(r'\*\*\.\*\*', '.', cleaned)
cleaned = re.sub(r'\*\*\:\-\*\*', ':-', cleaned)
cleaned = re.sub(r'\*\*\-\*\*', '-', cleaned)
print("1 '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

while True:
    next_text = re.sub(r'\*\*([^* \t\n][^*]*?)\*\*([ \t]*)\*\*([^* \t\n][^*]*?)\*\*', r'**\1\2\3**', cleaned)
    if next_text == cleaned:
        break
    cleaned = next_text
print("2 '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'\*\*([\d.]+)\*\*([.\d]+)', r'**\1\2**', cleaned)
cleaned = re.sub(r'([\d.]+)\*\*([.\d]+)\*\*', r'**\1\2**', cleaned)
print("3 '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'(?<!\*)\*\*+[ \t]*\*\*+(?!\*)', '', cleaned)
cleaned = re.sub(r'(?<!\*)\*[ \t]+\*(?!\*)', '', cleaned)
print("4 '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'\(\s*\)', '', cleaned)
print("5 '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(
    r'\*\*([^*]+)\*\*\s*(\:\-|\:)\s*',
    lambda m: f"**{m.group(1).strip()}{m.group(2)}** ",
    cleaned
)
print("6 '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(
    r'([a-zA-Z0-9])\*\*+\s*\)\s*([^*]+)\*\*+',
    lambda m: f"{m.group(1)}) **{m.group(2).strip()}**",
    cleaned
)
print("6b '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'(?<!\*)\*\*([^*]+?)\*\*(?=[a-zA-Z0-9])', r'**\1** ', cleaned)
print("6c '2.':", [line for line in cleaned.split("\n") if "Setting" in line])

cleaned = re.sub(r'\*\* +([^*]+?)\*\*', r' **\1**', cleaned)
print("6d opening '2.':", [line for line in cleaned.split("\n") if "Setting" in line])
cleaned = re.sub(r'\*\*([^*]+?) +\*\*', r'**\1** ', cleaned)
print("6d closing '2.':", [line for line in cleaned.split("\n") if "Setting" in line])
