/*

I'm resuing google calendar event window for auto trading.  
if portoflio name starts with & then the calendar icon changes to a robot.
interface to view and monitor order are displayed in this dialog

the dialog is called google calendar events something 


*/


import React, { useContext, useEffect, useRef, useState } from 'react'
import TableBoxReports from './TableBoxReports'
import { UserContext } from './UserContext'
import { helpVideos } from './Videos'
import { appserverURL } from './Common'
import './styles/InfoPopup.css'

import ErrorBoundary from './ErrorBoundary';
import { getSelectedIDFromSecuritiesList2 } from './Common'
import jwt_decode from 'jwt-decode'
import { incrementDate } from './Common'
import { getTodayDate } from './Common'
import SelectBox from './SelectBox'
import Tippy from '@tippyjs/react'
import { brand, trend_chart_left_gap_days } from './Common'
import { getCookie, setCookie } from './Common'

import { BiSolidSquare, BiSquare } from "react-icons/bi"
import { statusColor, themeColors } from './Common'
import { MdRocket } from "react-icons/md";
import { IoMdDownload } from "react-icons/io";
import { BsPlus, BsFolderSymlink, BsTrash3 } from "react-icons/bs"
import { SlSettings } from "react-icons/sl";
import { GrEdit } from "react-icons/gr";
import { BsPencil, BsFillPenFill } from "react-icons/bs"
import { LiaClipboardListSolid } from "react-icons/lia";
import { GrClose } from "react-icons/gr";

import { RiArticleLine, RiArticleFill } from "react-icons/ri";  // for news article switches <RiArticleLine />  

import { userlist_amp, userlist_auto, userlist_article } from './Common'

import { IoNewspaperSharp } from "react-icons/io5";
import { GiAutomaticSas } from "react-icons/gi"; // total automation icon for news articles



const CLIENT_ID = process.env.REACT_APP_CLIENT;
const SCOPES = process.env.REACT_APP_SCOPES;
const CLIENT_SECRET = process.env.REACT_APP_GOOGLE_CLIENT_SECRET;
const APIKEY = process.env.REACT_APP_GOOGLE_API_KEY;



