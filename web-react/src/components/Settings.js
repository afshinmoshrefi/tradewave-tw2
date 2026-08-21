import React, { useContext, useEffect, useState } from 'react'
import { UserContext } from './UserContext'
import { appserverURL, securityTypeList } from './Common'
import './styles/InfoPopup.css'
import './styles/Settings.css'
import { GrClose } from "react-icons/gr";
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import { GrEdit, GrRun } from "react-icons/gr";
import { BsTrash3 } from "react-icons/bs";
import CheckBox from './CheckBox'
import { monthsOptionsList, monthsOptionsListS, getTodayDate } from './Common'

// <SlSettings size={portMoveSize} style={{ fill: "black", backgroundColor: "transparent", verticalAlign: 'bottom' }} />

const Settings = (props) => {


    const { numReportsAllowed, browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)


    const [message, SetMessage] = useState('')
    const [newText, SetNewText] = useState('')
    const [selPort, SetSelPort] = useState('main')

    const [numOppsSelectedPortfolio, SetNumOppsSelectedPortfolio] = useState(-1)


    const [emailSelection, SetEmailSelection] = useState(false);



    var bannerHeight = '10%';

    var DialogH = '30%';
    var DialogW = '30%';
    var DialogT = '35%';
    var DialogL = '35%';

    var DialogHelpH = '30%';
    var DialogHelpW = '25%';
    var DialogHelpT = '35%';
    var DialogHelpL = '28%';

    var DialogHelpBorderT = '2px solid black';
    var DialogHelpBorderL = '0px solid black';
    var DialogHelpBorderR = '2px solid black';
    var DialogHelpBorderB = '2px solid black';

    var grclose_iconsize = 17;
    var icon_sizeP = 15;
    var icon_sizeE = 12;
    var icon_sizeD = 12;
    var title_text_size = '1vw';
    var button_height = '2.5vh'
    var textboxWidth = 24;

    var titleCloseDivWidth = '6%';
    var titleCenterDivWidth = '88%';

    var questionSize = 16;
    var helpTextFontSize = '0.9rem';
    var headingSize = '0.8vw';

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
        DialogH = '40%';
        DialogW = '100%';
        DialogT = '15%';
        DialogL = '0';

        DialogHelpH = '40%';
        DialogHelpW = '100%';
        DialogHelpT = '55%';
        DialogHelpL = '0';


        DialogHelpBorderT = '0px solid black';
        DialogHelpBorderL = '2px solid black';
        DialogHelpBorderR = '2px solid black';
        DialogHelpBorderB = '2px solid black';


        grclose_iconsize = 17;
        title_text_size = '4.5vw';
        textboxWidth = 16;
        button_height = '3.5vh';
        titleCloseDivWidth = '10%';
        titleCenterDivWidth = '80%';
        bannerHeight = '8%';

        questionSize = 20;

        headingSize = '3.5vw'
        helpTextFontSize = '1.25rem'
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {

        DialogH = '60%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '20%';

        DialogHelpH = '60%';
        DialogHelpW = '40%';
        DialogHelpT = '35%';
        DialogHelpL = '60%';

        DialogHelpBorderT = '2px solid black';
        DialogHelpBorderL = '0px solid black';
        DialogHelpBorderR = '2px solid black';
        DialogHelpBorderB = '2px solid black';

        headingSize = '1.5vw';

        grclose_iconsize = 17;
        title_text_size = '2vw';
        textboxWidth = 17;
        button_height = '5.5vh';
        bannerHeight = '12%';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserW < 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';

        DialogHelpH = '30%';
        DialogHelpW = '70%';
        DialogHelpT = '65%';
        DialogHelpL = '15%';

        DialogHelpBorderT = '2px solid black';
        DialogHelpBorderL = '0px solid black';
        DialogHelpBorderR = '2px solid black';
        DialogHelpBorderB = '2px solid black';

        helpTextFontSize = '1.5rem'

        headingSize = '1.25rem'


        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 24;
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserH < 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';

        DialogHelpH = '30%';
        DialogHelpW = '40%';
        DialogHelpT = '65%';
        DialogHelpL = '30%';

        DialogHelpBorderT = '0px solid black';
        DialogHelpBorderL = '2px solid black';
        DialogHelpBorderR = '2px solid black';
        DialogHelpBorderB = '2px solid black';

        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 19;

        headingSize = '1.25rem';

        helpTextFontSize = '1.15rem'
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';


        DialogHelpH = '30%';
        DialogHelpW = '70%';
        DialogHelpT = '65%';
        DialogHelpL = '15%';

        DialogHelpBorderT = '0px solid black';
        DialogHelpBorderL = '2px solid black';
        DialogHelpBorderR = '2px solid black';
        DialogHelpBorderB = '2px solid black';

        questionSize = 22;

        headingSize = '2.5vw'
        helpTextFontSize = '1.6rem'

        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 26;
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserW > 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '15%';

        DialogHelpH = '30%';
        DialogHelpW = '40%';
        DialogHelpT = '35%';
        DialogHelpL = '55%';

        DialogHelpBorderT = '2px solid black';
        DialogHelpBorderL = '0px solid black';
        DialogHelpBorderR = '2px solid black';
        DialogHelpBorderB = '2px solid black';

        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 23;

    }
    //------------------------------------------------------------------------------------------------------------
    const popupDialogStyle = {
        fontFamily: 'sans-serif',
        fontSize: '0.75vw',
        fontWeight: 'bold',
        position: 'absolute',
        backgroundColor: "lightblue",
        height: DialogH,
        width: DialogW,
        top: DialogT,
        left: DialogL,
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid black',
        alignItems: 'center',
        zIndex: 7800,

    }

    const popupHelpStyle = {
        height: DialogHelpH,
        width: DialogHelpW,
        top: DialogHelpT,
        left: DialogHelpL,
        position: 'absolute',
        backgroundColor: 'mistyrose',
        borderTop: DialogHelpBorderT,
        borderBottom: DialogHelpBorderB,
        borderRight: DialogHelpBorderR,
        borderLeft: DialogHelpBorderL,
        display: props.helpEmailDisplay,
        padding: '10px',
        fontSize: helpTextFontSize,
        color: 'black'

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {



    }, [])
    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------
    const mainCoverDiv = {
        position: 'absolute',
        backgroundColor: 'rgb(222,222,222,0)',
        zIndex: 1000,
        fontFamily: 'sans-serif',
        width: '100%',
        height: '100%',
        left: '0%',
        top: '0%',
    }
    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------
    const controlsDIV = {

        width: '80%',
        height: '80%',
        backgroundColor: 'transparent',

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const controlRowDIV = {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        wdith: '100%',
        height: '25%',
        backgroundColor: 'transparent',
        // borderBottom: '1px solid black'
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const controlLeftCell = {
        display: 'flex',
        justifyContent: 'right',
        alignItems: 'center',
        paddingRight: '2px',
        width: '50%',
        height: '100%',
        backgroundColor: 'transparent'
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const controlRightCell = {
        width: '50%',
        height: '100%',
        display: 'flex',
        justifyContent: 'left',
        alignItems: 'center',
        paddingRight: '2px',
        backgroundColor: 'transparent'
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleBlur = (event) => {
        let num = event.target.value;
        if (!isNaN(num)) {
            props.SetTrimYear(num);
        }

    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleEnter = (event) => {

        let num = event.target.value;
        if (!isNaN(num)) {
            props.SetTrimYear(num);
        }

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const checkboxChanged = (event) => {
        props.SetShowSR2(!props.showSR2);
        props.SetOpportunities([])
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handlePortfolioAction = (action) => {
        console.log('handel portoflio action ', action)


        let asURL = appserverURL();
        var url = `${asURL}/process_auto_portfolio?token=${token}`


        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => {
                const contentType = res.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    return res.json();
                }
                else {
                    console.log('response status = ', res.status)
                }
            })
            .then((ret) => {
                

            })
            .catch(err => {
                console.log('catch login error=', err.message)
            })









    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div className='main-cover-opp-manager' style={mainCoverDiv} onClick={() => { props.SetShowSettings(false); }}  >

            <div className='popup-dialog-style' style={popupDialogStyle} onClick={(e) => { e.stopPropagation(); }} >

                <div style={{ width: '100%', height: bannerHeight, backgroundColor: 'gray', display: 'flex' }}>
                    <div style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'transparent' }}></div>
                    <div className='div_basic' style={{ height: '100%', width: titleCenterDivWidth, backgroundColor: 'transparent' }}><span style={{ fontSize: title_text_size, color: 'whitesmoke' }}>Settings</span></div>
                    <div className='div_basic' onClick={() => { props.SetShowSettings(false) }} style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'lightgray' }}><GrClose size={grclose_iconsize} /></div>
                </div>

                <div className='settings-dialog' style={{ paddingTop: '2px', backgroundColor: 'whitesmoke', height: `calc(100% - ${bannerHeight})`, width: '100%' }}>

                    <div className="add-gc-div-top-rows" style={{ backgroundColor: 'WhiteSmoke', height: '10%', fontSize: infoTextSize, display: 'flex', alignItems: 'center' }}>
                        {/* Tabs */}
                        {/* Tab 1 */}
                        <div style={{ width: '30%', height: '100%', backgroundColor: 'lightgray', borderRight: '1px solid black', borderTop: '1px solid black', justifyContent: 'center', display: 'flex' }}>
                            <span style={{ fontSize: headingSize }} >Wave Viewer</span>
                        </div>
                        {/* Tab 2  */}
                        <div style={{ width: '30%', height: '100%', backgroundColor: 'whitesmoke', borderBottom: '1px solid black', justifyContent: 'center', display: 'flex', alignItems: 'center', cursor: 'pointer' }}
                            onClick={() => { props.SetShowSettings(false); props.SetShowSecuritiesGroupSettings(true); }}>
                            <span style={{ fontSize: headingSize, color: 'gray' }}>Securities Groups</span>
                        </div>
                        <div style={{ width: '20%', height: '100%', backgroundColor: 'whitesmoke', borderBottom: '1px solid black', justifyContent: 'center', display: 'flex' }}>
                            <span ></span>
                        </div>
                        <div style={{ width: '20%', height: '100%', backgroundColor: 'whitesmoke', borderBottom: '1px solid black', justifyContent: 'center', display: 'flex' }}>
                            <span ></span>
                        </div>


                    </div>


                    <div style={{ backgroundColor: 'lightgray', height: '10%', fontSize: infoTextSize, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <div style={{ width: '5%', height: '100%', backgroundColor: 'transparent' }}></div>
                        <div style={{ width: '90%', height: '100%', display: 'flex', backgroundColor: 'transparent', alignItems: 'center', justifyContent: 'center' }}><span style={{ color: 'black', paddingLeft: '5px', fontSize: headingSize }}>Update Wave Viewer Settings</span></div>
                        {/* <div style={{ width: '5%', height: '100%', display: 'flex', backgroundColor: 'transparent', alignItems: 'center', justifyContent: 'center' }}><BsQuestionCircle size={questionSize} style={{ fill: "black" }} onClick={handleHelpClicked} /></div> */}
                    </div>




                    <div className="add-gc-div-top-rows" style={{ backgroundColor: 'transparent', height: '80%', fontSize: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>

                        <div style={controlsDIV}>
                            <div style={controlRowDIV}>
                                <div style={controlLeftCell}>
                                    <span>Trim Year To:</span>
                                </div>
                                <div style={controlRightCell}>
                                    <TextBox text={props.trimYear} width="7" name="trimyear" tbBlur={handleBlur} tbEnter={handleEnter} />
                                </div>
                            </div>

                            <div style={controlRowDIV}>
                                <div style={controlLeftCell}>
                                    <span>MFE SR:</span>
                                </div>
                                <div style={controlRightCell}>
                                    <CheckBox name="MFESR" cbChanged={checkboxChanged} checked={props.showSR2} />
                                </div>
                            </div>

                            <div style={controlRowDIV}>

                                <button onClick={() => handlePortfolioAction('process')}>Process Auto Portfolio</button>
                            </div>

                            <div style={controlRowDIV}>
                                <div style={controlLeftCell}>
                                    <label htmlFor="bar-chart-excursion-style">Bar Chart:</label>
                                </div>
                                <div style={controlRightCell}>
                                    <select
                                        id="bar-chart-excursion-style"
                                        value={props.barChartExcursionStyle || 'ticks'}
                                        onChange={(event) => props.SetBarChartExcursionStyle(event.target.value)}
                                    >
                                        <option value="filled">Filled Extensions</option>
                                        <option value="ticks">Capped Needles</option>
                                        <option value="needle">Range Needles</option>
                                    </select>
                                </div>
                            </div>



                        </div>
                    </div>


                </div>


            </div>




        </div>
    )
}
export default Settings
