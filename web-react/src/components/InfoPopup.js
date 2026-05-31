import React, { useContext, useState, useEffect } from 'react'
import { getCookie, setCookie, appserverURL, themeColors } from './Common'
import { UserContext } from './UserContext'
import CheckBox from './CheckBox'
import './styles/InfoPopup.css'
import { logo64 } from './Common'
import { userAccessToSelectedSecurity } from './Common'

const InfoPopup = (props) => {

    const { loggedinUser, rdd, browserW, browserH, token, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [termsCheckBox, SetTermsCheckBox] = useState(false);
    const [checkboxNotificationColor, SetCheckboxNotificationColor] = useState('white');


    // dialogType = 'terms-conditions'
    // dialogType = 'quick-help'
    // dialogType = 'free-register'

    // let dialogType = 'terms-conditions'


    var DialogW = '50%', DialogH = '50%', DialogT = '25%', DialogL = '25%', title, contentText, button1Text, button2Text, coverDivColor;

    var titleFontSize = '1.5vw', contentFontSize = '1vw', buttonFontSize = '1vw', buttonH = '5vh';

    var logo_width = '18vw';
    var line_height = '150%';

    var display_smartphonep = 'none';
    var display_not_smartphonep = 'flex';

    switch (props.dialogType) {
        case 'terms-conditions':
            title = '';

            if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { display_not_smartphonep = 'none'; display_smartphonep = 'flex'; DialogW = '86%'; DialogH = '86%'; DialogT = '4%'; DialogL = '10%'; titleFontSize = '6vw'; contentFontSize = '3.8vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
            else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '70%'; DialogH = '76%'; DialogT = '24%'; DialogL = '15%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '6.0vh'; logo_width = '30vw'; line_height = '100%' }
            else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '60%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '4.5vw'; contentFontSize = '2.3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '50%'; DialogH = '70%'; DialogT = '15%'; DialogL = '25%'; titleFontSize = '2vw'; contentFontSize = '1.2vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }

            contentText = 'This site uses cookies to provide necessary functionality.  Review Terms of Service, Risk Disclosure and Privacy Policy and acknowledge your agreement to continue';
            button1Text = 'Cancel';
            button2Text = 'Continue';
            // opaque = 0.96;
            coverDivColor = 'rgb(222,222,222,0.94)';
            break;
        case 'quick-help':
            title = 'Quick Help';
            DialogW = '50%'; DialogH = '50%'; DialogT = '25%'; DialogL = '25%';
            contentText = '';
            button1Text = 'Cancel';
            button2Text = 'Continue';
            // opaque = 0.96;
            coverDivColor = 'rgb(222,222,222,0.94)';
            break;
        case 'free-register':

            if (loggedinUser == '0') title = 'Loggedin Feature';
            else title = 'Premium Feature';

            if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '90%'; DialogH = '70%'; DialogT = '30%'; DialogL = '5%'; titleFontSize = '6vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
            else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '70%'; DialogH = '75%'; DialogT = '25%'; DialogL = '15%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '60%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '4.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '50%'; DialogH = '70%'; DialogT = '15%'; DialogL = '25%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }

            let retArray = userAccessToSelectedSecurity(props.securityTypeList2, props.selectedSecurity)

            contentText = ''
            if (props.loggedinUser === '0') {
                contentText = "You are seeing this dialog because the feature is either a loggedin or a premium feature that requires an upgrade to our Premium subscriptions. Register for a free account, and gain access to our portfolio manager, which allows you to save and track Wave opportunities."

            }
            else if (retArray[0] === 'F' && retArray[1] === 0) {
                contentText = "You are seeing this dialog because this action is a premium feature that requires an upgrade to our Premium subscriptions.";
            }
            else if (retArray[0] === 'F' && retArray[1] > 0) {
                contentText = 'You have free access to ' + props.selectedSecurity + '.  To get premium access to ' + props.selectedSecurity + ', please upgrade your plan.';
            }
            else {
                contentText = 'ERROR'
            }

            button1Text = 'Close';
            if (props.loggedinUser === 0) {
                button2Text = 'Login';
            }
            else {
                button2Text = '';
            }
            // opaque = 0;
            coverDivColor = 'rgb(222,222,222,0)'
            break;
        case 'rate-limit':
        case 'register':
            title = 'Register';
            if (props.dialogType === 'rate-limit') title = "Get More Queries";
            if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '86%'; DialogH = '69%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '6vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
            else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '70%'; DialogH = '75%'; DialogT = '25%'; DialogL = '15%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '60%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '4.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '50%'; DialogH = '70%'; DialogT = '15%'; DialogL = '25%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }
            contentText = ''
            if (props.dialogType === 'rate-limit') contentText = `
              Alert: You've hit the rate limit for Trade Wave queries. Rate limits are set by second, hour, or day. Subscribers enjoy higher rate limit quotas. Kindly reduce your query frequency. If you continue to encounter rate-limit messages, you may want to consider subscribing, or simply wait until the next day for unrestricted access.
            `;

            button1Text = 'Close';
            button2Text = 'Login';
            coverDivColor = 'rgb(222,222,222,0)'

            break;

        case 'strategist-feature':


            if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '90%'; DialogH = '78%'; DialogT = '20%'; DialogL = '5%'; titleFontSize = '6vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
            else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '70%'; DialogH = '75%'; DialogT = '25%'; DialogL = '15%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '60%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '4.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
            else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '50%'; DialogH = '70%'; DialogT = '15%'; DialogL = '25%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }

            title = 'Strategist Feature';
            contentText = `Presidential Election Cycle Patterns automatically scan for seasonal opportunities that repeat in the current U.S. election cycle year (PE, PE+1, PE+2, PE+3) instead of mixing all years together.  This often reveals clean strategist-grade edges that disappear in “consecutive years” analysis.

Includes:
- Automatic PE cycle filtering for the current cycle year.
- Opportunity detection ranked by historical performance.
- Faster discovery of cycle-specific bullish and bearish windows.
- Upgrade to Strategist Monthly or Yearly to enable this feature.`

            button1Text = 'Close';

            button2Text = 'Upgrade to Strategist';
            if (rdd.isMobile && !rdd.isTablet && browserH > browserW) button2Text = 'Upgrade';


            // opaque = 0;
            coverDivColor = 'rgb(222,222,222,0)'
            break;



        case 'info-box':
            title = props.dialogProp['title'];

            if (title === 'Delete Opportunity' || title === 'delay') { // set dialog dimensions in case of Delete Opportunity Confirmation dialog
                DialogW = '30%'; DialogH = '20%'; DialogT = '40%'; DialogL = '35%'; titleFontSize = '1vw'; contentFontSize = '1.1vw'; buttonFontSize = '0.8vw'; buttonH = '7vh'; logo_width = '22vw'
                if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '10%'; DialogT = '60%'; DialogL = '10%'; titleFontSize = '6vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
                else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '40%'; DialogH = '30%'; DialogT = '35%'; DialogL = '30%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '60%'; DialogH = '20%'; DialogT = '40%'; DialogL = '20%'; titleFontSize = '4.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '40%'; DialogH = '20%'; DialogT = '40%'; DialogL = '30%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }
            }
            else if (title === 'Delete Article') { // set dialog dimensions in case of Delete Opportunity Confirmation dialog
                DialogW = '30%'; DialogH = '25%'; DialogT = '40%'; DialogL = '35%'; titleFontSize = '1vw'; contentFontSize = '1.1vw'; buttonFontSize = '0.8vw'; buttonH = '7vh'; logo_width = '22vw'
                if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '10%'; DialogT = '60%'; DialogL = '10%'; titleFontSize = '6vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
                else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '40%'; DialogH = '30%'; DialogT = '35%'; DialogL = '30%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '60%'; DialogH = '20%'; DialogT = '40%'; DialogL = '20%'; titleFontSize = '4.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '40%'; DialogH = '20%'; DialogT = '40%'; DialogL = '30%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }
            }
            else if (title === 'Google Calendar Events') {
                DialogW = '30%'; DialogH = '30%'; DialogT = '40%'; DialogL = '35%'; titleFontSize = '1vw'; contentFontSize = '1.4vw'; buttonFontSize = '0.8vw'; buttonH = '7vh'; logo_width = '22vw'
                if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '30%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '4vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
                else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '60%'; DialogH = '40%'; DialogT = '30%'; DialogL = '20%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '60%'; DialogH = '30%'; DialogT = '35%'; DialogL = '20%'; titleFontSize = '2.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '40%'; DialogH = '30%'; DialogT = '35%'; DialogL = '30%'; titleFontSize = '1.5vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }
            }
            // place order
            else if (title.includes('Order')) {
                DialogW = '30%'; DialogH = '30%'; DialogT = '40%'; DialogL = '35%'; titleFontSize = '1.2vw'; contentFontSize = '1.0vw'; buttonFontSize = '0.8vw'; buttonH = '7vh'; logo_width = '22vw'
                if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '100%'; DialogH = '40%'; DialogT = '30%'; DialogL = '0%'; titleFontSize = '4vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
                else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '60%'; DialogH = '40%'; DialogT = '30%'; DialogL = '20%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '60%'; DialogH = '30%'; DialogT = '35%'; DialogL = '20%'; titleFontSize = '2.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '40%'; DialogH = '30%'; DialogT = '35%'; DialogL = '30%'; titleFontSize = '1.5vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }
            }
            else {
                if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { DialogW = '90%'; DialogH = '70%'; DialogT = '30%'; DialogL = '5%'; titleFontSize = '6vw'; contentFontSize = '4vw'; buttonFontSize = '4vw'; buttonH = '5vh'; logo_width = '65vw' }
                else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { DialogW = '70%'; DialogH = '75%'; DialogT = '25%'; DialogL = '15%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '1.8vw'; buttonH = '7vh'; logo_width = '32vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { DialogW = '80%'; DialogH = '60%'; DialogT = '30%'; DialogL = '10%'; titleFontSize = '4.5vw'; contentFontSize = '3vw'; buttonFontSize = '3vw'; buttonH = '5vh'; logo_width = '36vw' }
                else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { DialogW = '50%'; DialogH = '70%'; DialogT = '15%'; DialogL = '25%'; titleFontSize = '2vw'; contentFontSize = '1.7vw'; buttonFontSize = '2vw'; buttonH = '7vh'; logo_width = '22vw' }
            }
            contentText = props.dialogProp['contentText'];

            button1Text = props.dialogProp['button1Text'];
            button2Text = props.dialogProp['button2Text'];
            // opaque = 0;
            coverDivColor = props.dialogProp['coverDivColor'];
            break;

        default:
            break;
    }


    const popupDialogStyle = {
        backgroundColor: tc.panelBg,
        color: tc.text,
        height: DialogH,
        width: DialogW,
        top: DialogT,
        left: DialogL,
        display: 'flex',
        flexDirection: 'column',
        border: '1px solid ' + tc.border,
    }



    const contentDivStyle = {
        // backgroundColor: "red",
        height: '94%',
        width: '100%',
        top: '0%',
        left: 0,
        fontSize: contentFontSize,
    }
    const acknowledgeDivStyle = {
        // backgroundColor: "blue",
        height: title === 'Delete Opportunity' ? '30%' : '10%',
        width: '100%',
        top: '90%',
        left: '0',
        display: 'flex',
        justifyContent: 'flex-end'
    }

    const contentDetailDivStyle = {
        // display:'flex',
        backgroundColor: "transparent",
        height: '84%',
        width: '90%',
        marginLeft: '5%',
        marginTop: '2%',
        lineHeight: line_height,
    }

    const continueStyle = {

        height: '100%',
        width: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid ' + tc.border
    }
    const cancelStyle = {

        rightBorder: '1px ' + tc.border + ' solid',
        height: '100%',
        width: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: '1px solid ' + tc.border
    }

    const rightButtonClicked = () => {


        if (props.dialogType === 'strategist-feature') {
            upgradeToInstitutional();
            return;
        }

        if (props.dialogType === 'info-box') {
            props.SetInfoBoxVisible(false);

            if (props.dialogProp['title'] === 'Too Many Requests') {
                window.location.href = '/';
            }

            else if (props.dialogProp['title'] === 'Delete Opportunity') {  // run the delete function in 
                let dr_id = 0;
                delOpportunity(props.dialogProp['dr_id'], token);

            }
            else if (props.dialogProp['title'] === 'Place Order') {
                // run the place order function in TradeInstrument.js  1/11/2024

                props.dialogProp['placeCreditspreadTrade'](); // this function was passed with a state variable from TradeInstrument.js

            }
            else if (props.dialogProp['title'] === 'Place Market Exit Order') {
                props.dialogProp['ExecuteFuncAfterConfirmation']();
            }

            else if (props.dialogProp['title'] === 'Delete Article') {
                props.dialogProp['ExecuteFuncAfterConfirmation']();
            }
            else if (props.dialogProp['title'] === 'Place Conditional Exit Orders') {
                props.dialogProp['ExecuteFuncAfterConfirmation']();
            }
            else if (props.dialogProp['title'] === 'Cancel Order') {
                props.dialogProp['CancelOrder'](); // this function was passed with a state variable from TradeInstrument.js
            }




        }

        if (props.dialogType === 'free-register' || props.dialogType === 'anonymous-user' || props.dialogType === 'register' || props.dialogType === 'rate-limit') {
            window.location.href = '/login'
        }



        if (props.dialogType === 'terms-conditions') {
            if (termsCheckBox) {
                props.SetInfoBoxVisible(false);

                let cookie = getCookie('first1');

                if (cookie === null) {
                    props.SetHelpBoxVisible(true);
                    setCookie('first1', 1, 300);
                }
            }

            else {
                SetCheckboxNotificationColor('red') //if continue is clicked without selecting the checkbox, notification color changes from transparent to red
            }
        }
    }
    //------------------------------------------------------------------------------------------------------------------
    const leftButtonClicked = () => {

        // console.log('props.dialogType =', props.dialogType)

        if (props.dialogType === 'free-register') { props.SetInfoBoxVisible(false); return }
        else if (props.dialogType === 'register') { props.SetInfoBoxVisible(false); }
        else if (props.dialogType === 'rate-limit') {
            // window.location.href = '/'; 
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'strategist-feature') { props.SetInfoBoxVisible(false); }
        else if (props.dialogProp['title'] === 'Delete Article') { props.SetInfoBoxVisible(false); }
        else if (props.dialogType === 'terms-conditions') {
            window.location.href = '/';
        }
        else if (props.dialogProp['title'] == 'Delete Opportunity') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogProp['title'] == 'Cannot Delete Opportunity') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'Place Order') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'Place Market Exit Order') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'Place Conditional Exit Order') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'Error Placing Order') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'Cancel Order') {
            props.SetInfoBoxVisible(false);
        }
        else if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'Ins') {
            props.SetInfoBoxVisible(false);
        }


        else if (title === 'Opportunities Limit Reached' || title === 'Daily Limit Reached') {
            props.SetInfoBoxVisible(false);

            if (loggedinUser === 0) {
                window.location.href = '/#pricing';
            }
            else {
                window.location.href = '/pricing';
            }

        }

    }


    //------------------------------------------------------------------------------------------------------------------
    const cbChanged = () => {
        SetTermsCheckBox(!termsCheckBox)
    }
    //------------------------------------------------------------------------------------------------------------------
    // info-box with title of delay will close in 2 seconds
    //------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        if (props.dialogType === 'info-box' && props.dialogProp['title'] === 'delay') {

            let delay_seconds = 5;

            if ('delay' in props.dialogProp) {
                delay_seconds = props.dialogProp['delay'];
            }



            const timer = setTimeout(() => {
                props.SetInfoBoxVisible(false)
            }, delay_seconds * 1000);

            return () => clearTimeout(timer);
        }

    }, []);
    //----------------------------------------------------------------------------------------------------------------------------------------
    // this function is to delete a user saved web report - had to be here because after confirmation need access to  props.numReportsCreated 
    // this is before I figured out I could have passed this function from the calling component :(  1/24/2024
    //----------------------------------------------------------------------------------------------------------------------------------------

    const delOpportunity = (dr_id, token) => {

        // console.log('del confirmed triggered - ', dr_id)



        let asURL = appserverURL()
        let url = `${asURL}/dr_report_remove/${dr_id}?token=${token}`
        var tmp

        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })
            .then((data) => {
                props.SetNumReportsCreated(props.numReportsCreated - 1); // decrement after a web report is deleted
                props.SetReportsList([])
            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });

    }

    const upgradeToInstitutional = () => {
        const url = (loggedinUser === '0')
            ? '/#pricing'
            : '/pricing';

        window.open(url, '_blank', 'noopener,noreferrer');

        // close the dialog
        props.SetInfoBoxVisible(false);
    };

    //----------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div className='main-cover' style={{ backgroundColor: coverDivColor, zIndex: 9999 }} >

            <div className='dialog-popup' style={popupDialogStyle}  >

                {(props.dialogProp['title'] !== 'Delete Opportunity' && props.dialogProp['title'] !== 'delay') &&  /* hide title for Delete Opportunity Confirmation */
                    <div className='dialog-top-row'>

                        <div style={{ width: '100%', display: 'flex', backgroundColor: 'transparent' }}>

                            {/* <div className='dialog-logo'>
                                <img src={"data:image/png;base64, " + logo64} alt="" style=f'{{ width: logo_width }} />
                            </div> */}

                            <div className='dialog-title'>
                                <span style={{ fontSize: titleFontSize }} > <b>{title}</b>  </span>
                            </div>
                        </div>

                    </div>
                }
                <div style={contentDivStyle} >

                    {props.dialogType === 'terms-conditions'
                        &&
                        <div style={contentDetailDivStyle}>
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent' }}>
                                {contentText}
                            </div>

                            <div style={{ width: '100%', height: '70%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
                                <button className='button' style={{ fontSize: buttonFontSize, height: buttonH }} onClick={() => window.open('/terms.html', '_blank')}>Terms of Service</button>
                                <button className='button' style={{ fontSize: buttonFontSize, height: buttonH }} onClick={() => window.open('/privacy.html', '_blank')}>Privacy Policy</button>
                                <button className='button' style={{ fontSize: buttonFontSize, height: buttonH }} onClick={() => window.open('/disclaimer.html', '_blank')}>Risk Disclosure</button>
                            </div>

                            {/* this div is only for smartphone portrait  */}
                            <div style={{ width: '70%', display: display_smartphonep, alignItems: 'center', justifyContent: 'flex-end' }}>
                                <span style={{ color: 'black' }}> <a href='/#pricing'>register</a> or <a href='/login'>login</a></span>
                            </div>

                            {/* notification when they don't click */}
                            <div style={{ width: '100%', height: '10%', display: 'flex', flexDirection: 'row', alignItems: 'flex-end', }}>
                                <span style={{ color: checkboxNotificationColor }} >click the checkbox to continue</span>
                            </div>

                            <div style={{ width: '100%', height: '10%', display: 'flex', flexDirection: 'row', alignItems: 'center', }}>

                                <div style={{ width: '100%', display: 'flex' }}>
                                    <div style={{ paddingLeft: '5px', paddingRight: '5px', display: 'flex' }}>
                                        <CheckBox checked={termsCheckBox} cbChanged={cbChanged} />
                                    </div>
                                    <div >
                                        <span> I accept the terms of the agreement</span>
                                    </div>
                                </div>



                                {/* this div is not for smartphone portrait.  its for everything else  */}
                                <div style={{ width: '34%', display: display_not_smartphonep, alignItems: 'center', justifyContent: 'flex-end' }}>
                                    <span style={{ color: 'black' }}> <a href='/#pricing'>register</a> or <a href='/login'>login</a></span>
                                </div>

                            </div>





                        </div>

                    }

                    {props.dialogType === 'free-register'
                        &&
                        <div style={contentDetailDivStyle}>
                            <div style={{ width: '100%', height: '80%', backgroundColor: 'transparent' }}>
                                {contentText}
                            </div>
                            <div style={{ width: '100%', height: '00%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexDirection: 'column' }}>

                            </div>
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <button style={{ fontSize: buttonFontSize, height: buttonH }} className='button' onClick={() => window.open('/#pricing', '_blank')}>Membership Plans</button>
                            </div>

                        </div>

                    }
                    {(props.dialogType === 'register' || props.dialogType === 'rate-limit')
                        &&

                        <div style={contentDetailDivStyle}>
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent' }}>
                                {contentText}
                            </div>
                            <div style={{ width: '100%', height: '60%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexDirection: 'column' }}>
                                <button style={{ fontSize: buttonFontSize, height: buttonH }} className='button' onClick={() => window.open('/login', '_blank')}>Register</button>
                            </div>
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>

                            </div>

                        </div>

                    }

                    {props.dialogType === 'strategist-feature'
                        &&

                        <div style={contentDetailDivStyle}>
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent' }}>
                                <p style={{ whiteSpace: 'pre-wrap' }}> {contentText} </p>
                            </div>
                            {/* <div style={{ width: '100%', height: '60%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexDirection: 'column' }}>
                                <button style={{ fontSize: buttonFontSize, height: buttonH }} className='button' onClick={upgradeToInstitutional}>Upgrade to Strategist</button>
                            </div> */}
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>

                            </div>

                        </div>

                    }




                    {props.dialogType === 'info-box' && props.dialogProp['title'] !== 'Place Order'
                        &&
                        <div style={contentDetailDivStyle}>
                            <div style={{ width: '100%', height: '99%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>

                                {contentText}

                            </div>

                            {(props.dialogProp['title'] === 'Portfolio Manager' || props.dialogProp['title'] === 'Settings') &&
                                <p>
                                    <span style={{ color: 'black' }}> <a href='/#pricing'>register</a> or <a href='/login'>login</a></span>
                                </p>
                            }
                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>
                            </div>
                        </div>
                    }

                    {props.dialogType === 'info-box' && props.dialogProp['title'] === 'Place Order'
                        &&
                        <div style={contentDetailDivStyle}>
                            <div style={{ width: '100%', height: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>

                                <div style={{ height: '14%', width: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: `${contentText["line1j"]}`, alignItems: 'center' }}>{contentText['line1']}</div>


                                <div style={{ height: '14%', width: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: `${contentText["line2j"]}`, alignItems: 'center', fontWeight: 'bold' }}>{contentText['line2']}</div>
                                <div style={{ height: '14%', width: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: `${contentText["line3j"]}`, alignItems: 'center', fontWeight: 'bold' }}>{contentText['line3']}</div>


                                <div style={{ height: '14%', width: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: `${contentText["line4j"]}`, alignItems: 'right' }}>{contentText['line4']}</div>

                                <div style={{ height: '14%', width: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: `${contentText["line5j"]}`, alignItems: 'center' }}>{contentText['line5']}</div>
                                <div style={{ height: '14%', width: '100%', backgroundColor: 'tranparent', display: 'flex', justifyContent: `${contentText["line6j"]}`, alignItems: 'center' }}>{contentText['line6']}</div>
                                <div style={{ height: '14%', width: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: `${contentText["line7j"]}`, alignItems: 'center' }}>{contentText['line7']}</div>

                            </div>



                            <div style={{ width: '100%', height: '20%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>
                            </div>
                        </div>
                    }



                </div>


                {props.dialogProp['title'] !== 'delay' &&
                    <div className='dialog-footer' style={acknowledgeDivStyle}>
                        <div>

                        </div>
                        <div style={cancelStyle} onClick={leftButtonClicked}>
                            <span className='no-select' style={{ color: 'white', fontSize: buttonFontSize, cursor: 'default' }}>{button1Text}</span>
                        </div>

                        <div style={continueStyle} onClick={rightButtonClicked}>
                            <span className='no-select' style={{ color: 'white', fontSize: buttonFontSize, cursor: 'default' }}>{button2Text}</span>
                        </div>
                    </div>
                }

            </div>


        </div>
    )
}

export default InfoPopup
