from appserver import OppList4
import sys
sys.path.insert(0, '/home/flask')
import config
import requests
from pprint import pprint


def get_keyprovider_token():
    url = config.appserver_url+'/login/2/3/4/5/6'
    api_result = requests.get(url)
    result = api_result.json()
    t = result['message'].split(' ')
    return t[4]


# after logging in, the returned token is used to make other calls to the appserver
def login_appserver(keyprovider_token):
    url = config.appserver_url+'/login/28/3/4/5/'+keyprovider_token
    api_result = requests.get(url)
    result = api_result.json()
    return result['token']

def get_opp_list(group_id, month, day, years, pyears,day_range,appserver_token):
    urlX = config.appserver_url+'/OppList4/'+str(group_id)+'/'+month+'/'+day+'/'+str(years)+'/'+str(pyears)+'/'+day_range+'/0/0?token='+appserver_token
    
    print('urlX:',urlX,'\n\n')

    api_result = requests.get(urlX)

    # Debugging: Log the raw response
    print("URL:", urlX)
    # print("Response Code:", api_result.status_code)
    # print("Response Text:", api_result.text)

    if api_result.status_code != 200:
        raise ValueError(f"API returned non-200 status: {api_result.status_code}")
    
    try:
        result = api_result.json()
        return result
    except ValueError:
        raise ValueError(f"Invalid JSON response: {api_result.text}")




if __name__ == "__main__":
    # Test messages

    keyprovider_token = get_keyprovider_token()
    appserver_token = login_appserver(keyprovider_token)

    result = get_opp_list(1, 'January', '4', 10, 10, '-', appserver_token)
    pprint(result['OppList'])
