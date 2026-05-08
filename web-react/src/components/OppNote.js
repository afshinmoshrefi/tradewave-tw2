import React, { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { UserContext } from './UserContext'
import { appserverURL, themeColors } from './Common'
import './styles/InfoPopup.css'
import './styles/Portfolios.css'
import { GrClose } from "react-icons/gr";
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import { BsPlus, BsFolderSymlink, BsTrash3, BsThermometerLow } from "react-icons/bs"
import { GrEdit } from "react-icons/gr";

const OppNote = (props) => {

    const maxCharacters = 1000; // maximum number of characters allowed in a note
    const tc = themeColors(props.UITheme)

    const { numReportsAllowed, browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)

    const [text, setText] = useState("");
    const [dashboardDialog_TLHW, SetDashboardDialog_TLHW] = useState(''); // this the main portfolio dialog TOp Left Height Width - coordinates are used to place a transparent div over the dashboard before rendering notes dilaog - this to enable clciking outside of the dialog and then closing the dialog.

    const [dragPos, setDragPos] = useState(null)
    const [dragSize, setDragSize] = useState(null)
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
        if (e.detail === 2) { setDragPos(null); setDragSize(null); return }
        const el = dialogRef.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        dragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top }
        if (!dragSize) setDragSize({ w: rect.width, h: rect.height })
        e.preventDefault()
    }

    var DialogH = '50%';
    var DialogW = '50%';
    var DialogT = '25%';
    var DialogL = '25%';
    var grclose_iconsize = 17;
    var icon_sizeP = 15;
    var icon_sizeE = 12;
    var icon_sizeD = 12;
    var title_text_size = '1vw';
    var button_height = '2.5vh'
    var textboxWidth = 24;

    var titleCloseDivWidth = '6%';
    var titleCenterDivWidth = '88%';

    var cancel_width = '25%';
    var save_width = '25%';

    var charIndicatorFontSize = '0.7vw'; // this is indicator showing number of chars typed

    var textareaFont = '0.8vw';

    var icon_trash_size = 15;

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
        DialogH = '40%';
        DialogW = '100%';
        DialogT = '18%';
        DialogL = '0';
        grclose_iconsize = 17;
        title_text_size = '4.5vw';
        textboxWidth = 16;
        button_height = '4vh';
        titleCloseDivWidth = '10%';
        titleCenterDivWidth = '80%';

        cancel_width = '33%';
        save_width = '28%'
        charIndicatorFontSize = '3vw';
        textareaFont = '3.5vw';
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {

        DialogT = '35%';
        DialogL = '20%';
        DialogH = '50%';
        DialogW = '60%';
        grclose_iconsize = 17;
        title_text_size = '2vw';
        textboxWidth = 17;
        button_height = '5.3vh';

        cancel_width = '40%';
        save_width = '28%'
        charIndicatorFontSize = '1.8vw';
        textareaFont = '2vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserW < 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';
        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 24;
        charIndicatorFontSize = '1.9vw';
        textareaFont = '2.2vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserH < 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';
        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 19;
        charIndicatorFontSize = '1.1vw';
        textareaFont = '1.3vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';
        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 26;
        charIndicatorFontSize = '2vw';
        textareaFont = '2vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserW > 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';
        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 23;
        charIndicatorFontSize = '1.1vw';
        textareaFont = '1.3vw';
    }
