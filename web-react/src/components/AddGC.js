// AddGC is the dialog that displays when user clicks the add to google calendar icon in Opportunities Manager 
// Is uses the new GIS authentication method to communicate with Google Calendar

// about loading date to javascript:  d = new Date(d)
// I add time of 6AM to it and the timezone offset of the local time
// otherwise, it would screwup when calculating date to the next monday

// console.cloud.google.com to setup the APIs

import React, { useEffect, useState, useContext, useRef } from 'react';
import jwt_decode from "jwt-decode";
import { UserContext } from './UserContext'
import './styles/InfoPopup.css';
import CheckBox from './CheckBox';
// import TextBox from './TextBox';
import { getAllEventTimes, themeColors } from './Common'
import SelectBox from './SelectBox'
import { getCookie, setCookie } from './Common'
import { GrClose } from "react-icons/gr";
import { google_logo} from './Common';



// process.env.REACT_APP_CLIENT_ID
// process.env.REACT_APP_SCOPES

// const CLIENT_ID = process.env.REACT_APP_CLIENT_ID
// const SCOPES = process.env.REACT_APP_SCOPES
const src = 'https://accounts.google.com/gsi/client'
                     
const CLIENT_ID_DEV='25262567698-tsaoo718sc35n3k25os074b17jklc5rm.apps.googleusercontent.com'
const CLIENT_ID_STAGE='234718616773-7pbj86h6co2q900lnab9i2lra0e1m946.apps.googleusercontent.com'
const CLIENT_ID_PROD1='37066762490-h47l6ar339q0uv3p602jlh5oe88ipqko.apps.googleusercontent.com' // afshinmoshrefi@gmail version
const CLIENT_ID_PROD2='914262652560-gbih917rcpp57gfci0v94es7bu9k42uu.apps.googleusercontent.com'  // tradeseasonals@gmail version

const CLIENT_ID = CLIENT_ID_PROD2;


const SCOPES = 'https://www.googleapis.com/auth/calendar';

const TEST_EVENT = {
    'summary': 'Example Event',
    'location': 'New York, NY',
    'description': 'a description for this',
    'start': {
        'dateTime': '2023-03-27T10:00:00-04:00',
        'timeZone': Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
    'end': {
        'dateTime': '2023-03-27T11:00:00-04:00',
        'timeZone': Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
};


const loadScript = (src) =>
    new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) return resolve()
        const script = document.createElement('script')
        script.src = src
        script.onload = () => resolve()
        script.onerror = (err) => reject(err)
        document.body.appendChild(script)
    })



