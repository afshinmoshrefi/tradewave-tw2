// AddGC is the dialog that displays when user clicks the add to google calendar icon in Opportunities Manager 
// Is uses the new GIS authentication method to communicate with Google Calendar

// about loading date to javascript:  d = new Date(d)
// I add time of 6AM to it and the timezone offset of the local time
// otherwise, it would screwup when calculating date to the next monday

// console.cloud.google.com to setup the APIs

import React, { useEffect, useState, useContext, useRef } from 'react';
import { UserContext } from './UserContext'
import './styles/InfoPopup.css';
import CheckBox from './CheckBox';
// import TextBox from './TextBox';
import { getAllEventTimes } from './Common'
import SelectBox from './SelectBox'
import TextBoxTime from './TextBoxTime';
import { getCookie, setCookie } from './Common'
import { GrClose } from "react-icons/gr";
import { url_at } from './Common'




const TradeInstrumentReport = (props) => {

    const { browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)


    // const local_timezone_offset = Intl.DateTimeFormat().resolvedOptions().timeZoneOffset;

   


   

    //------------------------------------------------------------------------
    // device specific 
    //------------------------------------------------------------------------
    var font_size = '0.9vw', title_width = '90%', title_close_width = '5%', closeIconSize = 18, title_height = '10%', body_height = '90%';
    var button_font_size = '0.9vw';
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { font_size = '4vw'; title_width = '80%'; title_close_width = '10%'; closeIconSize = 20; title_height = '5%'; body_height = '95%'; button_font_size = '3.5vw' }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { font_size = '1.5vw'; button_font_size = '1.5vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { font_size = '2vw'; title_height = '5%'; body_height = '95%'; button_font_size = '2vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { font_size = '1.4vw' }
    //------------------------------------------------------------------------

   
    //--------------------------------------------------------------------------------
    function createGCdict(start_or_end) {  // 'start' or 'end' - all comes from googleCalendarDict



    }
    //--------------------------------------------------------------------------------
    useEffect(() => {

        let url = `${url_at}/get_strategies/`

        console.log('url=',url)

        fetch(url)
            .then((res) => {
                return res.json();
            })
            .then((g) => {
                console.log('ssssssssssssssssssssssty',g)
            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
            })

    }, []);

    //-----------------------------------------------------------------------------

    //-----------------------------------------------------------------------------
    const AddGC_style = {
        display: 'flex',
        flexDirection: 'column',
        position: 'absolute',
        backgroundColor: 'whitesmoke',
        width: props.googleCalendarDict['DialogW'],
        height: props.googleCalendarDict['DialogH'],
        top: props.googleCalendarDict['DialogT'],
        left: props.googleCalendarDict['DialogL'],
        zIndex: 6000
    }
    //-----------------------------------------------------------------------------



    //-----------------------------------------------------------------------------


    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div className="dialog-GC" style={AddGC_style}   >

            {/* <div id="signInDiv"></div>
            {Object.keys(user).length != 0 &&
                <button onClick={(e) => handleSignOut(e)}>Sign Out</button>
            } */}
            <div style={{ width: '100%', height: '90%', backgroundColor: 'RGB(205, 252, 202)', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'dimgray', height: title_height, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <div style={{ width: title_close_width, height: '100%', backgroundColor: 'transparent' }}></div>
                    <div style={{ width: title_width, display: 'flex', justifyContent: 'center', alignItems: 'center' }}><span style={{ color: 'white', fontSize: font_size }}>{props.googleCalendarDict['ticker']} Trade Report</span></div>
                    <div style={{ width: title_close_width, height: '100%', backgroundColor: 'lightgray', display: 'flex', justifyContent: 'center', alignItems: 'center' }} onClick={() => props.SetShowTradeInstrumentReport(false)} ><GrClose size={closeIconSize} style={{ fill: 'white' }} /></div>
                </div>



                <div style={{ backgroundColor: 'transparent', width: '100%', height: body_height }}>

                    <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                        <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: 'black' }}>Ticker Symbol:</span></div>
                        <div style={{ width: '50%', display: 'flex', justifyContent: 'left', alignItems: 'center' }}>
                            <span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw', paddingLeft: '5px', paddingRight: '5px', paddingBottom: '1px' }}>
                                {props.googleCalendarDict['ticker']}
                            </span>

                        </div>
                    </div>

                    <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                       
                    </div>

                    <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                        
                    </div>


                    <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                        <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: 'black' }}>Trade Entry Time:</span></div>
                        <div style={{ width: '50%', display: 'flex', justifyContent: 'left', alignItems: 'center' }}><span style={{ backgroundColor: 'black', color: 'white', marginLeft: '1vw' }}><TextBoxTime /></span>
                         
                        </div>
                    </div>

                    {/* <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: 'black' }}>Email Reminder:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left' }}><span style={{ backgroundColor: 'transparent', color: 'white', marginLeft: '1vw' }}><CheckBox cbChanged={handleCheckboxChanged} label="email_reminder" checked={emailReminder} /></span><span style={{ marginLeft: '1vw' }}>Sent 24 hours prior</span></div>
                </div>
                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '10%', fontSize: font_size, display: 'flex', alignItems: 'center' }}>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'right' }}><span style={{ color: 'black' }}>Popup Reminder:</span></div>
                    <div style={{ width: '50%', display: 'flex', justifyContent: 'left' }}><span style={{ backgroundColor: 'transparent', color: 'white', marginLeft: '1vw' }}><CheckBox cbChanged={handleCheckboxChanged} label="popup_reminder" checked={popupReminder} /></span><span style={{ marginLeft: '1vw' }}>5 minutes prior</span></div>
                </div>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '5%' }}>

                </div> */}

                </div>
            </div>

            <div style={{ borderTop: '1px solid gray', width: '100%', height: '10%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>
                <button style={{ marginLeft: '10px', fontSize: button_font_size }} onClick={() => props.SetShowTradeInstrumentReport(false)}>Cancel</button>

                
            </div>

        </div>


    )
}
export default TradeInstrumentReport
