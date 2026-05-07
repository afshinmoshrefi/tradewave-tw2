import requests
import csv
import os

# Set your EODHD API key and desired exchange code
API_KEY = os.environ["EOD_TOKEN"]
EXCHANGE = "ETF"
url = f"https://eodhistoricaldata.com/api/exchange-symbol-list/{EXCHANGE}?api_token={API_KEY}&fmt=csv"

# Download CSV data
response = requests.get(url)
response.raise_for_status()  # Ensure the request was successful

# Process CSV and extract just the first column (symbol)
symbols = []
csv_lines = response.text.splitlines()
reader = csv.reader(csv_lines)
next(reader)  # Skip header
for row in reader:
    if row:  # skip empty rows
        symbols.append(row[0])

# Save symbols to a file, one per line
with open("symbols_"+EXCHANGE+".txt", "w") as f:
    for symbol in symbols:
        f.write(symbol + "\n")

print("Saved", len(symbols), "symbols to tickers.txt")