const AddGC = (props) => {

    const { browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    const EVENT_TIMES_LIST = getAllEventTimes(); // this function creates a list of objects of 48 times throught out the day seperated by 30 minutes
    const local_timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

    // const local_timezone_offset = Intl.DateTimeFormat().resolvedOptions().timeZoneOffset;

    function local_timezone_offset() { // timezone offset in for of -04:00 to be added to the end of date time string for time zone   
        const dtz = new Date();
        let offest_num_minutes = dtz.getTimezoneOffset();
        let offset_hours = Math.floor(offest_num_minutes / 60);
        let offset_minues = offest_num_minutes % 60;

        var time1 = `${offset_hours.toString().padStart(2, '0')}:${offset_minues.toString().padStart(2, '0')}`;

        return time1;
    }


    const [user, setUser] = useState({});
    const [tokenClient, setTokenClient] = useState({});
    // const [startEvent, SetStartEvent] = useState({});
    // const [endEvent, SetEndEvent] = useState({});
    const [eventTime, SetEventTime] = useState(() => {

        let ret = '8:00AM'; // the default value
        let event_time_saved = getCookie('event_time');
        if (event_time_saved !== null) {
            ret = event_time_saved;
        }
        return ret;
    });

    const [emailReminder, SetEmailReminder] = useState(() => {
        let ret = true; // the default value
        let email_reminder_saved = getCookie('email_reminder');
        if (email_reminder_saved !== null) {
            if (email_reminder_saved === 'false') ret = false;
        }
        return ret;
    });

    const [popupReminder, SetPopupReminder] = useState(() => {
        let ret = true; // the default value
        let popup_reminder_saved = getCookie('popup_reminder');
        if (popup_reminder_saved !== null) {
            if (popup_reminder_saved === 'false') ret = false;
        }
        return ret;
    });
    //-----------------------------------------------------------------------------------
    // the variable passed for date1 is props.googleCalendarDict['date1']
    // this date could be saturday or sunday - in that case we find the
    // next monday and return the value for the next monday otherwise, keep
    // the same value - we can also compare reminderDate1 with the passed
    // value to see if its shifted and show the actual date
    const [reminderDate1, SetReminderDate1] = useState(() => {
        let d = props.googleCalendarDict['date1'];
        let ltzo = local_timezone_offset();
        let dd = `${d}T06:00:00-${ltzo}`  // create the date for 6AM of teh local timezone
        let date = new Date(dd);
        let dayOfWeek = date.getDay();  // had to put UTC day otherwise its off by 1 day
        if (dayOfWeek === 0 || dayOfWeek === 6) {
            let daysUntilMonday = dayOfWeek === 0 ? 1 : 8 - dayOfWeek;
            date.setDate(date.getDate() + daysUntilMonday);
            let year = date.getFullYear();
            let month = String(date.getMonth() + 1).padStart(2, '0');
            let day = String(date.getDate()).padStart(2, '0');
            let nextMonday = `${year}-${month}-${day}`;
            d = nextMonday;
        }
        return d;
    });
    //-----------------------------------------------------------------------------------
    const [reminderDate2, SetReminderDate2] = useState(() => {
        let d = props.googleCalendarDict['date2'];
        let ltzo = local_timezone_offset();
        let dd = `${d}T06:00:00-${ltzo}`  // create the date for 6AM of teh local timezone
        let date = new Date(dd);
        let dayOfWeek = date.getDay();  // had to put UTC day otherwise its off by 1 day
        if (dayOfWeek === 0 || dayOfWeek === 6) {
            let daysUntilMonday = dayOfWeek === 0 ? 1 : 8 - dayOfWeek;
            date.setDate(date.getDate() + daysUntilMonday);
            let year = date.getFullYear();
            let month = String(date.getMonth() + 1).padStart(2, '0');
            let day = String(date.getDate()).padStart(2, '0');
            let nextMonday = `${year}-${month}-${day}`;
            d = nextMonday;
        }
        return d;
    });

    const [dragPos, setDragPos] = useState(null)
    const dragRef = useRef({ active: false, offsetX: 0, offsetY: 0 })
    const dialogRef = useRef(null)

    useEffect(() => {
        const onMouseMove = (e) => {
            if (!dragRef.current.active) return
            const x = Math.max(0, Math.min(window.innerWidth - 200, e.clientX - dragRef.current.offsetX))
            const y = Math.max(0, Math.min(window.innerHeight - 60, e.clientY - dragRef.current.offsetY))
            setDragPos({ x, y })
        }
        const onMouseUp = () => { dragRef.current.active = false }
        window.addEventListener('mousemove', onMouseMove)
        window.addEventListener('mouseup', onMouseUp)
        return () => {
            window.removeEventListener('mousemove', onMouseMove)
            window.removeEventListener('mouseup', onMouseUp)
        }
    }, [])

    const handleTitleMouseDown = (e) => {
        if (rdd.isMobile) return
        if (e.detail === 2) { setDragPos(null); return }
        const el = dialogRef.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        dragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top }
        e.preventDefault()
    }

    //------------------------------------------------------------------------
    // device specific
    //------------------------------------------------------------------------
    var font_size = '0.9vw',title_width ='90%',title_close_width='5%',closeIconSize=18,title_height='10%',text_height='35%';
    var button_font_size = '0.9vw';
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { font_size = '4vw';title_width ='80%';title_close_width='10%';closeIconSize=20;title_height='5%';text_height='40%';button_font_size = '3.5vw' }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { font_size = '1.5vw';button_font_size = '1.5vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { font_size = '2vw';title_height='5%';text_height='40%';button_font_size = '2vw'}
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { font_size = '1.4vw'}
    //------------------------------------------------------------------------

    function handleCallbackResponse(response) {
        console.log('encoded JWT ID token:' + response.credential);
        var userObject = jwt_decode(response.credential);
        console.log(userObject)
        setUser(userObject);
        document.getElementById('signInDiv').hidden = true;
    }
    //-----------------------------------------------------------------------------------
    function handleSignOut(event) {
        setUser({});
        document.getElementById('signInDiv').hidden = false;
    }

    // async function sendEvent() {
    //     console.log('send event')

    // }
    //-------------------------------------------------------------------------------------
    // converts like of 2:30PM to 14:30:00 - and some special stuff for 11:00PM and 11:30PM 
    function convert_eventTime_24hour_format(timeStr) {

        let t1 = '';
        let t2 = '';
        let h2 = '';
        let m2 = '';

        let ampm = timeStr.substring(timeStr.length - 2);
        let tmp = timeStr.substring(0, timeStr.length - 2);

        let [hours, min] = tmp.split(":");

        if (ampm === 'PM') {
            let t = parseInt(hours) + 12;
            h2 = (t + 1).toString(); // this is for end time
            hours = t.toString();
        }
        else { // AM
            let t = parseInt(hours);
            h2 = (t + 1).toString(); // this is for end time
        }

        if (hours.length === 1) hours = '0' + hours;
        if (h2.length === 1) h2 = '0' + h2;

        let min2 = min;

        if (h2 === '24') { // trying to fix the possible issue of setting notificaiton time to 23:00:00
            if (min == '00') {
                h2 = '23';
                min2 = '30';
            }
            else {
                h2 = '23';
                min2 = '45';
            }
        }
        t1 = hours + ':' + min + ':00';
        t2 = h2 + ':' + min2 + ':00'

        // console.log('t1,t2=',t1,t2)
        return [t1, t2]

    }
    //--------------------------------------------------------------------------------
    function createGCdict(start_or_end) {  // 'start' or 'end' - all comes from googleCalendarDict

        var domain_name = window.location.host; // used to generate a link to the report
        var start_date_time, end_date_time, dict;
        // var start_date_time = `${props.googleCalendarDict['date1']}T08:00:00-04:00` // -04:00 represents eastern timezone
        // var end_date_time = `${props.googleCalendarDict['date1']}T09:00:00-04:00`;
        let [eventTime24_1, eventTime24_2] = convert_eventTime_24hour_format(eventTime);

        let summary = '';
        let description = '';
        var start_date_time = '';
        var end_date_time = '';

        if (start_or_end === 'start') {
            start_date_time = `${reminderDate1}T${eventTime24_1}` // -04:00 represents eastern timezone
            end_date_time = `${reminderDate1}T${eventTime24_2}`;
            summary = `${props.googleCalendarDict['ticker']} TradeWave Opportunity Start Event`;
            description = `This event marks the start date of a TradeWave opportunity for ${props.googleCalendarDict['ticker']}, a member of the ${props.googleCalendarDict['resource_group']} financial group. The opportunity date range is from ${props.googleCalendarDict['date1']} to ${props.googleCalendarDict['date2']}, a ${props.googleCalendarDict['days']} day opportunity. For more information, please refer to the detailed <a href="${domain_name}/${props.googleCalendarDict['slug']}">report</a> linked in the event.\n This Event was generated by <a href='https://tradewave.ai'>tradewave.ai</a>`
        }

        else {
            start_date_time = `${reminderDate2}T${eventTime24_1}` // -04:00 represents eastern timezone
            end_date_time = `${reminderDate2}T${eventTime24_2}`;
            summary = `${props.googleCalendarDict['ticker']} TradeWave Opportunity End Event`;
            description = `This event marks the End Date of a TradeWave opportunity for ${props.googleCalendarDict['ticker']}, a member of the ${props.googleCalendarDict['resource_group']} financial group. The opportunity date range is from ${props.googleCalendarDict['date1']} to ${props.googleCalendarDict['date2']}, a ${props.googleCalendarDict['days']} day opportunity. For more information, please refer to the detailed <a href="${domain_name}/${props.googleCalendarDict['slug']}">report</a> linked in the event.\n This Event was generated by <a href='https://tradewave.ai'>tradewave.ai</a>`
        }

        var overrides = [];

        if (emailReminder) {
            overrides.push({ 'method': 'email', 'minutes': 24 * 60 });
        }
        if (popupReminder) {
            overrides.push({ 'method': 'popup', 'minutes': 5 })
        }


        var dict = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_date_time,
                'timeZone': local_timezone,
            },
            'end': {
                'dateTime': end_date_time,
                'timeZone': local_timezone,
            },
            'reminders': {
                'useDefault': false,
                'overrides': overrides
            }
        }

        return (dict);

    }
    //--------------------------------------------------------------------------------
    useEffect(() => {

        // console.log('environment variable =',process.env.REACT_APP_CLIENT_ID)

        // console.log('CLIENT_ID=',CLIENT_ID)


        loadScript(src)
            .then(() => {



                /* global google */

                const google = window.google;
                google.accounts.id.initialize({
                    client_id: CLIENT_ID,
                    callback: handleCallbackResponse
                })


                // Get Access Token
                // create something called a tokenClient
                setTokenClient(
                    google.accounts.oauth2.initTokenClient({
                        client_id: CLIENT_ID,
                        scope: SCOPES,
                        callback: (tokenResponse) => {
                            // console.log('tokenResponse=', tokenResponse);
                            // we now have access to a live token to use for ANY google API
                            if (tokenResponse && tokenResponse.access_token) {
                                // create the calendar event here

                                //---------------------------------------------------------------------------
                                //  Insert Notification for Start Date of the Seasonal Date Range
                                //---------------------------------------------------------------------------
                                let cal_dict = createGCdict('start')
                                // console.log('cal_dict start',cal_dict)
                                var contentText = ''
                                props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
                                props.SetDialogType('info-box');
                                props.SetInfoBoxVisible(true)

                                fetch('https://www.googleapis.com/calendar/v3/calendars/primary/events', {
                                    method: 'POST',
                                    headers: {
                                        'Authorization': 'Bearer ' + tokenResponse.access_token
                                    },
                                    body: JSON.stringify(cal_dict)
                                }).then((data) => {
                                    contentText = contentText + ''
                                    props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })

                                    return data.json();
                                }).then((data) => {


                                    if (data.hasOwnProperty('error')) {
                                        contentText = 'Error:' + data['error']['message'];
                                    }
                                    else {
                                        contentText = 'Created Start and End Events On Google Calendar';
                                    }

                                    // console.log('Start data data =', data);
                                    // alert('start event created check google calendar')
                                    props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })

                                })
                                //---------------------------------------------------------------------------
                                //  Insert Notification for End Date of the Seasonal Date Range
                                //---------------------------------------------------------------------------
                                cal_dict = createGCdict('end');
                                // console.log('cal_dict end',cal_dict)

                                fetch('https://www.googleapis.com/calendar/v3/calendars/primary/events', {
                                    method: 'POST',
                                    headers: {
                                        'Authorization': 'Bearer ' + tokenResponse.access_token
                                    },
                                    body: JSON.stringify(cal_dict)
                                }).then((data) => {
                                    // contentText = contentText + '\nend event added'
                                    // props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })

                                    return data.json();
                                }).then((data) => {
                                    // console.log('End data data =', data);
                                    // alert('End event created check google calendar')
                                    // contentText = contentText + '\nend event 2 added'
                                    //props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
                                    if (data.hasOwnProperty('error')) {
                                        contentText = 'Error:' + data['error']['message'];
                                    }
                                    else {

                                        contentText = 'Created Start and End Events On Google Calendar';
                                        props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })

                                    }
                                })


                                props.SetAddGCVisible(false);


                            }
                        }
                    })
                );


