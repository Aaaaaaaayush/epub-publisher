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

print("Testing clean_markdown_formatting on the full block:")
cleaned = clean_markdown_formatting(raw_text)
lines = cleaned.split("\n")
for idx, line in enumerate(lines):
    if "Setting" in line or "Impression" in line:
        print(f"Line {idx}: {repr(line)}")
