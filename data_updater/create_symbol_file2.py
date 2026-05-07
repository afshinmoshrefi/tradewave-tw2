import requests
import csv
import os

# Set your EODHD API key and desired exchange code
API_KEY = os.environ["EOD_TOKEN"]
EXCHANGE = "US"
url = f"https://eodhistoricaldata.com/api/exchange-symbol-list/{EXCHANGE}?api_token={API_KEY}&fmt=csv"

def abbreviate_name(name, max_len=50):
    # Common abbreviations
    abbreviations = {
        "Corporation": "Corp.",
        "Company": "Co.",
        "Incorporated": "Inc.",
        "Limited": "Ltd.",
        "Trust": "Tr.",
        "Fund": "Fd.",
        "ETF": "ETF",
        "Capital": "Cap.",
        "International": "Intl.",
        "Group": "Grp.",
        "Holdings": "Hldgs.",
        "Management": "Mgmt.",
        "Partners": "Prtnrs.",
    }

    for long, short in abbreviations.items():
        # replace only whole-word matches
        name = name.replace(long, short)
    return name

#-------------------------------------------------------------------

# Download CSV data
response = requests.get(url)
response.raise_for_status()  # Ensure the request was successful

# Parse the CSV from the response
csv_lines = response.text.splitlines()
reader = csv.DictReader(csv_lines)

# Prepare output CSV
output_file = f"symbols_{EXCHANGE}.csv"
with open(output_file, "w", newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(["symbols", "name"])
    for row in reader:
        # EODHD uses 'Code' for symbol and 'Name' for company/ETF name
        symbol = row.get("Code", "").strip()
        name = row.get("Name", "").strip()

        if len(name) > 50:
            name = abbreviate_name(name)

        if symbol and name:
            writer.writerow([symbol, name])

print(f"Saved symbol list to {output_file}")
