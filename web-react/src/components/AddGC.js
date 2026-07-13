// AddGC is the dialog that displays when user clicks the add to google calendar icon in Opportunities Manager
// It uses the new GIS authentication method to communicate with Google Calendar.
// All OAuth + event-content machinery lives in googleCalendarEvents.js (shared
// with the one-click Remind me bell on the wave viewer) - this file is only the
// custom-settings dialog UI (event time, email/popup reminders).

import React, { useEffect, useState, useContext, useRef } from 'react';
import { UserContext } from './UserContext'
import './styles/InfoPopup.css';
import CheckBox from './CheckBox';
import { getAllEventTimes, themeColors, appserverURL } from './Common'
import SelectBox from './SelectBox'
import { getCookie, setCookie } from './Common'
import { GrClose } from "react-icons/gr";
import { google_logo } from './Common';
import { buildPatternEventDict, insertCalendarEvents, requestCalendarAccessToken, shiftWeekendToNextMonday } from './googleCalendarEvents'


const AddGC = (props) => {

    const { browserH, browserW, rdd, globalTextSize, loggedinUser, token, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    const EVENT_TIMES_LIST = getAllEventTimes(); // this function creates a list of objects of 48 times throught out the day seperated by 30 minutes
    const local_timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

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

    // Weekend-shifted reminder dates (a Sat/Sun pattern date gets its reminder
    // on the following Monday); compared against the actual dates for display.
    const [reminderDate1] = useState(() => shiftWeekendToNextMonday(props.googleCalendarDict['date1']));
    const [reminderDate2] = useState(() => shiftWeekendToNextMonday(props.googleCalendarDict['date2']));

    // Pattern stats for the event description (win rate, avg gain, ...) - fetched
    // from the same ChartData4 endpoint the viewer uses. null = not loaded / failed;
    // the description simply omits the stats line then (never block event creation).
    const [patternStats, SetPatternStats] = useState(null)
    useEffect(() => {
        const d = props.googleCalendarDict;
        if (!d || !d['ticker']) return;
        const days_api = parseInt(d['days'], 10) - 1; // same daysOut-1 convention as SeasonalBarChart
        const url = `${appserverURL()}/ChartData4/${d['rid']}/${d['date1']}/${d['ticker']}/${days_api}/${d['years']}?token=${token}`;
        fetch(url)
            .then((r) => r.json())
            .then((data) => { if (data && data['stats']) SetPatternStats(data['stats']); })
            .catch(() => { });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

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
    var font_size = '0.9vw', title_width = '90%', title_close_width = '5%', closeIconSize = 18, title_height = '10%', text_height = '35%';
    var button_font_size = '0.9vw';
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { font_size = '4vw'; title_width = '80%'; title_close_width = '10%'; closeIconSize = 20; title_height = '5%'; text_height = '40%'; button_font_size = '3.5vw' }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { font_size = '1.5vw'; button_font_size = '1.5vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { font_size = '2vw'; title_height = '5%'; text_height = '40%'; button_font_size = '2vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { font_size = '1.4vw' }
    //------------------------------------------------------------------------

    // Map the dialog's state + googleCalendarDict onto the shared event builder.
    const buildEventDicts = () => {
        const d = props.googleCalendarDict;
        const p = {
            rid: d['rid'],
            ticker: d['ticker'],
            direction: d['direction'],
            date1: d['date1'],
            date2: d['date2'],
            days: d['days'],
            years: d['years'],
            resource_group: d['resource_group'],
            slug: d['slug'],
            sharpe_ratio: d['sharpe_ratio'],
            publishDate: d['publishDate'],
            stats: patternStats,
            eventTime: eventTime,
            emailReminder: emailReminder,
            popupReminder: popupReminder,
            reminderDate1: reminderDate1,
            reminderDate2: reminderDate2,
        };
        return [buildPatternEventDict('start', p), buildPatternEventDict('end', p)];
    }

    const showResult = (contentText) => {
        props.SetDialogProp({ title: 'Google Calendar Events', contentText: contentText, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' })
        props.SetDialogType('info-box');
        props.SetInfoBoxVisible(true)
    }

    //-----------------------------------------------------------------------------
    async function createCalendarEvent() {
        const eventDicts = buildEventDicts();
        try {
            // requestCalendarAccessToken opens the consent popup - this runs inside
            // the button-click gesture so popup blockers allow it.
            const accessToken = await requestCalendarAccessToken();
            showResult('Creating events on your Google Calendar...')
            const results = await insertCalendarEvents(accessToken, eventDicts);
            const errors = results
                .filter((r) => r && r.hasOwnProperty('error'))
                .map((r) => r['error']['message'])
            if (errors.length) {
                showResult('Error: ' + errors.join(' / '))
            } else {
                // Stamp gc_events_created on the saved record (fire-and-forget) so the
                // wave viewer's Remind me pill shows "Reminder set" for this pattern.
                const d = props.googleCalendarDict;
                fetch(`${appserverURL()}/dr_report_mark_gc_events/${d['ticker']}/${d['date1']}/${d['days']}/${d['years']}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => { })
                showResult('Created Start and End Events On Google Calendar')
            }
        } catch (err) {
            // GIS load failure (CSP/adblock), popup blocked, or user closed the popup.
            showResult('Could not complete Google sign-in (' + err.message + '). Please allow popups for this site and try again, or contact help@tradewave.ai.')
        }
        props.SetAddGCVisible(false);
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

    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div ref={dialogRef} className="dialog-GC" style={AddGC_style}   >

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
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left', alignItems: 'center' }}><span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw', paddingLeft: '5px', paddingRight: '5px', paddingBottom: '1px' }}>{reminderDate1}</span>
                        {(props.googleCalendarDict['date1'] !== reminderDate1 && !(rdd.isMobile && !rdd.isTablet && browserH > browserW)) &&
                            <span style={{ marginLeft: '1vw', color: tc.text }}>Actual: {props.googleCalendarDict['date1']}</span>
                        }
                    </div>
                </div>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: tc.text }}>Opportunity End Date:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left', display: 'flex', alignItems: 'center' }}><span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw', paddingLeft: '5px', paddingRight: '5px', paddingBottom: '1px' }}>{reminderDate2}</span>
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
                <button style={{ marginLeft: '10px', fontSize: button_font_size }} onClick={() => props.SetAddGCVisible(false)}>Cancel</button>
                <button style={{ marginLeft: '10px', fontSize: button_font_size, display: 'flex', alignItems: 'center' }} onClick={() => createCalendarEvent()}> <img src={"data:image/png;base64, " + google_logo} alt="" />  &nbsp;Create calendar events</button>


            </div>

        </div>


    )
}
export default AddGC
