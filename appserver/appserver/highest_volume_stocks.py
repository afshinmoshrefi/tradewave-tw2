# this script maintainss 2 csv files for highest volume and highest volume spikes
# they are saved in the same folder as US csvs under data and used by post processing in article generation and when volume spikes are needed
#
# this needs to run daily with crontab - at midnight

import sys
import os
import requests
from datetime import datetime, timedelta
sys.path.insert(0, '/home/flask')
import config


DAYS_OLD_STALE = 10 # number of days for the last row to consider it stale


def get_highest_volume_US_stocks(limit: int = 100, days: int = 30):
    csv_folder = os.path.join(config.csv_folder, 'US')
    results = []  # (ticker, avg_vol, today_vol, rvol)

    MIN_PRICE = 5.0          # min price for volume spikes
    MIN_AVG_VOL = 5_000_000  # min volume for volume spikes

    for fname in os.listdir(csv_folder):
        if not fname.lower().endswith('.csv'):
            continue

        ticker = fname[:-4]  # strip .csv
        fpath = os.path.join(csv_folder, fname)

        last_rows = []
        with open(fpath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                last_rows.append(line)

        if len(last_rows) < days:
            continue

        recent = last_rows[-days:]

        vols = []
        for row in recent:
            parts = row.split(',')
            if len(parts) < 7:
                continue
            try:
                volume = int(parts[6])
                vols.append(volume)
            except ValueError:
                continue

        if not vols:
            continue

        avg_vol = sum(vols) / len(vols)

        # Last row = today's data
        last_parts = last_rows[-1].split(',')
        
        if len(last_parts) < 7:
            continue








        # Check if data is stale (first column is date YYYY-MM-DD)
        try:
            last_date_str = last_parts[1]
            last_date = datetime.strptime(last_date_str, '%Y-%m-%d')
            days_old = (datetime.now() - last_date).days
            if days_old > DAYS_OLD_STALE:
                continue  # Skip stale data
                
        except (ValueError, IndexError):
            continue  # Skip if date parsing fails






        try:
            today_vol = int(last_parts[6])
            last_close = float(last_parts[5])
        except ValueError:
            continue

        # Basic liquidity + price filter
        if avg_vol < MIN_AVG_VOL or last_close < MIN_PRICE:
            continue

        rvol = today_vol / avg_vol if avg_vol > 0 else 0.0
        results.append((ticker, avg_vol, today_vol, rvol))

    # ---------------- TOP AVG VOLUME ----------------
    results_by_avg = sorted(results, key=lambda x: x[1], reverse=True)
    top_avg = results_by_avg[:limit]

    csv_folder = os.path.join(config.csv_folder, 'US')

    out_path1 = os.path.join(csv_folder, 'highest_volume_list.csv')
    with open(out_path1, 'w') as f:
        f.write('rank,ticker,avg_volume_30d,today_volume,rvol\n')
        for idx, (ticker, avg_vol, today_vol, rvol) in enumerate(top_avg, start=1):
            f.write(f'{idx},{ticker},{int(avg_vol)},{today_vol},{rvol:.2f}\n')

    # ---------------- TOP VOLUME SPIKES ----------------
    results_by_rvol = sorted(results, key=lambda x: x[3], reverse=True)
    top_spikes = results_by_rvol[:limit]

    out_path2 = os.path.join(csv_folder, 'highest_volume_spikes.csv')
    with open(out_path2, 'w') as f:
        f.write('rank,ticker,avg_volume_30d,today_volume,rvol\n')
        for idx, (ticker, avg_vol, today_vol, rvol) in enumerate(top_spikes, start=1):
            f.write(f'{idx},{ticker},{int(avg_vol)},{today_vol},{rvol:.2f}\n')

    return top_avg, top_spikes


# ----------------------------------------------------------------
if __name__ == "__main__":
    top_avg, top_spikes = get_highest_volume_US_stocks()

    # Format payload rows for sending to the webserver
    hv_rows = [
        [idx + 1, t, int(avg), today, round(rvol, 2)]
        for idx, (t, avg, today, rvol) in enumerate(top_avg)
    ]

    hs_rows = [
        [idx + 1, t, int(avg), today, round(rvol, 2)]
        for idx, (t, avg, today, rvol) in enumerate(top_spikes)
    ]

    payload = {
        "highest_volume": hv_rows,
        "highest_spikes": hs_rows
    }

    # e.g. config.blog_queue_server = "http://10.0.0.5/"  (with trailing slash)
    url = f'{config.blog_queue_server}update_volume_lists'

    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=5
        )
        resp.raise_for_status()
        print("Successfully updated webserver volume lists.")
    except Exception as e:
        print("Failed to update webserver volume lists:", e)

    print("Top avg volume:", top_avg[:5])
    print("Top volume spikes:", top_spikes[:5])