//------------------------------------------------------------------------------------------------------------
    const DashboardCover = {
        height: dashboardDialog_TLHW ['height'],
        width:dashboardDialog_TLHW ['width'] ,
        top:dashboardDialog_TLHW ['top'] ,
        left: dashboardDialog_TLHW ['left'],
        backgroundColor:'transparent',
        display:'flex',
        position:'absolute',
        zIndex:9999
    }
    //------------------------------------------------------------------------------------------------------------
    const popupDialogStyle = {
        fontFamily: 'sans-serif',
        fontSize: '0.8vw',
        fontWeight: 'bold',
        backgroundColor: tc.panelBg,
        color: tc.text,
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid ' + tc.border,
        alignItems: 'center',
        zIndex: 7800,
        ...(dragPos
            ? { position: 'fixed', top: dragPos.y, left: dragPos.x, width: dragSize?.w, height: dragSize?.h, boxShadow: '0 8px 32px rgba(0,0,0,0.35)' }
            : { position: 'absolute', top: DialogT, left: DialogL, height: DialogH, width: DialogW })
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useMemo is for retreiving the coordinates of the parent Div, Report Dashboard
    useMemo(() => {

        const elem = document.querySelector('.dialog-popup-reports-dashboard');
        const rect = elem.getBoundingClientRect();
        if (rect) {
            SetDashboardDialog_TLHW(rect);
        }
    }, []);
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        // console.log('selected slug=', props.selectedDRID)

        let asURL = appserverURL()
        let url = `${asURL}/get_note/${props.selectedDRID}?token=${token}`


        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                let txt = data['note']
                txt = decodeURIComponent(txt)
                setText(txt)
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });

    }, [])
    //-------------------------------------------------------------------------------------------------------------------------------------
    // save the note to redis in appserver
    //-------------------------------------------------------------------------------------------------------------------------------------
    function save_note() {


        if (text.length > maxCharacters) return -1;

        let t = text;
        if (t.length === 0) { // otherwise rest api fails when text is empty
            t = '-';
        }
        // if (t.length >1000){
        //     t=t.substring(0,1000);
        // }
        // from chatGPT about % not getting encoded:
        // The % character is a special character in URI encoding and has a specific purpose. It is used to represent the start of a percent-encoded character in a URI. When you try to encode a string that contains the % character using encodeURIComponent, it does not get further encoded because it assumes that the % is already part of a percent-encoded character.
        //To fix this issue and ensure that the % character is properly encoded, you need to manually replace it with its percent-encoded representation, which is %25.
        t = t.replace('%', '%25')

        // encode textarea text
        let encodedText = encodeURIComponent(t); // to preserver \n text is encoded


        let asURL = appserverURL()
        let url = `${asURL}/save_note/${encodedText}/${props.selectedDRID}?token=${token}`
        // console.log('save note url=',url)
        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                // console.log('save note returned', data)
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });



        return text.length
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handle_save_note = () => {
        save_note();
        props.SetShowOppNote(false);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleTextChange = (event) => {
        setText(event.target.value);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // only afshin sees this  userid 1 , 22 or 16
    // this will tell the appserver to send the opp with the passed slug to SM - facebook initially and then all
    // handle_sm also saves the note
    const handle_sm = () => {

        if (text.length > maxCharacters) return -1;

        let t = text;
        if (t.length === 0) { // otherwise rest api fails when text is empty
            t = '-';
        }

        // encode textarea text
        let encodedText = encodeURIComponent(t); // to preserver \n text is encoded

        let asURL = appserverURL()
        let url = `${asURL}/opp_to_social_media/${encodedText}/${props.selectedDRID}?token=${token}`
        // console.log('handle_sm url=',url)
        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                console.log('opp_to_social_media returned', data)
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });

        props.SetShowOppNote(false)
        props.SetReportsList([]) // reload the list so that the trashcan shows up when there is social media post
        // console.log('selectedPortfolioRec =', props.selectedPortfolioRec['sm_post'])

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handle_del_sm = () => {

        let asURL = appserverURL()
        let url = `${asURL}/opp_del_social_media/${props.selectedDRID}?token=${token}`

        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                console.log('opp_del_social_media returned', data)
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });

        props.SetShowOppNote(false)
        props.SetReportsList([]) // reload the list so that the trashcan is removed when there is social media post

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div style={DashboardCover} onClick={() => { props.SetShowOppNote(false); }}>

            <div ref={dialogRef} style={popupDialogStyle} onClick={(e) => { e.stopPropagation(); }}>

                <div style={{ width: '100%', height: '12%', backgroundColor: tc.titleBar, display: 'flex', cursor: rdd.isMobile ? 'default' : 'move' }} onMouseDown={handleTitleMouseDown}>
                    <div style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'transparent' }}></div>
                    <div className='div_basic' style={{ height: '100%', width: titleCenterDivWidth, backgroundColor: 'transparent' }}><span style={{ fontSize: title_text_size, color: tc.textOnControl }}>Note</span></div>
                    <div className='div_basic' onClick={() => { props.SetShowOppNote(false); }} style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: tc.closeBtnBg }}><GrClose size={grclose_iconsize} /></div>
                </div>

                <div className='div_basic' style={{ width: '100%', height: '88%', backgroundColor: 'transparent', flexDirection: 'column' }}>

                    <div className='div_basic' style={{ width: '100%', height: '85%', backgroundColor: 'transparent' }}>
                        <textarea value={text} style={{ height: '100%', width: '100%', padding: '5px', resize: 'none', fontSize: textareaFont, backgroundColor: tc.inputBg, color: tc.text, border: '1px solid ' + tc.border }} onChange={handleTextChange} />
                    </div>

                    {/* <div className='div_basic' style={{ width: '100%', height: '10%', backgroundColor: 'transparent' }}></div> */}

                    <div className='div_basic' style={{ width: '100%', height: '15%', backgroundColor: 'transparent' }}>

                        <div className='div_basic' style={{ width: '50%', height: '100%', justifyContent: 'left', marginLeft: '5px', fontSize: charIndicatorFontSize }}>
                            <span>Num Characters:</span><span style={{ color: text.length > maxCharacters ? 'red' : tc.text }}> {text.length}</span>
                        </div>

                        <div style={{ display: 'flex', width: '50%', height: '100%', justifyContent: 'right', alignItems: 'center', marginRight: '5px' }} >

                            {
                                ((props.loggedinUser === '1' || props.loggedinUser === '22' || props.loggedinUser === '16') && props.selectedPortfolioRec['sm_post'] === 'pos') &&
                                <BsTrash3 size={icon_trash_size} style={{ verticalAlign: "middle", marginRight: '1vw', fill: "gray" }} onClick={handle_del_sm} />
                            }

                            {/* only show this button for afshin  */}
                            {
                                (props.loggedinUser === '1' || props.loggedinUser === '22' || props.loggedinUser === '16') &&
                                <button onClick={handle_sm} style={{ width: save_width, height: button_height, marginRight: '5%' }}>SM</button>
                            }


                            <button onClick={() => { props.SetShowOppNote(false) }} style={{ width: cancel_width, marginRight: '5%', height: button_height }}>Cancel</button>
                            <button onClick={handle_save_note} style={{ width: save_width, height: button_height }}>Save</button>
                        </div>


                    </div>

                </div>

            </div >
        </div>
    )
}
export default OppNote
