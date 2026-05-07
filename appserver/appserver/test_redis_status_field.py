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




keys = redis_client2.keys('user_reports_*')


if len(keys) > 0 :
    for k in keys:
        res = redis_client2.get(k)
        if res is not None:
            user_reports = json.loads(res)
            for r in user_reports:
                if 'status' in r:
                    if r['status'] == 'NaN':
                        r['status'] = '0'
                    else:
                        print('found status')
                else:
                    r['status']='0'
            redis_client2.set(k,json.dumps(user_reports))
            


    for u in user_reports:
        print(u)
        print('')

#         kd = k.decode() # convert byte to string
#         user_bytes=redis_client2.get(kd)
#         if user_bytes is not None:
#             user_dict = json.loads(user_bytes)
#             # check if user_dict has the following keys: email, first_name, last_name, tags - if not add it
#             if 'email' not in user_dict: # get this info from UMP APIGet in wordpress
#                 user_id = int( kd.rsplit('_',1)[-1])
#                 print('no email key',user_id)

#                 ump_url = f'{config.wordpress_url}?ihc_action=api-gate&ihch={ump_key}&action=user_get_details&uid={user_id}'
#                 response = requests.get(ump_url)
#                 d=response.json()
                
#                 first_name = d['response']['first_name']
#                 last_name = d['response']['last_name']
#                 email = d['response']['user_email']
#                 # add the 3 values to the user dictionary 
#                 user_dict['first_name']=first_name
#                 user_dict['last_name']=last_name
#                 user_dict['email']=email
#                 # set it back in redis to save the email and firstname and lastname 
#                 redis_client2.set(kd,json.dumps(user_dict))
#                 # add this user to the email provider's list



# print(keys)