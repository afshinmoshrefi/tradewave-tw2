# migrate_opp_records_year_pe.py
# Migrates legacy PE year records (e.g., 'pe2') to new format (e.g., 'pe2-16')

import redis
import json
import sys

sys.path.insert(0, '/home/flask')
from get_symbol_csv import get_symbol_csv
import config

redis_client2 = redis.Redis(host='localhost', port=6379, db=2)  # used as a db


def getStockMetaData(resourceID, symbol):
    """Get first and last year of available data for a symbol"""
    exchange = config.exchange_mapping[resourceID]
    result = get_symbol_csv(symbol, exchange)
    
    if isinstance(result, str):
        return None, None  # Error case
    
    df = result
    y1 = int(df.iloc[0]['date'][:4])   # First year
    y2 = int(df.iloc[-1]['date'][:4])  # Last year
    
    return y1, y2


def count_pe_years(y1, y2, pe_num):
    """Count how many completed years in range match the PE cycle (excludes current year)"""
    count = 0
    for yr in range(y1, y2):  # y2 (current year) is excluded - it hasn't happened yet
        if yr % 4 == pe_num:
            count += 1
    return count


def migrate_records(dry_run=True):
    """
    Migrate legacy PE records to new format.
    
    Args:
        dry_run: If True, only print what would change. If False, actually update Redis.
    """
    
    if dry_run:
        print("=" * 60)
        print("DRY RUN - No changes will be made")
        print("=" * 60)
    else:
        print("=" * 60)
        print("LIVE RUN - Changes will be saved to Redis")
        print("=" * 60)
    
    print()
    
    keys = redis_client2.keys('user_reports_*')
    
    total_migrated = 0
    total_errors = 0
    
    if len(keys) > 0:
        for k in keys:
            res = redis_client2.get(k)
            if res is not None:
                user_reports = json.loads(res)
                user_key = k.decode() if isinstance(k, bytes) else k
                records_changed = False
                
                for r in user_reports:
                    years = r['years']
                    resource_id = r['resourceID']
                    symbol = r['symbol']
                    
                    # Check if this is a legacy PE record (has 'pe' but no '-')
                    if 'pe' in years.lower() and '-' not in years:
                        pe_num = int(years[2])  # 'pe2' -> 2
                        
                        # Get data range for this symbol
                        y1, y2 = getStockMetaData(resource_id, symbol)
                        
                        if y1 is None or y2 is None:
                            print(f"  ERROR: Could not get data for {symbol}")
                            total_errors += 1
                            continue
                        
                        # Count PE years
                        max_pe_years = count_pe_years(y1, y2, pe_num)
                        
                        # Build new value
                        old_years = years
                        new_years = f"{years.lower()}-{max_pe_years}"
                        
                        print(f"  {user_key}")
                        print(f"    Symbol: {symbol}")
                        print(f"    Data range: {y1} - {y2}")
                        print(f"    BEFORE: {old_years}")
                        print(f"    AFTER:  {new_years}")
                        print()
                        
                        # Update the record
                        r['years'] = new_years
                        records_changed = True
                        total_migrated += 1
                
                # Save back to Redis if not dry run and records changed
                if not dry_run and records_changed:
                    redis_client2.set(k, json.dumps(user_reports))
    
    print("=" * 60)
    print(f"Total records to migrate: {total_migrated}")
    print(f"Total errors: {total_errors}")
    print("=" * 60)
    
    if dry_run and total_migrated > 0:
        print()
        print("To apply these changes, run with dry_run=False")


if __name__ == '__main__':
    # Parse command line argument
    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        migrate_records(dry_run=False)
    else:
        print("Usage:")
        print("  python migrate_opp_records_year_pe.py          # Dry run (preview changes)")
        print("  python migrate_opp_records_year_pe.py --live   # Apply changes")
        print()
        migrate_records(dry_run=True)