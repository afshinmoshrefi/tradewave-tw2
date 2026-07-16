# implemeted a file based cache for the seasonal chart data
# some of the longer years we have takes a long time over and over again
# noticed it specially when the demo is on 96 years of SPX or very high numbers of seasonal charts that take for ever
# also it's so much faster to load from a file than to be recalculated
# redis does do it quick but the cache memory for redis is limited so it gets flushed out freqently.
# the server get crushed when multiple users are looking at long years of data and trend charts are being calculated
# so now it should only be calculated once a year -

# the cache must be flushed at the end of the year and the start of the new year

import os
import json
import logging
import datetime
import sys
import threading
# Add the parent directory to the system path
sys.path.insert(0, '/home/flask')
import config

# Assume SEASONAL_CHART_CACHE_DIR is defined in config
SEASONAL_CHART_CACHE_DIR = config.cache_folder

def get_file_cache_path(redis_key):
    """
    Generates a file path for the given Redis key.
    """
    safe_key = redis_key.replace(':', '_').replace('/', '_')  # Replace characters to create a safe filename
    return os.path.join(SEASONAL_CHART_CACHE_DIR, f"{safe_key}.json")
#------------------------------------------------------------------------------------------------------------
def load_from_file_cache(redis_key):
    """
    Loads cached data from a file based on the Redis key.
    Returns None if the file does not exist, is outdated, or fails to load.
    """
    file_path = get_file_cache_path(redis_key)
    if os.path.isfile(file_path):
        try:
            # Get the file's creation time
            creation_time = os.path.getctime(file_path)
            creation_year = datetime.datetime.fromtimestamp(creation_time).year
            current_year = datetime.datetime.now().year

            logging.debug(f"Cache file '{file_path}' was created in {creation_year}.")

            if creation_year == current_year:
                with open(file_path, 'r') as f:
                    logging.debug(f"Loading cache from file: {file_path}")
                    return json.load(f)
            else:
                # Cache file is outdated; delete it
                os.remove(file_path)
                logging.info(f"Deleted outdated cache file: {file_path}")
        except Exception as e:
            logging.error(f"Failed to load or delete cache file {file_path}: {e}")
    else:
        logging.debug(f"No cache file found at: {file_path}")
    return None
#------------------------------------------------------------------------------------------------------------
def save_to_file_cache(redis_key, data):
    """
    Saves data to a file-based cache.
    """
    file_path = get_file_cache_path(redis_key)
    temp_path = f"{file_path}.tmp.{os.getpid()}.{threading.get_ident()}"
    try:
        with open(temp_path, 'w') as f:
            json.dump(data, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, file_path)
        logging.debug(f"Saved cache to file: {file_path}")
    except Exception as e:
        logging.error(f"Failed to save cache to file {file_path}: {e}")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logging.warning(f"Failed to remove temporary cache file {temp_path}")
#------------------------------------------------------------------------------------------------------------
# Ensure the cache directory exists
if not os.path.exists(SEASONAL_CHART_CACHE_DIR):
    os.makedirs(SEASONAL_CHART_CACHE_DIR, exist_ok=True)
    logging.debug(f"Created cache directory at {SEASONAL_CHART_CACHE_DIR}")