const ReportsDashboard = (props) => {


    const { numReportsAllowed, browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)
    const tc = themeColors(props.UITheme)

    const [rowIndexDRclicked, SetRowIndexDRclicked] = useState(null) // this is the visible UI row index
    const [clickedRowIndex, SetClickedRowIndex] = useState(-1);      // actual row index from the data

    // this holds a list of dictionaries with investment + current value + % gain/loss for tooltips
    const [oppValues, SetOppValues] = useState([]);
    const [oppValuesTotal, SetOppValuesTotal] = useState({});
    const [showDiv, setShowDiv] = useState('none'); // this is used to add delay for description div when no opps are added yet
    const [portfolioTableLength, SetPortfolioTableLength] = useState(0)
    const [publishDate, setPublishDate] = useState(getTodayDate());

    const [securityData, SetSecurityData] = useState(
        {
            'value1': '',
            'value2': '',
            'value3': '',
            'bgcolor': 'transparent'  // this is the background color of the last_price - based on if it has gone up or down it changes
        }
    )

    const [totalInvestedStatus, SetTotalInvestedStatus] = useState(0);

    const [newsToggle, SetNewsToggle] = useState(() => localStorage.getItem('newsToggle') === '1') // switches news toggle icon on and off
    // const [articleVer, SetArticleVer] = useState(0); // this is just used to refresh loading the reports list when
    // publishArticl creates a new article or deletes one - so it refreshes
    //-------------------------------------------------------------------------------------------
    // props.SetSelectedPortfolio and props.selectedPortfolio is used to put reports in the right portfolio
    //-------------------------------------------------------------------------------------------

    // Drag state - null means use default CSS position, {x,y} px means user has dragged it
    const [dragPos, setDragPos] = useState(null);
    const dragRef = useRef({ active: false, offsetX: 0, offsetY: 0 });

    // Reset position every time the dialog opens
    useEffect(() => {
        if (!props.reportsDashVisible) setDragPos(null);
    }, [props.reportsDashVisible]);

    // Window-level mouse listeners for drag
    useEffect(() => {
        const onMouseMove = (e) => {
            if (!dragRef.current.active) return;
            const x = Math.max(0, Math.min(window.innerWidth  - 200, e.clientX - dragRef.current.offsetX));
            const y = Math.max(0, Math.min(window.innerHeight - 60,  e.clientY - dragRef.current.offsetY));
            setDragPos({ x, y });
        };
        const onMouseUp = () => { dragRef.current.active = false; };
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup',   onMouseUp);
        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup',   onMouseUp);
        };
    }, []);

    const handleTitleMouseDown = (e) => {
        if (rdd.isMobile) return;
        if (e.detail === 2) { setDragPos(null); return; }
        // Find the dialog element to get its current screen position
        const dialog = e.currentTarget.closest('.dialog-popup-reports-dashboard');
        if (!dialog) return;
        const rect = dialog.getBoundingClientRect();
        dragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top };
        e.preventDefault(); // prevent text selection while dragging
    };

    // desktop values are default
    // factor is used to create this dialogbox at dimensions of the opporutnities manager divided by factor
    var DialogW = '60%', DialogH = '57%', DialogT = '25%', DialogL = '20%', titleFontSize = '1.0vw', contentFontSize = '1.1vw', rowHeight = '30px', factor = 1.14;

    var opp_saved_text = 'Saved Patterns';
    var opp_remaining_text = 'Remaining';

    var title_width = '86%', title_close_width = '3.5%'; //86% is because there are 2 small divs on the left and 2 on the right
    var controls_fontsize = '0.75vw';
    var grclose_iconsize = 18;

    var title_height = '7%';
    var controls_height = '7%';
    var content_height = '79%';
    var stats_height = '7%';

    var opp_info_footer_height = '7%';

    var data1title = 'Total Invested:';
    var data2title = 'Total Current Value:';
    var data3title = 'Total % Gain or Loss';
    // these are titles for the securities info row
    var sdata1title = 'Security Purchase Price:';
    var sdata2title = '# Shares:';
    var sdata3title = 'Security Last Price';

    var statsFontFamily = 'sans-serif';

    var statsFontSize = '0.7vw';

    var portPlusSize = '25';
    var portMoveSize = '20';

    var listIconSize = '18';

    var newspaperIconSize = '20';

    var articleIconSize = '23';

    var portTrashSize = '15';
    var port_icon_div_width = '2vw';
    var controlWidth = ['60%', '20%', '20%'] // width of 3 sections of the controls of portfolio manager

    var main_cover_css_position = 'absolute';  // do not do absolute position for mobile smartphone


    var icon_status_size = 17;


    var savedFontSize = '0.8vw';


    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {

        title_height = '5%';
        controls_height = '7%';
        content_height = '85%';
        stats_height = '5%';
        opp_info_footer_height = '5%';

        data1title = 'Invested:';
        data2title = 'Value:';
        data3title = '% Gain/Loss';

        sdata1title = 'Buy Price:';
        sdata2title = '# Shares:';
        sdata3title = 'Last Price';

        DialogW = '100%';
        DialogH = '88%';
        DialogT = '12%';
        DialogL = '0%';
        titleFontSize = '4vw';
        contentFontSize = '3vw';
        rowHeight = '45px';
        factor = 1.0;

        opp_saved_text = 'Saved'
        opp_remaining_text = 'Remains';

        title_width = '80%';
        title_close_width = '10%';
        title_height = '5%';
        controls_fontsize = '3.5vw';
        grclose_iconsize = 15;
        statsFontSize = '2.5vw';

        portPlusSize = 25;
        portMoveSize = 18;
        portTrashSize = 15;
        port_icon_div_width = '9vw';
        controlWidth = ['85%', '0', '14%']
        savedFontSize = '3vw';
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
        statsFontSize = '1.3vw';
        DialogW = '100%';
        DialogH = '100%'; //////////////////////////////////////////
        DialogT = '20%';
        DialogL = '0';
        titleFontSize = '2.0vw';
        contentFontSize = '2.0vw';
        controls_fontsize = '2vw';
        grclose_iconsize = 15;
        main_cover_css_position = 'static';
        statsFontSize = '1.5vw';
        portMoveSize = 17;
        port_icon_div_width = '4vw';

        sdata1title = 'Buy Price:';
        sdata2title = '# Shares:';
        sdata3title = 'Last Price';
        savedFontSize = '1.8vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) {
        DialogW = '90%';
        DialogH = '70%';
        DialogT = '15%';
        DialogL = '5%';
        titleFontSize = '2.5vw';
        contentFontSize = '2.0vw';
        title_width = '90%';
        title_close_width = '5%';
        controls_fontsize = '2.2vw';
        grclose_iconsize = 15;
        statsFontSize = '2vw';
        data1title = 'Invested:';
        data2title = 'Value:';
        data3title = '% Gain/Loss';

        sdata1title = 'Buy Price:';
        sdata2title = '# Shares:';
        sdata3title = 'Last Price';

        title_height = '5%';
        controls_height = '5%';
        content_height = '83%';
        stats_height = '7%';

        port_icon_div_width = '4vw';
        savedFontSize = '1.8vw';

        if (browserH > 1024) portMoveSize = '22';
        else portMoveSize = '17';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) {
        DialogW = '70%';
        DialogH = '50%';
        DialogT = '25%';
        DialogL = '15%';
        titleFontSize = '2vw';
        contentFontSize = '1.6vw';
        controls_fontsize = '1.2vw';
        grclose_iconsize = 15;
        statsFontSize = '1vw';

        portMoveSize = '15';

        port_icon_div_width = '3vw';

        sdata1title = 'Buy Price:';
        sdata2title = '# Shares:';
        sdata3title = 'Last Price';
        savedFontSize = '1.2vw';
    }

    //-----------------------------------------------------------------------------------------------------------

    const popupDialogStyle = {
        backgroundColor: tc.panelBg,
        color: tc.text,
        height: DialogH,
        width: DialogW,
        ...(dragPos
            ? { position: 'fixed', top: dragPos.y, left: dragPos.x, boxShadow: '0 8px 32px rgba(0,0,0,0.35)' }
            : { top: DialogT, left: DialogL }),
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid ' + tc.border,
        alignItems: 'center'
    }


    const titleDiv = {
        backgroundColor: tc.titleBar,
        height: title_height,
        width: '100%',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        fontSize: titleFontSize,
        color: tc.textOnControl,
        fontWeight: 'bold',
        textTransform: 'uppercase'
    }

    const controlsDiv = {
        backgroundColor: tc.panelBg,
        height: controls_height,
        width: '100%',
        display: 'flex',
        justifyContent: 'left',
        alignItems: 'center',
        paddingLeft: '5px',
        // fontSize: tableTitleTextSize,
        // fontSize: contentFontSize,
        fontSize: controls_fontsize,
        color: tc.text,
        fontFamily: 'sans-serif'
    }

    const controlItem = {

    }

    const contentDiv = {
        backgroundColor: tc.panelBg,
        height: content_height,
        display: 'flex',
        width: '100%',
        overflowY: 'auto',
        fontSize: contentFontSize
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useEffect is run when the dialog is first opened and gets the list of reports for the loggedin user
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {
        let asURL = appserverURL()
        let userid = loggedinUser;

        let articleToggle = newsToggle ? 1 : 0; // passing to react if news icon is toggled on as 0 or 1

        let url = `${asURL}/dr_report_list/${props.selectedPortfolioID}/${articleToggle}?token=${token}`

        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                var tmp = data['reports_list'];

                for (let i = 0; i < tmp.length; i++) tmp[i].id = i; // add a sequence of numbers for id for future reference
                props.SetReportsList(tmp)
                // console.log('lllllllllist=', tmp)
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });


    }, [props.reportsDashVisible, props.reportsList.length, props.selectedPortfolioID, props.numReportsCreated, props.showPopulatePortfolio, newsToggle]);
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useEffect is run initially when dialog is opened and run again when status color icon next to Total Invested is changed
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        var today_date = getTodayDate();

        // create the investment+gain for each of the opportunities and set it up for tooltips + total investment
        let opptmp = [];
        let total_invested = 0.0;
        let total_current_value = 0.0;

        let current_selected_status = totalInvestedStatus; // this is shown by the color next to Total Invested on the bottom row 




        // console.log(props.reportsList);


        let tmp = [...props.reportsList] // just lazy so I copied it to tmp - this is because I copied it from another useEffect and created a new useEffect

        if (props.reportsList) {
            for (let i = 0; i < tmp.length; i++) {



                let status = parseInt(tmp[i]['status']); // status is the colored square on the left 

                if (totalInvestedStatus !== 0 && totalInvestedStatus != status) {
                    continue;  // we are only using the values that match the selected flag - unless no flag then adds up all.
                }

                var v = {};
                var p = parseFloat(tmp[i]['price1']);
                var n = parseInt(tmp[i]['num_shares']);
                v['pct_profit_loss'] = tmp[i]['gain_loss']

                if (tmp[i]['date'] <= today_date) {
                    v['invested'] = n * p;
                }
                else { // this opportunity has not started yet
                    v['invested'] = 0
                }

                // only add to total invested if the start date is today or in the past
                if (tmp[i]['date'] <= today_date) {
                    total_invested += v['invested'];
                }
                if (tmp[i]['direction'] === 'long') {
                    v['current_value'] = v['invested'] * (1 + parseFloat(tmp[i]['gain_loss']) / 100);
                    total_current_value += v['current_value'];
                }
                else {
                    v['current_value'] = v['invested'] * (1 - parseFloat(tmp[i]['gain_loss']) / 100);
                    total_current_value += v['current_value'];
                }

                // round numbers
                v['current_value'] = Math.ceil(v['current_value']);
                v['invested'] = Math.ceil(v['invested']);

                v['current_value'] = v['current_value'].toLocaleString();
                v['invested'] = v['invested'].toLocaleString();

                v['num_shares'] = n;
                // console.log(v)

                opptmp.push(v);

            }
            // calculate total profit loss percent
            var total_pct_profit_loss = 0;
            if (total_invested > 0) {
                total_pct_profit_loss = 100 * (total_current_value - total_invested) / total_invested;
                total_pct_profit_loss = total_pct_profit_loss.toFixed(2);
            }
            // console.log('total_pct_profit_loss=',total_pct_profit_loss.toFixed(2))

            // convert the total_invested to integers
            total_invested = Math.ceil(total_invested)
            total_current_value = Math.ceil(total_current_value)
            // add commas to the total_invested and current value numbers
            total_invested = total_invested.toLocaleString()
            total_current_value = total_current_value.toLocaleString()

            let tmp_total = { 'total_invested': total_invested, 'total_current_value': total_current_value, 'total_pct_profit_loss': total_pct_profit_loss }
            // console.log('tmp_total=',tmp_total);

            SetOppValues(opptmp);
            SetOppValuesTotal(tmp_total)

            // console.log(opptmp, tmp_total)

            // props.SetSelectedPortfolioRec('') // initialize the selected slug - its set when a row is clicked and its used for Note

        }

    }, [totalInvestedStatus, props.reportsList]);
    //-------------------------------------------------------------------------------------------------------------------------------------
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useEffect is run when the dialog is first opened and gets the list of portfolios for the loggedin user
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {
        let asURL = appserverURL()
        let url = `${asURL}/get_user_portfolio_names?token=${token}`



        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })
            .then((data) => {
                let tmp = []
                // console.log('......................portfolio data=', data['portfolio_names_list'])
                for (let i = 0; i < data['portfolio_names_list'].length; i++) {
                    tmp.push({ id: data['portfolio_names_list'][i]['id'], value: data['portfolio_names_list'][i]['name'], label: data['portfolio_names_list'][i]['name'] });
                }
                props.SetPortfolios(tmp);

                // not necessary here to retreive the last selected portfolio because its initialized in app.js and cookie is read there

                // let cookie = getCookie('selected_portfolio')

                // // retrieve the last selected portfolio
                // if (cookie !== null){
                //     let sp = cookie.split(',')
                //     props.SetSelectedPortfolioID(sp[0])
                //     props.SetSelectedPortfolio(sp[1])
                // }




            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });


    }, []);

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handlerKeyDown = (event) => {
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handlerTotalInvestedIcon = (event) => {

        // console.log('props.reportsList=',props.reportsList)

        let newStatus = totalInvestedStatus + 1;
        if (newStatus >= Object.keys(statusColor).length) {
            newStatus = 0;
        }
        SetTotalInvestedStatus(newStatus);
    }
    //-------------------------------------------------------------------------------------------------------------------
    // this is for tooltip of the individual opportunities when hove3red over %
    //-------------------------------------------------------------------------------------------------------------------
    const getCurValue = (row) => {

        let today_date = getTodayDate();
        let td = JSON.parse(JSON.stringify(props.reportsList));
        if (td.length === 0) return '';
        let idx = row['id'];
        if (td[idx]['date'] > today_date) return '$0';
        let price = parseFloat(td[idx]['price1']);
        let shares = parseInt(td[idx]['num_shares']);
        let investment = shares * price;

        let cur_val = 0;
        if (td[idx]['direction'] === 'long') {
            cur_val = investment * (1 + td[idx]['gain_loss'] / 100);
        }
        else {
            cur_val = investment * (1 - td[idx]['gain_loss'] / 100);
        }
        cur_val = Math.ceil(cur_val);
        cur_val = cur_val.toLocaleString();
        return '$' + cur_val;
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handlerRowClicked = (rowIndex) => (event) => { // this is to handleRowClicked in TableBox

        // console.log('handler row clicked event trigered')

        if (rowIndexDRclicked !== rowIndex && rowIndex !== null) {

            // console.log('HHH','rowIndexDRclicked , rowIndex = ',rowIndexDRclicked , rowIndex)

            SetRowIndexDRclicked(rowIndex);
            // find the dr_id for the selected opp and save it for Note
            let parentRow = event.target.closest("tr");
            let firstCell = parentRow.querySelector("td:first-child");
            let idx = firstCell.innerText;

            SetClickedRowIndex(parseInt(idx));

            let dr_id = props.reportsList[idx]['dr_id']

            props.SetSelectedDRID(dr_id)
            props.SetSelectedPortfolioRec(props.reportsList[idx])

            // console.log('sssssssssssssssssselected profolio record=',props.reportsList[idx])
        }

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this is useful when a queue date is updated in publisharticle then this state variable is updated also
    useEffect(() => {
        if (clickedRowIndex == null) return;
        if (!props.reportsList || props.reportsList.length <= clickedRowIndex) return;

        props.SetSelectedPortfolioRec(props.reportsList[clickedRowIndex]);
    }, [props.reportsList, clickedRowIndex]);
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {
        // update securityData for display on the security row below

        if (clickedRowIndex === -1) return; // this is the first time before any row selected

        let security_purchase_price = parseFloat(props.reportsList[clickedRowIndex]['price1']).toFixed(2);
        let security_num_shares = parseInt(props.reportsList[clickedRowIndex]['num_shares']);
        let gain_loss = parseFloat(props.reportsList[clickedRowIndex]['gain_loss']);


        let security_current_price = (security_purchase_price * (1 + gain_loss / 100)).toFixed(2);

        let tmp = { ...securityData }; // making a copy of securityData object 

        tmp['value1'] = '$' + security_purchase_price.toString();
        tmp['value2'] = security_num_shares.toString();
        tmp['value3'] = '$' + security_current_price.toString();

        tmp['bgcolor'] = 'transparent'; // this is the color if gain_loss===0
        if (gain_loss > 0) tmp['bgcolor'] = tc.profitRowBg;
        else if (gain_loss < 0) tmp['bgcolor'] = tc.lossRowBg;



        SetSecurityData(tmp);


    }, [clickedRowIndex])

    //-------------------------------------------------------------------------------------------------------------------------------------
    // Add a report to the queue for blog creation - called from handleAddReport and handleRefresh
    // type is either 'new' or 'refresh'
    //------------------------------------------------------------------------------------------------------------------------------------- 
    const AddReportCreationJob = (id, symbol, date, days_hold, years, direction, sharpe_ratio, type) => {
        let asURL = appserverURL()
        let selected_portfolio = props.selectedPortfolio;

        let url = `${asURL}/dr_report_publish/${id}/${symbol}/${date}/${days_hold}/${years}/${direction}/${sharpe_ratio}/${selected_portfolio}?token=${token}`
        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })
            .then((data) => {

                // console.log(data)

                // don't need dialogs here - its just precaution to add teh report creation.  if its a duplicate so be it -
                // it only useful if report has been deleted somehow
                // if (type == 'new') {
                //     if (data['publish_dr_report'] === 'success') {
                //         props.SetDialogProp({ title: 'delay', contentText: 'Opportunity Added', button1Text: '', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                //     }
                //     else if (data['publish_dr_report'] === 'duplicate') {
                //         props.SetDialogProp({ title: 'delay', contentText: 'Duplicate', button1Text: '', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                //     }
                //     else { // should not happen
                //         props.SetDialogProp({ title: 'delay', contentText: 'should not happen', button1Text: '', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                //     }
                //     props.SetDialogType('info-box');
                //     props.SetInfoBoxVisible(true)
                // }

                // else if (type == 'refresh') {
                //     props.SetDialogProp({ title: 'delay', contentText: 'Web Report Refresh Requested', button1Text: '', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                // }
                // else {
                //     props.SetDialogProp({ title: 'delay', contentText: 'should not happen', button1Text: '', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                // }

            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });
    };
    //-------------------------------------------------------------------------------------------------------------------------------------
    // new report added by clicking the plus in reports dashboard dialog
    // THIS FUNCTION IS DUPLICATED IN SEASONAL BARCHART DUE TO ISSUES WITH PROPS SCOPE - CHANGES ARE REQUIRED IN BOTH PLACES
    //------------------------------------------------------------------------------------------------------------------------------------- 
    const handleAddReport = () => {
        // new report added by clicking the plus in reports dashboard dialog
        // let asURL = appserverURL()
        let id = getSelectedIDFromSecuritiesList2(props.securityTypeList, props.selectedSecurity)
        let symbol = props.symbol
        let date = props.startDate
        let days_hold = props.daysOut;
        let years = props.seasonalYears;
        // let base_year = date.substring(0, 4); // base_year is used for naming subfolder in wordpress and seasonal chart begin end dates
        // let zero_last_year = "False"; // this is a python false
        // let category = 0; // category 0 means use the default for the call - in this case its a date range report
        // let userid = loggedinUser;
        let direction = props.tradeDetailData['Trade Dir']
        let sharpe_ratio = props.tradeDetailData['Sharpe Ratio']



        // AddReportCreationJob(id, symbol, date, days_hold, years, direction, sharpe_ratio, 'new') // type new is just added vs refresh

        // if the length is 0 add a dummy entry first to trigger the useEffect, otherwise, setting the reportList to [] will trigger it
        if (props.reportsList.length === 0) props.SetReportsList({ date: '2023-02-02', days_hold: '156', dr_id: 1, resourceID: '0', slug: '', symbol: '0000', years: '12', direction: 'long', sharpe_ratio: '2.43' },)
        else props.SetReportsList([])

    }
    //-------------------------------------------------------------------------------------------------------------------------------------

    const handlerLoadClicked = (index, event) => {

        let parentRow = event.target.closest("tr");
        let firstCell = parentRow.querySelector("td:first-child");
        let idx = firstCell.innerText;


        let rid = props.reportsList[idx]['resourceID']
        let resource_group = resourceObj[parseInt(rid)]

        let date = props.reportsList[idx]['date']
        let years = props.reportsList[idx]['years']

        // Handle PE cycle years (both new format "pe2-10" and legacy format "pe2")
        if (years.toLowerCase().includes('pe')) {
            if (years.includes('-')) {
                // New format: PE2-10
                let sp = years.split('-');
                props.SetPEselected(sp[0].toLowerCase());
                years = sp[1];
            } else {
                // Legacy format: PE2 (no number of years)
                // Set to max available (99 will be capped by available data)
                props.SetPEselected(years.toLowerCase());
                years = '99';
            }
        } else {
            // Consecutive years
            props.SetPEselected('cons');
        }

        let ticker = props.reportsList[idx]['symbol']
        let days = props.reportsList[idx]['days_hold']

        props.SetOpportunities([])
        props.SetStartDate(date)

        let trend_chart_start_date = incrementDate(date, -trend_chart_left_gap_days); // set to 2 weeks before  - set in common 
        props.SetTrendChartStartDate(trend_chart_start_date)

        // Removed the condition as it was causing displaying broken charts when going from one opp to another
        // and the number of years being the same and symbol being the same.  no reason for the conditiona
        // if (ticker !== props.symbol || years !== props.seasonalYears) {
        props.SetSymbol(ticker)


        props.SetSeasonalYears(years)


        props.SetConsolidatedSeasonalData([])
        props.SetRefreshKey(prev => prev + 1); // here prev is really refreshKey so it gets incremented somehow - per chatGPT 3/27/2025
        // }
        props.SetDaysOut(days)
        props.SetMonthsAndQtrs('Months & Qtrs')

        props.SetReportsDashVisible(false)
        props.SetSelectedSecurity(resource_group)

        if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
            props.chartTo(1)
        }

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // delete an opportunity
    const handlerDelClicked = (index, event, orders) => {

        // if orders is true and name of the portfolio starts with & cannot delete it

        if (props.selectedPortfolio[0] === '&' && orders) { // must not delete - because this opportunity has brokerage orders 
            contentText = 'Cannot delete an opportunity with brokerage orders'
            props.SetDialogType('info-box');
            props.SetDialogProp({ title: 'Cannot Delete Opportunity', contentText: contentText, button1Text: 'Close', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
            props.SetInfoBoxVisible(true)

            return;
        }

        let parentRow = event.target.closest("tr");
        let firstCell = parentRow.querySelector("td:first-child");
        let idx = firstCell.innerText;



        let dr_id = props.reportsList[idx]['dr_id']
        var contentText = `Delete Opportunity id ${idx}?`

        props.SetDialogType('info-box');
        props.SetDialogProp({ title: 'Delete Opportunity', contentText: contentText, button1Text: 'Cancel', button2Text: 'OK', coverDivColor: 'rgb(222,222,222,0)', dr_id: dr_id })
        props.SetInfoBoxVisible(true)

        // clears the first footer row when del is clicked - this is a lazy bad way of doing it because if user
        // clicks delete but does not confirm, the footer row is cleared anyways.  they have to click it again
        // too much work to fix it for now but it needs to be fixed at some point.  8/22/2023
        SetSecurityData(
            {
                'value1': '',
                'value2': '',
                'value3': '',
                'bgcolor': 'transparent'
            }
        )
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    // this triggers when user clicks the link icon on the opportunities dashboard for a row
    // this is also shared for SetSHowTradeInstrumentReport - which is envoked only if the name of portfolio starts with '&'
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handlerLinkClicked = (index, event) => {
        // this handles opening the report  or trade_report dialog based on the permissions and name of the portfolio if it start with &
        // actual opening which dialog is doen in desktop mobileL and mobileP routines
        // if name of portfolio starts with & but user doesn't have permission for auto trading.  don't run this

        if (props.selectedPortfolio[0] === '&' && !userlist_auto.includes(props.loggedinUser)) {
            return;
        }

        let parentRow = event.target.closest("tr");
        let firstCell = parentRow.querySelector("td:first-child");
        let idx = firstCell.innerText;



        let id = props.reportsList[idx]['resourceID'];
        let symbol = props.reportsList[idx]['symbol'];
        let date = props.reportsList[idx]['date'];
        let days_hold = props.reportsList[idx]['days_hold'];
        let years = props.reportsList[idx]['years'];
        let direction = props.reportsList[idx]['direction'];
        let sharpe_ratio = props.reportsList[idx]['sharpe_ratio'];


        // this is a special portfolio for auto trading and icons are repurposed - it does not open a regular static report like other portfolios - this is a trade report isnteaed
        if (props.selectedPortfolio[0] === '&') {

            let tradeInfoDict = {}; // just a place holder, add all the info for the trade instrument report to this dictionary

            props.SetTradeInstrumentReportDict(tradeInfoDict);
            props.SetShowTradeInstrumentReport(true);
        }
        else {
            AddReportCreationJob(id, symbol, date, days_hold, years, direction, sharpe_ratio, 'new')
            // TW2: static reports live at /r/<slug>/ (TW1 served them at /<slug>)
            window.open('/r/' + props.reportsList[idx]['slug'] + '/', '_blank');
        }

    }

    //----------------------------------------------------------------------------------------
    const handlerCreateCalendarEvent = (index, event) => {


        // this handles opening create calendar event and trade dialog based on the permissions and name of the portfolio if it start with &
        // actual opening which dialog is doen in desktop mobileL and mobileP routines
        // if name of portfolio starts with & but user doesn't have permission for auto trading.  don't run this

        if (props.selectedPortfolio[0] === '&' && !userlist_auto.includes(props.loggedinUser)) {
            return;
        }



        let parentRow = event.target.closest("tr");
        let firstCell = parentRow.querySelector("td:first-child");
        let idx = firstCell.innerText;


        let rid = props.reportsList[idx]['resourceID']
        let dr_id = props.reportsList[idx]['dr_id']
        let resource_group = resourceObj[parseInt(rid)]
        let date1 = props.reportsList[idx]['date']
        let years = props.reportsList[idx]['years']
        let ticker = props.reportsList[idx]['symbol']
        let days = props.reportsList[idx]['days_hold']
        let date2 = incrementDate(date1, days - 1)

        let orders_list = [];
        if (props.reportsList[idx].hasOwnProperty('orders')) {
            let orders_string = props.reportsList[idx]['orders'];
            orders_list = orders_string.split(',');
            orders_list = orders_list.map(item => parseInt(item));
        }



        // var factor = 1.2; // 2 mean divide height and width by 2
        var gcDict = {
            'DialogW': parseInt(DialogW) / factor + "%",
            'DialogH': parseInt(DialogH) / factor + "%",
            'DialogT': (parseInt(DialogT) + (parseInt(DialogH) - (parseInt(DialogH) / factor)) / 2) + '%',
            'DialogL': (parseInt(DialogL) + (parseInt(DialogW) - (parseInt(DialogW) / factor)) / 2) + '%',
            'dr_id': dr_id,
            'rid': rid,
            'resource_group': resource_group,
            'date1': date1,
            'date2': date2,
            'years': years,
            'ticker': ticker,
            'days': days,
            'direction': props.reportsList[idx]['direction'],
            'slug': props.reportsList[idx]['slug'],
            'order_id_list': orders_list
        }

        // console.log('gcDict=', gcDict)
        props.SetGoogleCalendarDict(gcDict);
        props.SetAddGCVisible(true);
        props.SetShowPortfolioSettings(false); // just making sure this dialog is hidden if user clicks on add google event icon
    };
    //-------------------------------------------------------------------------------------------------------------------
    // status clciked for one of the opportunities
    //-------------------------------------------------------------------------------------------------------------------
    const handlerStatusClicked = (index, event, value, statusColor) => {

        // console.log('handler status event trigered')
        // console.log('current value =', value)

        let len = Object.keys(statusColor).length; // this is the max number of status colors available 
        let new_status_value = parseInt(value) + 1;


        if (new_status_value >= len) { // back to 0
            new_status_value = 0;
        }


        // now update by calling the appserver
        // get the index for this opp first
        let parentRow = event.target.closest("tr");
        let firstCell = parentRow.querySelector("td:first-child");
        let idx = firstCell.innerText;

        let id = -1;
        for (let i = 0; i < props.portfolios.length; i++) {
            if (props.selectedPortfolio === props.portfolios[i]['value']) {
                id = props.portfolios[i]['id'];
                break;
            }
        }

        // get the slug for this opportunity since we need it to update the status on server
        // let slug = props.reportsList[idx]['slug']
        let dr_id = props.reportsList[idx]['dr_id']


        // call the api to update the status for the opportunity
        let asURL = appserverURL()
        let url = `${asURL}/update_status/${new_status_value}/${id}/${dr_id}?token=${token}`

        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                // console.log('update status returned ', data)
                // console.log('current reports list=', props.reportsList)
                // modify status value in reports list without reloading it
                // find the record first
                let idx = props.reportsList.findIndex(obj => obj['dr_id'] === dr_id);
                // console.log('result=', props.reportsList[idx]);

                // Create a new array with the modified object
                let updatedReportsList = [...props.reportsList]; // make a copy first
                // updatedReportsList[idx] = { ...updatedReportsList[idx], status: new_status_value };
                updatedReportsList[idx]['status'] = new_status_value.toString();

                // Update the state with the new array
                props.SetReportsList(updatedReportsList);



            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });


    }
    //-------------------------------------------------------------------------------------------------------------------
    // runs when share number is changed and cursor is clicked away
    //----------------------------------------------------------------------------------------
    const handleBlur = (textbox_name, old_value, event, price1) => {

        let new_value = event.target.value
        if (new_value.charAt(0) === '$') { // getting rid of $ if its in the textbox
            new_value = new_value.substring(1);
        }

        if (old_value === parseInt(new_value)) return; // number didn't change




        let parentRow = event.target.closest("tr");
        let firstCell = parentRow.querySelector("td:first-child");
        let idx = firstCell.innerText;

        // let slug = props.reportsList[idx]['slug']



        // calculate the new number of shares
        let num_shares = 0;

        if (textbox_name === 'shares') {
            num_shares = parseInt(new_value);
        }
        else if (textbox_name === 'total_price') {
            // calculate the new number of shares

            let price1 = props.reportsList[idx]['price1']
            num_shares = parseInt(new_value / price1);

            if (new_value > 0 && num_shares === 0) num_shares = 1;

            // console.log('shares from total price change ', num_shares)
        }



        // if (textbox_name === 'total_price') return;

        // console.log('portfolios=',props.portfolios)
        // console.log('selected one ',props.selectedPortfolio)

        // find portfolio id from selectedPortfolio since its only the name
        let id = -1;
        for (let i = 0; i < props.portfolios.length; i++) {
            if (props.selectedPortfolio === props.portfolios[i]['value']) {
                id = props.portfolios[i]['id'];
                break;
            }
        }

        // console.log('selected portfolio id=',id)



        // let slug = props.reportsList[idx]['slug']
        let dr_id = props.reportsList[idx]['dr_id']


        // call the api to update the shares for the opportunity
        let asURL = appserverURL()
        let url = `${asURL}/update_number_of_shares/${num_shares}/${id}/${dr_id}?token=${token}`

        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                // console.log('update num_shares returned ', data)

                // if $ value or number of shares changes, update the display on the 1st footer row 8/22/2023
                let tmp = securityData;
                tmp['value2'] = num_shares.toString(); // update only number of shares for display on the first footer row
                SetSecurityData(tmp);
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });


        props.SetReportsList([]) // force refresh

    }
    //----------------------------------------------------------------------------------------

    const mainCoverDiv = { // transparent Div covers the entire screen then the popup is displayed over it.  this is so that if user clicks ouside of the dialog box we can capture it and turn off the dialog
        position: main_cover_css_position,
        backgroundColor: tc.dialogOverlay,
        zIndex: 5000,
        fontFamily: 'sans-serif',
        width: '100%',
        height: '100%',
        left: '0%',
        top: '0%',
    }
    //----------------------------------------------------------------------------------------
    // protfolio changed event handler
    //----------------------------------------------------------------------------------------
    const portfolioChanged = (event) => {

        // let id = event.target.id;
        let value = event.target.value;


        props.SetSelectedPortfolio(value) // this is the portfolio name - also need to set portfolioID

        let id = -1;

        for (let i = 0; i < props.portfolios.length; i++) {
            if (props.portfolios[i]['value'] === value) {
                id = props.portfolios[i]['id']
                break;
            }
        }

        // save portfolio id and name in a cookie for next time its loaded
        setCookie('selected_portfolio', `${id},${value}`, 300);
        setCookie('selected_portfolio_uid', loggedinUser, 300);


        props.SetSelectedPortfolioID(id)
        setShowDiv('none')


        props.SetReportsList([])


        // blank out the securities values

        SetSecurityData(
            {
                'value1': '',
                'value2': '',
                'value3': '',
                'bgcolor': 'transparent'
            }
        )

        // reset and remove the selected row
        SetRowIndexDRclicked(null);
        SetClickedRowIndex(-1);

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const HandleNotesClicked = () => {
        // console.log('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',rowIndexDRclicked)
        if (rowIndexDRclicked !== null && props.showOppNote === false && props.showPortfolioSettings === false) {
            props.SetShowOppNote(true)
        }
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const PublishArticle = () => {
        if (rowIndexDRclicked !== null && props.showOppNote === false && props.showPortfolioSettings === false) {
            props.SetShowArticlePublish(true)
        }
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const downloadPortfolioCSV = () => {

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // handles automatic queuing of all articles in the selectedPortfolio that do not have an article
    //-------------------------------------------------------------------------------------------------------------------------------------
    const AutomateArticleInFolder = () => {
        const asURL = appserverURL();
        const portfolioId = props.selectedPortfolioID;
        const articleDate = publishDate;           // YYYY-MM-DD from state

        if (!portfolioId || !articleDate) {
            console.error("AutomateArticleInFolder: missing portfolioId or publishDate");
            return;
        }

        const url = `${asURL}/article_folder_workflow/${portfolioId}/${articleDate}?token=${token}`;


        fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((resp) => {
                if (!resp.ok) {
                    throw new Error(`HTTP ${resp.status}`);
                }
                return resp.json();
            })
            .then((data) => {
                console.log("article_folder_workflow result:", data);

                // trigger reload of portfolio rows so icons update
                if (props.SetReportsList) {
                    props.SetReportsList([]);
                }

                // if you have any status/message UI here, set it:
                // SetMsgColor(data.status === "ok" ? "darkgreen" : "darkorange");
                // SetMessage(`Queued ${data.queued} opportunities for ${articleDate}`);
            })
            .catch((err) => {
                console.error("article_folder_workflow error:", err);
                // optional: SetMsgColor("red"); SetMessage(`Error: ${err.message}`);
            });
    };



    const savedCount = props.numReportsCreated;
    const allowedCount = props.numReportsAllowed;
    const quotaText = `${savedCount}/${allowedCount}`;

    // mobile always uses compact quota
    const showQuotaCompact = rdd.isMobile;

    // width for the compact quota in multiPortfolios mode (uses the "saved" + "remaining" column widths)
    // const quotaWidth = `${parseFloat(controlWidth[1]) + parseFloat(controlWidth[2])}%`;
    const quotaWidth = `${(parseFloat(controlWidth[1]) + parseFloat(controlWidth[2]))}%`;



    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div className='main-cover-opp-manager' style={mainCoverDiv} onClick={() => { props.SetReportsDashVisible(false); props.SetAddGCVisible(false); props.SetShowPortfolioSettings(false); props.SetShowOppNote(false); props.SetShowPopulatePortfolio(false); props.SetShowAutoTrade(false); props.SetShowArticlePublish(false); }}  >

            <div className='dialog-popup-reports-dashboard' style={popupDialogStyle} onClick={(e) => { e.stopPropagation(); }} >

                <div style={titleDiv}>

                    <div style={{ height: '100%', width: (parseFloat(title_close_width.replace('%', '')) * 2) + '%', display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
                        <span style={{ color: tc.textOnControl }}>
                            {props.reportsList.length}
                        </span>
                    </div>


                    <div style={{ height: '100%', width: title_width, display: 'flex', justifyContent: 'center', alignItems: 'center', backgroundColor: 'transparent', cursor: rdd.isMobile ? 'default' : 'move' }} onMouseDown={handleTitleMouseDown}>
                        <span>Portfolio&nbsp;&nbsp;&nbsp;Manager</span>
                    </div>

                    <div style={{ height: '100%', width: title_close_width }}></div>
                    <div style={{ height: '100%', width: title_close_width, display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: tc.closeBtnBg }} onClick={() => { props.SetShowPortfolioSettings(false); props.SetReportsDashVisible(false) }} >
                        <GrClose size={grclose_iconsize} />
                    </div>
                </div>


                {!props.multiPortfolios
                    ?
                    <div style={controlsDiv}>

                        {showQuotaCompact ? (

                            <div
                                className='reports-header-info'
                                style={{
                                    width: '100%',
                                    backgroundColor: 'transparent',
                                    justifyContent: 'center',
                                    fontSize: savedFontSize
                                }}
                            >
                                {quotaText}
                            </div>

                        ) : (

                            <>
                                {rdd.isMobile ? (
                                    <div
                                        className='reports-header-info'
                                        style={{
                                            width: '100%',
                                            backgroundColor: 'transparent',
                                            justifyContent: 'center',
                                            fontSize: savedFontSize
                                        }}
                                    >
                                        {quotaText}
                                    </div>
                                ) : (
                                    <>
                                        {/* KEEP your existing Saved/Remaining divs exactly as-is here */}
                                    </>
                                )}
                            </>

                        )}

                    </div>

                    :
                    <div style={controlsDiv}>

                        <div className='reports-header-info' style={{ display: 'flex', width: controlWidth[0], backgroundColor: 'transparent', justifyContent: 'left' }}>
                            {!rdd.isMobile &&
                                <span>portfolio&nbsp;</span>
                            }

                            <SelectBox tooltipContent={props.tooltipSW ? 'b,Select Portfolio - When Opportunities are added, they are saved in the selected portfolio.  To save an opportunity to a new portfolio.  you need to select the portfolio first with this pulldown before adding the opportunity.' : ''} optionList={props.portfolios} name="portfolios" value={props.selectedPortfolio} sbChanged={portfolioChanged} />

                            <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                <div theme="tw" >
                                    {props.tooltipSW ? 'With Portfolio Settings you can add new portfolios, edit portfolio names and delete portfolios.' : ''}
                                </div>
                            }>
                                <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'center' }} onClick={(e) => { if (props.showOppNote === false) { const dlg = e.currentTarget.closest('.dialog-popup-reports-dashboard'); if (dlg) props.SetReportsDashRect(dlg.getBoundingClientRect()); props.SetShowPortfolioSettings(true); } }}  >
                                    <SlSettings size={portMoveSize} style={{ fill: tc.text, backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                                </div>
                            </Tippy>

                            <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                <div theme="tw" >
                                    {rowIndexDRclicked === null ? 'Select an opportunity to view & edit its note' : ''}
                                </div>
                            }>

                                <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'center' }} onClick={() => { HandleNotesClicked() }}  >
                                    <BsPencil size={portMoveSize} style={{ fill: "#FF8C00.", backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                                </div>
                            </Tippy>

                            {/* Article Management Icon  */}



                            {/* Article Management Icons */}
                            {userlist_article.includes(props.loggedinUser) && (
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw" >
                                        {rowIndexDRclicked === null ? 'Newsroom Interface Toggle' : ''}
                                    </div>
                                }>
                                    <div
                                        style={{
                                            backgroundColor: 'transparent',
                                            display: 'flex',
                                            verticalAlign: 'center',
                                            width: port_icon_div_width,
                                            justifyContent: 'center',
                                        }}
                                    >
                                        {newsToggle ? (
                                            <RiArticleFill
                                                size={articleIconSize}
                                                style={{ fill: props.UITheme === 'dark' ? 'cyan' : '#2563EB', backgroundColor: "transparent", verticalAlign: "bottom" }}
                                                onClick={() => { SetNewsToggle(false); localStorage.setItem('newsToggle', '0'); }}
                                            />
                                        ) : (
                                            <RiArticleLine
                                                size={articleIconSize}
                                                style={{ fill: tc.text, backgroundColor: "transparent", verticalAlign: "bottom" }}
                                                onClick={() => { SetNewsToggle(true); localStorage.setItem('newsToggle', '1'); }}
                                            />
                                        )}
                                    </div>
                                </Tippy>
                            )}

                            {newsToggle && (
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw" >
                                        <span>Set publish date and send all to article queue</span>
                                    </div>
                                }>
                                    <div style={{ display: 'flex' }}>
                                        <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'center' }}>
                                            <GiAutomaticSas size={articleIconSize} style={{ fill: props.UITheme === 'dark' ? 'cyan' : '#2563EB', backgroundColor: "transparent", verticalAlign: "bottom" }} onClick={() => AutomateArticleInFolder()} />
                                        </div>
                                        <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', justifyContent: 'center' }}>
                                            <input type="date" id="publish_date_input" lang="en-CA" value={publishDate} onChange={(e) => setPublishDate(e.target.value)} style={{ backgroundColor: tc.panelBg, color: tc.text, border: '1px solid ' + tc.border, borderRadius: '4px', padding: '2px 4px', colorScheme: props.UITheme === 'dark' ? 'dark' : 'light' }} />
                                        </div>
                                    </div>
                                </Tippy>
                            )}





                            <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'center' }} onClick={() => { if (props.showPopulatePortfolio === false) { props.SetShowPopulatePortfolio(true); props.SetShowPortfolioSettings(false) } }}  >
                                {userlist_amp.includes(props.loggedinUser) && props.selectedPortfolio[0] === '&' &&
                                    // {(props.loggedinUser === '1' || props.loggedinUser === '22' || props.loggedinUser === '16') &&
                                    <IoMdDownload size={listIconSize} style={{ fill: tc.text, backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                                }
                            </div>

                            <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'center' }} onClick={() => { if (props.showAutoTrade === false) props.SetShowAutoTrade(true) }}  >
                                {(userlist_auto.includes(props.loggedinUser) && props.selectedPortfolio[0] === '&') &&
                                    <MdRocket size={listIconSize} style={{ fill: tc.text, backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                                }
                            </div>

                            <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'center' }} onClick={() => { if (props.showTradeReport === false) props.SetShowTradeReport(true) }}  >
                                {(userlist_auto.includes(props.loggedinUser) && props.selectedPortfolio[0] === '&') &&
                                    <LiaClipboardListSolid size={listIconSize} style={{ fill: tc.text, backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                                }
                            </div>



                            {/* <div style={{ backgroundColor: 'transparent', display: 'flex', verticalAlign: 'center', width: port_icon_div_width, justifyContent: 'left' }}><BsFolderSymlink size={portMoveSize} style={{ fill: "black", backgroundColor: "transparent", verticalAlign: 'bottom' }} /></div> */}

                        </div>

                        {rdd.isMobile ? (
                            <div
                                className='reports-header-info'
                                style={{
                                    width: quotaWidth,

                                    // marginLeft: 'auto',     // <-- this is the key
                                    // marginRight: '2spx',     // optional

                                    backgroundColor: 'transparent',
                                    justifyContent: 'right',
                                    fontSize: savedFontSize
                                }}
                            >
                                {quotaText}
                            </div>
                        ) : (
                            <>
                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw" >
                                        {props.tooltipSW ? 'Number of Opportunities saved for tracking' : ''}
                                    </div>
                                }>
                                    <div className='reports-header-info' style={{ width: controlWidth[1], backgroundColor: 'transparent', justifyContent: 'center', fontSize: savedFontSize }}>
                                        {opp_saved_text} {props.numReportsCreated}
                                    </div>
                                </Tippy>

                                <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                    <div theme="tw" >
                                        {props.tooltipSW ? 'Total number of opportunities left that you can add for tracking based on your subscription level' : ''}
                                    </div>
                                }>
                                    <div className='reports-header-info' style={{ width: controlWidth[2], backgroundColor: 'transparent', justifyContent: 'center', fontSize: savedFontSize }}>
                                        {opp_remaining_text} {props.numReportsAllowed - props.numReportsCreated}
                                    </div>
                                </Tippy>
                            </>
                        )}
                    </div>
                }


                <div className={props.UITheme === 'dark' ? 'opp-table-dark' : ''} style={contentDiv}>

                    <TableBoxReports
                        table_data={props.reportsList}
                        getCurValue={getCurValue}
                        handlerRowClicked={handlerRowClicked}
                        handlerKeyDown={handlerKeyDown}

                        rowIndexDRclicked={rowIndexDRclicked}
                        SetRowIndexDRclicked={SetRowIndexDRclicked}
                        clickedRowIndex={clickedRowIndex}

                        filterText=""
                        tooltipSW={props.tooltipSW}
                        SetOppTableLength={SetPortfolioTableLength}
                        handlerLoadClicked={handlerLoadClicked}
                        handlerDelClicked={handlerDelClicked}
                        handlerLinkClicked={handlerLinkClicked}
                        handlerCreateCalendarEvent={handlerCreateCalendarEvent}
                        securityTypeList2={props.securityTypeList2}
                        handleBlur={handleBlur}
                        selectedPortfolioID={props.selectedPortfolioID}
                        showDiv={showDiv}
                        setShowDiv={setShowDiv}
                        handlerStatusClicked={handlerStatusClicked}
                        icon_status_size={icon_status_size}
                        selectedPortfolioName={props.selectedPortfolio}
                        newsToggle={newsToggle}
                        PublishArticle={PublishArticle}

                    />
                </div>


                <div style={{ height: opp_info_footer_height, width: '100%', backgroundColor: tc.footerBg, borderTop: '1px solid ' + tc.border, display: 'flex', fontSize: statsFontSize, fontFamily: statsFontFamily, fontWeight: 'bold' }}>
                    <div className='portfolio-div-left' style={{ backgroundColor: tc.footerRow1Label, color: tc.text }}>{sdata1title}</div>
                    <div className='portfolio-div-right' style={{ backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, color: tc.text }}>{securityData['value1']}</div>
                    <div className='portfolio-div-left' style={{ backgroundColor: tc.footerRow1Label, color: tc.text }}>{sdata2title}</div>
                    <div className='portfolio-div-right' style={{ backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, color: tc.text }}>{securityData['value2']}</div>
                    <div className='portfolio-div-left' style={{ backgroundColor: tc.footerRow1Label, color: tc.text }}>{sdata3title}</div>
                    <div className='portfolio-div-right' style={{ backgroundColor: securityData['bgcolor'], color: tc.text }}>{securityData['value3']}</div>
                </div>


                <div style={{ height: stats_height, width: '100%', backgroundColor: tc.panelBg, borderTop: '1px solid ' + tc.border, display: 'flex', fontSize: statsFontSize, fontFamily: statsFontFamily, fontWeight: 'bold' }}>


                    <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                        <div theme="tw" >
                            {props.tooltipSW ? 'Click to view results for a specific Filter Flag. White is Off' : ''}
                        </div>
                    }>

                        <div className='portfolio-div-left' style={{ backgroundColor: tc.footerRow2Label, color: tc.text }} onClick={() => handlerTotalInvestedIcon()}>
                            {totalInvestedStatus === 0
                                ? <BiSquare size={icon_status_size} style={{ fill: tc.textSecondary, verticalAlign: "middle", marginRight: '2px' }} />
                                : <BiSolidSquare size={icon_status_size} style={{ fill: statusColor[totalInvestedStatus], verticalAlign: "middle", marginRight: '2px' }} />
                            }
                            <span style={{ marginTop: '2px' }}>{data1title}</span>
                        </div>

                    </Tippy>

                    <div className='portfolio-div-right' style={{ backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, color: tc.text }}>${oppValuesTotal['total_invested']}</div>

                    <div className='portfolio-div-left' style={{ backgroundColor: tc.footerRow2Label, color: tc.text }}>{data2title}</div>
                    <div className='portfolio-div-right' style={{ backgroundColor: 'transparent', borderRight: '1px solid ' + tc.border, color: tc.text }}>${oppValuesTotal['total_current_value']}</div>

                    <div className='portfolio-div-left' style={{ backgroundColor: tc.footerRow2Label, color: tc.text }}>{data3title}</div>
                    <div className='portfolio-div-right' style={{ backgroundColor: oppValuesTotal['total_pct_profit_loss'] > 0 ? tc.profitRowBg : oppValuesTotal['total_pct_profit_loss'] < 0 ? tc.lossRowBg : 'transparent', color: tc.text }}>{oppValuesTotal['total_pct_profit_loss']}%</div>

                </div>

            </div>
        </div>
    )

}
export default ReportsDashboard
