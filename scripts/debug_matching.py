import re

raw_text = """### 5.1 Importance of Pricing

Pricing plays a crucial role in business and commerce, as it directly affects an organizations operations, financial stability, and long-term success. Its significance can be highlighted in the following ways:

1.** First Impression:** Price is often the first factor customers consider when evaluating a product or service. Even if buyers are influenced by the overall benefits of the offering, they tend to compare prices with similar alternatives. If the price exceeds what customers are willing or able to pay, they may lose interest altogether.

2.** Setting the Right Level:** Incorrect pricing can negatively impact a business and, in extreme cases, even lead to closure due to insufficient revenue. Hence, conducting detailed market research is essential before finalizing prices.

3.** Boosting Sales:** Reducing prices is a common strategy to increase sales volume. Sales managers may recommend lowering prices to attract more buyers and generate higher demand."""

# Test prefix spacing regex on the full multiline raw_text
print("1. Testing re.findall on raw_text:")
matches = re.findall(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*\d+\)|\s*[a-zA-Z]\))\*\*([^*]+?)\*\*', raw_text, flags=re.MULTILINE)
print("Matches:", matches)

print("\n2. Testing re.sub on raw_text:")
subbed = re.sub(r'^(\s*\d+\.|\s*[a-zA-Z]\.|\s*[a-zA-Z]\))\*\*([^*]+?)\*\*', r'\1 **\2**', raw_text, flags=re.MULTILINE)
print("Subbed contains '2. ** Setting'?:", "2. ** Setting" in subbed)
print("Subbed line 2:", repr([line for line in subbed.split("\n") if "Setting" in line]))
