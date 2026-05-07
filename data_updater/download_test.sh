: "${EOD_TOKEN:?EOD_TOKEN not set; source /etc/tradewave/secrets.env}"
for i in `cat tickers.txt`; do wget "https://eodhd.com/api/eod/$i.US?api_token=${EOD_TOKEN}&order=d&fmt=csv&from=1900-01-01" -O 1/$i.csv; done;

