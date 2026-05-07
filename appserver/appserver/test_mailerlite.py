# apigate setting in ump need to turn on api : Activate/Hold "Get all User Data" API Call
import redis
import json
import sys
import requests
import pprint
import mailerlite as MailerLite
import pprint
import datetime
from datetime import timedelta


sys.path.insert(0, '/home/flask')
import config

mailerlite_token = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiI0IiwianRpIjoiZDlmZDkxMjBkMmZlM2Y3MWZjNTM3MWExNzg2NTcxOTQ4ZWE4MDE5NWY4YjJkMzg4Njc3ODJlN2MzMmMxNzk4OWE5NDQ5YWFkZGQ3MDQ2ZGUiLCJpYXQiOjE2ODc3NDU5NDkuMzk1NzA1LCJuYmYiOjE2ODc3NDU5NDkuMzk1NzA4LCJleHAiOjQ4NDM0MTk1NDkuMzkwNDQ5LCJzdWIiOiI1MTg1NDEiLCJzY29wZXMiOltdfQ.E-vmUP8mcjPuewbK_DHyG8j5f03vkDeJ0mrkbnYGW5XuTl-sYeaiV6dP1-LrlH6_ttxn8Xnpgknc75uuWo7KM-PDNfOdXRzjCqZ5VSLGuIJ3d-7inp54JvGeULiMK5xX0AW4EDC-_1v5QdrIOeqCmrczXNhLD_N5dXrKffNg7Wx1KlLyZVBPhKtmJEZF-fcUUcFS1YV2TC44KTTbJRoEwoYKnTwb2zp4xJT1BxypNrmoM_rFc-K4SIendD8_F37-2cDUV3TT_BmTBL0WBTN4JS5hraBfspR95AmcHW16fBAt8_XdzgKP4ctIYDyowwNb7MMlqX49zvyPdcoz0X2omudxXQNcOc2WVIPm-MBpcMf1RR6FOVYJFsCIuaR_7tMWNSjMTpKK1D4keDFLlEzUX2NXdVIcK5yWp7O30ZtoSgEKJgjh64RJKl9yChFOSssL5CDKzUa0XccSk45I6aLPwr62Bl3dCAsqDHAvX2-V0sWdkLcROkfO0PFz-bdxjrdxBrS3q6-0zG01J_BRXq4PycAxYjHQXIv_VZB6jcvIeD2s-3ZgXq9vH95Xo-3PXmReuxYt9Kdq1VQY7QNBl6FOyky1xv3sChgnIIkvv1OeF-sS5c0CEr_7vDOuLhM48HPtB8l9GEUpb7OMJ4k-hr7sPqf6kwK9dve4WAD5YoFtAsk'
#-----------------------------------------------------------------------------------------------------
def create_subscriber(email,first_name,last_name,ip,optin_ip):
    client = MailerLite.Client({'api_key': mailerlite_token })
    response = client.subscribers.create(email, fields={'name': first_name, 'last_name': last_name}, ip_address=ip, optin_ip=optin_ip)
    return response
#-----------------------------------------------------------------------------------------------------
def get_list_subscribers():
    client = MailerLite.Client({'api_key': mailerlite_token })
    response = client.subscribers.list(limit=10, page=1, filter={'status': 'active'})
    return response
#-----------------------------------------------------------------------------------------------------
def create_campaign(campaign_name,subject,from_name,from_email,content):
    client = MailerLite.Client({'api_key': mailerlite_token })

    params = {
    "name": campaign_name,
    "language_id": 4,
    "type": "regular",
    "emails": [{
            "subject": subject,
            "from_name": from_name,
            "from": from_email,
            "content": content
        }]
    }

    response = client.campaigns.create(params)
    pprint.pprint(response['data'])
    campaign_id   = int(response['data']['id'])
    campaign_time = response['data']['created_at']
    return campaign_id,campaign_time
#-----------------------------------------------------------------------------------------------------
def schedule_campaign(campaign_id,send_date,send_hour,send_minute):
    client = MailerLite.Client({'api_key': mailerlite_token })

    params = {
        "delivery": "scheduled",
        "schedule": {
            "date": send_date,
            "hours": send_hour,
            "minutes": send_minute
        }
    }
    print('scheduling')
    response = client.campaigns.schedule(campaign_id, params)
    print(response)
#-----------------------------------------------------------------------------------------------------
def today_date_hour_min():
    dt=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(dt)

    d = dt[:10]
    h = dt[11:13]
    m = dt[14:16]

    return d,h,m

#-----------------------------------------------------------------------------------------------------
def future_date_hour_min(num_minutes):
    dt=datetime.datetime.now()
    future_datetime = dt + timedelta(minutes=num_minutes)
    fdate = future_datetime.strftime("%y-%m-%d")
    
    # Format the time as '%H:%M:%S'
    ftime = future_datetime.strftime("%H:%M:%S")

    d = fdate[:10]
    h = ftime[:2]
    m = ftime[3:5]

    return d,h,m
#-----------------------------------------------------------------------------------------------------
campaign_id,campaign_date_time = create_campaign('my test campaign','test subject','afshin desk','afshin@tradeseasonals.com','test content')
print(campaign_id,campaign_date_time)

d,h,m=future_date_hour_min(2) # get date hour and min of # minutes from now, whatever minutes number is passed.

schedule_campaign (campaign_id,d,h,m) # must schedule to send