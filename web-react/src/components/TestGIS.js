// this example is based on this video by cooper codes - step 1 is to login to google
// https://www.youtube.com/watch?v=roxC8SMs7HU&list=PLtTH-5FuN7VjRG-cShvcTUaCHbSK-0oN0&index=2&t=1s  GIS

// adding example 2 after example 1 above was successfully implemented - step 2 is to get access tokens
// https://www.youtube.com/watch?v=C0DUNy6RjNw&list=PLtTH-5FuN7VjRG-cShvcTUaCHbSK-0oN0&index=1&t=3s  GIS

import React, { useEffect, useState } from 'react'
import jwt_decode from "jwt-decode";



// dev
// const CLIENT_ID = '25262567698-tsaoo718sc35n3k25os074b17jklc5rm.apps.googleusercontent.com';
// prod
const CLIENT_ID = '37066762490-h47l6ar339q0uv3p602jlh5oe88ipqko.apps.googleusercontent.com';

const SCOPES = 'https://www.googleapis.com/auth/calendar';

const TEST_EVENT = {
    'summary': 'Example Event',
    'location': 'New York, NY',
    'description': 'a description for this',
    'start': {
        'dateTime': '2023-03-26T10:00:00-04:00',
        'timeZone': 'America/New_York',
    },
    'end': {
        'dateTime': '2023-03-26T11:00:00-04:00',
        'timeZone': 'America/New_York',
    },
};

const TestGIS = (props) => {


    const [user, setUser] = useState({});
    const [tokenClient, setTokenClient] = useState({});

    function handleCallbackResponse(response) {
        console.log('encoded JWT ID token:' + response.credential);
        var userObject = jwt_decode(response.credential);
        console.log(userObject)
        setUser(userObject);
        document.getElementById('signInDiv').hidden = true;
    }

    function handleSignOut(event) {
        setUser({});
        document.getElementById('signInDiv').hidden = false;
    }


    async function sendEvent () {
        console.log('send event')
        
    }



    useEffect(() => {

        /* global google */
        const google = window.google;
        google.accounts.id.initialize({
            client_id: CLIENT_ID,
            callback: handleCallbackResponse
        })
        google.accounts.id.renderButton(
            document.getElementById('signInDiv'),
            { theme: 'filled_blue', size: 'medium', type:'icon' }
        );

        // google.accounts.id.prompt(); // this is added to popup the login dialog when page is first loaded - didn't work

        // Get Access Token
        // create something called a tokenClient
        setTokenClient(
            google.accounts.oauth2.initTokenClient({
                client_id: CLIENT_ID,
                scope: SCOPES,
                callback: (tokenResponse) => {
                    console.log('tokenResponse=', tokenResponse);
                    // we now have access to a live token to use for ANY google API
                    if (tokenResponse && tokenResponse.access_token) {
                        // create the calendar event here

                        fetch ('https://www.googleapis.com/calendar/v3/calendars/primary/events',{
                            method: 'POST',
                            headers: {
                                'Authorization':'Bearer '+tokenResponse.access_token
                            },
                            body:JSON.stringify(TEST_EVENT)
                        }).then((data) => {
                            return data.json();
                        }).then((data) => {
                            console.log(data);
                            alert('event created check google calendar')
                        })  

                    }
                }
            })
        );



    }, []);


    function createCalendarEvent() {
        tokenClient.requestAccessToken();
    }




    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div className='main-cover' style={{ backgroundColor: 'lightblue', width: '100%', height: '100%', zIndex: '10000' }}   >

            <div id="signInDiv"></div>
            {Object.keys(user).length != 0 &&
                <button onClick={(e) => handleSignOut(e)}>Sign Out</button>
            }

            {user &&
                <div>
                    <img src={user['picture']}></img>
                    <h3>{user.name}</h3>
                    <button onClick={() => createCalendarEvent()}>Create calendar event</button>
                </div>
            }

        </div>


    )
}
export default TestGIS