//------------------------------------------------

            })
            .catch(console.error)
        return () => {
            const scriptTag = document.querySelector(`script[src="${src}"]`)
            if (scriptTag) document.body.removeChild(scriptTag)
        }


//------------------------------------------------


    }, [eventTime]);

    //-----------------------------------------------------------------------------
    function createCalendarEvent() {
        tokenClient.requestAccessToken();
    }
    //-----------------------------------------------------------------------------
    const AddGC_style = {
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: tc.panelBg,
        width: props.googleCalendarDict['DialogW'],
        height: props.googleCalendarDict['DialogH'],
        zIndex: 6000,
        ...(dragPos
            ? { position: 'fixed', top: dragPos.y, left: dragPos.x, boxShadow: '0 8px 32px rgba(0,0,0,0.35)' }
            : { position: 'absolute', top: props.googleCalendarDict['DialogT'], left: props.googleCalendarDict['DialogL'] })
    }
    //-----------------------------------------------------------------------------
    const handleEventTimeChanged = (event) => {
        SetEventTime(event.target.value);
        setCookie('event_time', event.target.value, 300);
    }
    //-----------------------------------------------------------------------------
    const handleCheckboxChanged = (event) => {
        if (event.target.value === 'email_reminder') {
            SetEmailReminder(event.target.checked);
            setCookie('email_reminder', event.target.checked.toString(), 300);
        }
        if (event.target.value === 'popup_reminder') {
            SetPopupReminder(event.target.checked);
            setCookie('popup_reminder', event.target.checked.toString(), 300);
        }
    }

    //-----------------------------------------------------------------------------





    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div ref={dialogRef} className="dialog-GC" style={AddGC_style}   >

            {/* <div id="signInDiv"></div>
            {Object.keys(user).length != 0 &&
                <button onClick={(e) => handleSignOut(e)}>Sign Out</button>
            } */}
            <div style={{ width: '100%', height: '90%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: tc.titleBar, height: title_height, display: 'flex', justifyContent: 'center', alignItems: 'center', cursor: rdd.isMobile ? 'default' : 'move' }} onMouseDown={handleTitleMouseDown}>
                    <div style={{ width: title_close_width, height: '100%', backgroundColor: 'transparent' }}></div>
                    <div style={{ width: title_width, display: 'flex', justifyContent: 'center', alignItems: 'center' }}><span style={{ color: 'white', fontSize: font_size }}>Add Opportunity To Google Calendar</span></div>
                    <div style={{ width: title_close_width, height: '100%', backgroundColor: tc.statLabelBg, display: 'flex', justifyContent: 'center', alignItems: 'center' }} onClick={() => props.SetAddGCVisible(false)} ><GrClose size={closeIconSize} style={{ fill: 'white' }} /></div>
                </div>

         

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: text_height }}>
                    <p style={{ color: tc.text, fontSize: font_size, margin: '1vw' }}>
                        By clicking the "Create Calendar Events" button, you can schedule two events in your Google Calendar: one for the Start Date and another for the End Date of this opportunity. With these calendar events you'll be able to keep track of the important dates for this opportunity.
                    </p>
                </div>


                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: tc.text }}>Opportunity Start Date:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left', alignItems: 'center' }}><span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw' ,paddingLeft:'5px',paddingRight:'5px',paddingBottom:'1px'}}>{reminderDate1}</span>
                        {(props.googleCalendarDict['date1'] !== reminderDate1 && !(rdd.isMobile && !rdd.isTablet && browserH > browserW)) &&
                            <span style={{ marginLeft: '1vw', color: tc.text }}>Actual: {props.googleCalendarDict['date1']}</span>
                        }
                    </div>
                </div>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: tc.text }}>Opportunity End Date:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left', display: 'flex', alignItems: 'center' }}><span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw',paddingLeft:'5px',paddingRight:'5px',paddingBottom:'1px' }}>{reminderDate2}</span>
                        {(props.googleCalendarDict['date2'] !== reminderDate2 && !(rdd.isMobile && !rdd.isTablet && browserH > browserW)) &&
                            <span style={{ marginLeft: '1vw', color: tc.text }}>Actual: {props.googleCalendarDict['date2']}</span>
                        }
                    </div>
                </div>


                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: tc.text }}>Calendar Event Time:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left', alignItems: 'center' }}><span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw' }}><SelectBox optionList={EVENT_TIMES_LIST} value={eventTime} suffix="" name="event_time" sbChanged={handleEventTimeChanged} /></span>
                        {!(rdd.isMobile && !rdd.isTablet && browserH > browserW) &&
                            <span style={{ marginLeft: '1vw', color: tc.text }}>{local_timezone}</span>
                        }
                    </div>
                </div>
                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: tc.text }}>Email Reminder:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left' }}><span style={{ backgroundColor: 'transparent', color: 'white', marginLeft: '1vw' }}><CheckBox cbChanged={handleCheckboxChanged} label="email_reminder" checked={emailReminder} /></span><span style={{ marginLeft: '1vw', color: tc.text }}>Sent 24 hours prior</span></div>
                </div>
                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: tc.text }}>Popup Reminder:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left' }}><span style={{ backgroundColor: 'transparent', color: 'white', marginLeft: '1vw' }}><CheckBox cbChanged={handleCheckboxChanged} label="popup_reminder" checked={popupReminder} /></span><span style={{ marginLeft: '1vw', color: tc.text }}>5 minutes prior</span></div>
                </div>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '5%' }}>

                </div>

            </div>


            <div style={{ borderTop: '1px solid ' + (UITheme === 'dark' ? 'gray' : tc.border), width: '100%', height: '10%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>
                <button style={{ marginLeft: '10px',fontSize:button_font_size }} onClick={() => props.SetAddGCVisible(false)}>Cancel</button>
                <button style={{ marginLeft: '10px',fontSize:button_font_size ,display:'flex',alignItems:'center'}} onClick={() => createCalendarEvent()}> <img src={"data:image/png;base64, " + google_logo} alt=""  />  &nbsp;Create calendar events</button>


            </div>

        </div>


    )
}
export default AddGC
