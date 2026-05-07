# apigate setting in ump need to turn on api : Activate/Hold "Get all User Data" API Call
import redis
import json
import sys
import requests
import pprint

sys.path.insert(0, '/home/flask')
import config

mailerlite_token = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiI0IiwianRpIjoiZDlmZDkxMjBkMmZlM2Y3MWZjNTM3MWExNzg2NTcxOTQ4ZWE4MDE5NWY4YjJkMzg4Njc3ODJlN2MzMmMxNzk4OWE5NDQ5YWFkZGQ3MDQ2ZGUiLCJpYXQiOjE2ODc3NDU5NDkuMzk1NzA1LCJuYmYiOjE2ODc3NDU5NDkuMzk1NzA4LCJleHAiOjQ4NDM0MTk1NDkuMzkwNDQ5LCJzdWIiOiI1MTg1NDEiLCJzY29wZXMiOltdfQ.E-vmUP8mcjPuewbK_DHyG8j5f03vkDeJ0mrkbnYGW5XuTl-sYeaiV6dP1-LrlH6_ttxn8Xnpgknc75uuWo7KM-PDNfOdXRzjCqZ5VSLGuIJ3d-7inp54JvGeULiMK5xX0AW4EDC-_1v5QdrIOeqCmrczXNhLD_N5dXrKffNg7Wx1KlLyZVBPhKtmJEZF-fcUUcFS1YV2TC44KTTbJRoEwoYKnTwb2zp4xJT1BxypNrmoM_rFc-K4SIendD8_F37-2cDUV3TT_BmTBL0WBTN4JS5hraBfspR95AmcHW16fBAt8_XdzgKP4ctIYDyowwNb7MMlqX49zvyPdcoz0X2omudxXQNcOc2WVIPm-MBpcMf1RR6FOVYJFsCIuaR_7tMWNSjMTpKK1D4keDFLlEzUX2NXdVIcK5yWp7O30ZtoSgEKJgjh64RJKl9yChFOSssL5CDKzUa0XccSk45I6aLPwr62Bl3dCAsqDHAvX2-V0sWdkLcROkfO0PFz-bdxjrdxBrS3q6-0zG01J_BRXq4PycAxYjHQXIv_VZB6jcvIeD2s-3ZgXq9vH95Xo-3PXmReuxYt9Kdq1VQY7QNBl6FOyky1xv3sChgnIIkvv1OeF-sS5c0CEr_7vDOuLhM48HPtB8l9GEUpb7OMJ4k-hr7sPqf6kwK9dve4WAD5YoFtAsk'



redis_client  = redis.Redis(host='localhost', port=6379, db=0)  # used as a cache
redis_client2 = redis.Redis(host='localhost', port=6379, db=2)  # used as a db


def get_keys(): # get key1 and key2 from keystore url
    response = requests.get(config.keystoreURL)
    json = response.json()
    key1 = json['key1']
    key2 = json['key2']

    return key1,key2

#-------------------------------------------------------

userid          =  3 #1,3,15,16,

redis_key_email_settings = f'user_email_settings_{userid}' # this is a json version of a list of dictionaries
redis_user_email_settings = redis_client2.get(redis_key_email_settings)

print(redis_user_email_settings)

keys = redis_client2.keys('user_email_settings_*')

_,ump_key = get_keys()

# get all the users - if email is missing get it from ump with apigate
# get all user email settings and create a user list for the email operation
users_to_email = []
if len(keys) > 0 :
    for k in keys:
        kd = k.decode() # convert byte to string
        user_bytes=redis_client2.get(kd)
        if user_bytes is not None:
            user_dict = json.loads(user_bytes)
            # check if user_dict has the following keys: email, first_name, last_name, tags - if not add it
            if 'email' not in user_dict: # get this info from UMP APIGet in wordpress
                user_id = int( kd.rsplit('_',1)[-1])
                print('no email key',user_id)

                ump_url = f'{config.wordpress_url}?ihc_action=api-gate&ihch={ump_key}&action=user_get_details&uid={user_id}'
                response = requests.get(ump_url)
                d=response.json()
                
                first_name = d['response']['first_name']
                last_name = d['response']['last_name']
                email = d['response']['user_email']
                # add the 3 values to the user dictionary 
                user_dict['first_name']=first_name
                user_dict['last_name']=last_name
                user_dict['email']=email
                # set it back in redis to save the email and firstname and lastname 
                redis_client2.set(kd,json.dumps(user_dict))
                # add this user to the email provider's list



print(keys)