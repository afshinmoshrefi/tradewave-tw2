# add status field to user_reports_{userid} - this only adds status if its missing

import redis
import json
import sys
import requests
import pprint

sys.path.insert(0, '/home/flask')
import config




redis_client  = redis.Redis(host='localhost', port=6379, db=0)  # used as a cache
redis_client2 = redis.Redis(host='localhost', port=6379, db=2)  # used as a db




redis_key_user_reports  = f'user_reports_16'
redis_user_reports_list = redis_client2.get(redis_key_user_reports)
redis_user_reports_list = json.loads(redis_user_reports_list)

# find index for dr_id = 16
dr_id = '16' # the index being updated
idx = [i for i, d in enumerate(redis_user_reports_list) if redis_user_reports_list[i]["dr_id"] == int(dr_id)]
idx = idx[0]

print(redis_user_reports_list[idx])
# orders = '9743731,9740790,9743789'
orders = '735601'
redis_user_reports_list[idx]['orders'] = orders

del redis_user_reports_list[idx]['orders']

redis_client2.set(redis_key_user_reports,json.dumps(redis_user_reports_list)) # set the list to the new list on redis

