
// this is a special dialog that build portfolios based on the opptable entries
// its only available to me or whoever I give access to - for now just me
// the purpose is to implement auto trading


import React, { useContext, useEffect, useMemo, useState } from 'react'
import { UserContext } from './UserContext'
import { appserverURL } from './Common'
import './styles/InfoPopup.css'
import './styles/Portfolios.css'
import { GrClose } from "react-icons/gr";
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import { BsPlus, BsFolderSymlink, BsTrash3, BsThermometerLow, BsFileEarmarkPerson } from "react-icons/bs"
import { GrEdit } from "react-icons/gr";
import { monthsOptionsList, monthsOptionsListS, getTodayDate } from './Common'
import { getSelectedIDFromSecuritiesList2 } from './Common'
import { securities_groups_default_years } from './Common'
import { getCookie, setCookie } from './Common'
import { BiSolidSquare, BiSquare } from "react-icons/bi"
import { statusColor } from './Common'
import { CSVLink, CSVDownload } from "react-csv";

const PortfolioTradeReport = (props) => {

    const maxCharacters = 1000; // maximum number of characters allowed in a note

    const { numReportsAllowed, browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)

    const [text, setText] = useState("");
    const [dashboardDialog_TLHW, SetDashboardDialog_TLHW] = useState(''); // this the main portfolio dialog TOp Left Height Width - coordinates are used to place a transparent div over the dashboard before rendering notes dilaog - this to enable clciking outside of the dialog and then closing the dialog.

    // I'm duplicating therse 2 - its also in oppTable - this is because I didn't put them in App.js now I can't access it from here and I'm not going to change it now so duplication
    const [seasonalYearsOptionsList, SetSeasonalYearsOptionsList] = useState([])
    const [partialSeasonalYearsOptionsList, SetPartialSeasonalYearsOptionsList] = useState([])

    const [selectedSecurityGroup, SetSelectedSecurityGroup] = useState(props.selectedSecurity);
    const [populateMonth, SetPopulateMonth] = useState(props.oppTableMonth);
    const [populateDay, SetPopulateDay] = useState(props.dayOfTheMonth);
    const [populateYears, SetPopulateYears] = useState(props.oppTableYears);
    const [populatePartialYears, SetPopulatePartialYears] = useState(props.oppTablePartialYears);

    const [minSR, SetMinSR] = useState('1.0');
    const [avgRet, SetAvgRet] = useState('3.0%');
    const [minMFE, SetMinMFE] = useState('0');
    const minMFEpct = [ // this defines the % of bars that need the min MFE - its very computation intensive because every stock has to query all years to check
        { id: 1, value: "1.0", label: "100%" },
        { id: 2, value: "0.9", label: "90%" },
        { id: 3, value: "0.8", label: "80%" },
        { id: 4, value: "0.7", label: "70%" },
        { id: 5, value: "0.6", label: "60%" },
    ];

    const [selectedMinMFEpct, SetSelectedMinMFEpct] = useState("1");

    const [dayRange, SetDayRange] = useState('9-39');

    // dictionary didn't work because it didn't rerender - broke down to individual state variables and now it works
    // const [textBoxError, SetTextBoxError] = useState({ 'min_SR': false, 'min_avg_return': false, 'min_MFE': false, 'day_range': false });

    const [textBoxError1, SetTextBoxError1] = useState(false);
    const [textBoxError2, SetTextBoxError2] = useState(false);
    const [textBoxError3, SetTextBoxError3] = useState(false);
    const [textBoxError4, SetTextBoxError4] = useState(false);
    const [textBoxError5, SetTextBoxError5] = useState(false);

    const [selectedMinMFE, SetSelectedMinMFE] = useState('0');

    const [loadedOpps, SetLoadedOpps] = useState([]);
    const [oppCount, SetOppCount] = useState(0);

    const [displayWorking, SetDisplayWorking] = useState('none'); // this is showing the working status of the query

    const minMFEfilters = () => {
        const filters = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '15', '20', '25', '35', '50'];
        let tmp = [];
        for (let i = 0; i < filters.length; i++) {
            tmp.push({ id: i + 1, value: filters[i], label: filters[i] });
        }

        return tmp;
    }


    // const tradeTypes = [
    //     { id: 1, value: 'manual', label: 'Manual Trade' },
    //     { id: 2, value: 'auto', label: 'Automatic Trade' }
    // ]

    // const [tradeType, SetTradeType] = useState('manual');


    const [minStockPrice, SetMinStockPrice] = useState('$20');

    const [initialStatus, SetInitialStatus] = useState(0);

    var DialogH = '30%';
    var DialogW = '30%';
    var DialogT = '35%';
    var DialogL = '35%';
    var grclose_iconsize = 17;
    var icon_sizeP = 15;
    var icon_sizeE = 12;
    var icon_sizeD = 12;
    var title_text_size = '1vw';
    var button_height = '2.5vh'
    var textboxWidth = 24;
    var text_font_size = '1em';
    var titleCloseDivWidth = '6%';
    var titleCenterDivWidth = '88%';

    var cancel_width = '40%';
    var protfolio_csv_width = '60%';
    var query_width = '12em';
    var charIndicatorFontSize = '0.7vw'; // this is indicator showing number of chars typed

    var buttonTextFont = '0.8vw';
    var textbox_width = '9';
    var icon_trash_size = 15;
    var redStarSize = '1.5vw';
    var icon_status_size = 17;


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
        textbox_width = '6';
        cancel_width = '33%';
        protfolio_csv_width = '50%'
        charIndicatorFontSize = '3vw';
        buttonTextFont = '3.5vw';

        text_font_size = '4em';
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
        protfolio_csv_width = '28%'
        charIndicatorFontSize = '1.8vw';
        buttonTextFont = '2vw';
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
        buttonTextFont = '2.2vw';
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
        buttonTextFont = '1.3vw';
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
        buttonTextFont = '2vw';
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
        buttonTextFont = '1.3vw';
    }


    //------------------------------------------------------------------------------------------------------------
    const DashboardCover = {

        // height: dashboardDialog_TLHW['height'],
        // width: dashboardDialog_TLHW['width'],
        // top: dashboardDialog_TLHW['top'],
        // left: dashboardDialog_TLHW['left'],

        height: '100%',
        width: '100%',
        top: '0',
        left: '0',


        backgroundColor: 'transparent',
        display: 'flex',
        position: 'absolute',
        zIndex: 9999
    }
    //------------------------------------------------------------------------------------------------------------
    const popupDialogStyle = {
        fontFamily: 'sans-serif',
        fontSize: '0.8vw',
        fontWeight: 'bold',
        position: 'absolute',
        backgroundColor: "whitesmoke",
        height: DialogH,
        width: DialogW,
        top: DialogT,
        left: DialogL,
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid black',
        alignItems: 'center',
        zIndex: 7800,
        userSelect: 'none'
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
    useEffect(() => { // get default cookie
        var qvars = getCookie('populate_portfolio_qvars');

        if (qvars !== null) {

            console.log('getCookie', qvars)

            let b64_str = window.atob(qvars);

            console.log('getCookie', b64_str)

            let params = b64_str.split('|');
            //                            0        1         2      3         4         5         6          7            8                9               10          11 
            // let qvars = window.btoa(`${id}|${monthNum}|${day}|${years}|${pyears}|${min_sr}|${avg_ret}|${min_mfe}|${day_range}|${selectedMinMFEpct}|${tradeType}|${minPrice}`);

            console.log('getCookie', 'params=', params)

            // SetSelectedSecurityGroup
            // SetPopulateMonth
            // SetPopulateDay
            // SetPopulateYears
            // SetPopulatePartialYears
            // SetTradeType
            if (params[5] !== 'undefined') SetMinSR(params[5]);
            if (params[6] !== 'undefined') SetAvgRet(params[6] + '%');
            if (params[7] !== 'undefined') SetSelectedMinMFE(params[7]);
            if (params[8] !== 'undefined') SetDayRange(params[8]);
            if (params[9] !== 'undefined') SetSelectedMinMFEpct(params[9]);
            if (params[11] !== 'undefined') SetMinStockPrice('$' + params[11]);
        }

    }, []);
    //-------------------------------------------------------------------------------------------------------------------------------------

    function getMonth(monthName) {
        const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
        const monthIndex = months.findIndex(month => month.toLowerCase() === monthName.toLowerCase());
        if (monthIndex !== -1) return monthIndex + 1;
        else return -1;
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        var id = getSelectedIDFromSecuritiesList2(props.securityTypeList, selectedSecurityGroup)

        let base_y = getTodayDate().substring(0, 4);
        let month = getMonth(populateMonth);
        let day = populateDay
        let asURL = appserverURL();
        var url = `${asURL}/YearsMetaData2/${id}/${base_y}/${month}/${day}?token=${token}`

        SetSeasonalYearsOptionsList([])
        SetPartialSeasonalYearsOptionsList([])



        fetch(url) //meta 
            .then(res => {
                const contentType = res.headers.get("content-type");
                if (contentType && contentType.indexOf("application/json") !== -1) {
                    return res.json();
                }
                else {
                    console.log('response status = ', res.status)
                }
            })
            .then((oppYearsLists) => {
                if (oppYearsLists !== undefined) {

                    var years = oppYearsLists['YearsMetaData'].map((item) => {
                        return parseInt(item[0])
                    })

                    years = [...new Set(years)] // unique set of years available
                    years.sort((a, b) => { return (a - b) }) //sort
                    var tmp = []
                    for (let i = 0; i < years.length; i++) {
                        tmp.push({ id: years[i], value: years[i].toString(), label: years[i].toString() })
                    }

                    SetSeasonalYearsOptionsList(tmp)


                    let tmp2 = [];
                    for (let i = 0; i < oppYearsLists['YearsMetaData'].length; i++) {

                        if (oppYearsLists['YearsMetaData'][i][0] === populateYears) {
                            tmp2.push({ key: i, id: oppYearsLists['YearsMetaData'][i][1], value: oppYearsLists['YearsMetaData'][i][1], label: oppYearsLists['YearsMetaData'][i][1] });
                        }
                    }
                    tmp2 = tmp2.sort()
                    SetPartialSeasonalYearsOptionsList(tmp2)

                }

            })
            .catch(err => {
                console.log('catch login error=', err.message)
            })

    }, [selectedSecurityGroup, populateMonth, populateDay, populateYears, populatePartialYears])

    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleTextChange = (event) => {
        setText(event.target.value);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleBlur = (event) => {

        let tmp = event.target.value.replace('%', '').replace('$', '');

        switch (event.target.id) {
            case 'min_SR':
                if (!isNaN(Number(tmp))) {
                    SetTextBoxError1(false);
                    SetMinSR(Number(tmp).toFixed(1));
                } else {
                    SetTextBoxError1(true);
                }
                break;
            case 'min_avg_return':
                if (!isNaN(Number(tmp))) {
                    SetTextBoxError2(false);
                    SetAvgRet(Number(tmp).toFixed(1) + '%');
                } else {
                    SetTextBoxError2(true);
                }
                break;
            // case 'min_MFE':
            //     if (!isNaN(Number(tmp))) {
            //         SetTextBoxError3(false);
            //         console.log('tmp=',tmp)
            //         SetMinMFE(tmp);
            //     } else {
            //         SetTextBoxError3(true);
            //     }
            //     break;
            case 'day_range':
                let isErr = false;
                let sp;
                if (tmp.includes('-')) {
                    sp = tmp.split('-');
                    if (isNaN(Number(sp[0]))) isErr = true;
                    if (isNaN(Number(sp[1]))) isErr = true;
                }
                else isErr = true;

                if (Number(sp[0]) >= Number(sp[1])) isErr = true;

                SetTextBoxError4(isErr);
                SetDayRange(tmp);
                break;
            case 'min_stock_price':
                if (!isNaN(Number(tmp))) {
                    SetTextBoxError5(false);
                    SetMinStockPrice('$' + Number(tmp).toFixed(0).toString());
                } else {
                    SetTextBoxError5(true);
                }
                break;
            default:
                break;




        }


    }








    //-------------------------------------------------------------------------------------------------------------------------------------
    const selectboxChanged = (event) => {


        console.log('event.target.id=', event.target.id, event.target.value)

        switch (event.target.id) {

            case 'securityTypeListP':
                SetSelectedSecurityGroup(event.target.value)
                SetPopulateYears(securities_groups_default_years[event.target.value][0].toString()); // default show 10 years
                break;
            case 'monthsP':
                SetPopulateMonth(event.target.value);
                break;
            case 'dayP':
                SetPopulateDay(event.target.value);
                break;
            case 'yearsP':
                SetPopulateYears(event.target.value);
                break;
            case 'partialYearsP':
                SetPopulatePartialYears(event.target.value);
                break;
            case 'minMFEfilters':
                SetSelectedMinMFE(event.target.value);
                break;
            case 'minMFEpct':
                SetSelectedMinMFEpct(event.target.value);
                break;
            default:
                console.log('selectbox encoutered an unknown name!!!!!!!!  should not be happening', event.target.value);
                break;
        }

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const portfolioActions = (action) => {




        let market = selectedSecurityGroup;
        let month = populateMonth;
        let day = populateDay;
        let years = populateYears;
        let pyears = populatePartialYears;
        let min_sr = minSR;
        let avg_ret = avgRet.replace('%', '');
        let min_mfe = selectedMinMFE.replace('%', '');
        let day_range = dayRange;
        let minPrice = minStockPrice.replace('$', '')

        let min_mfe_pct = selectedMinMFEpct.replace('%', '')

        SetDisplayWorking('block');

        // console.log('min_mfe=', min_mfe)
        // console.log('Market:', market);
        // console.log('Month:', month);
        // console.log('Day:', day);
        // console.log('Years:', years);
        // console.log('Partial Years:', pyears);
        // console.log('Min SR:', min_sr);
        // console.log('Avg Ret:', avg_ret);
        // console.log('Min MFE:', selectedMinMFE);
        // console.log('Day Range:', day_range);

        // console.log('min MFE pct:', selectedMinMFEpct)
        // console.log('initial status:', initialStatus)
        // console.log('min stock price:', minStockPrice)


        var id = getSelectedIDFromSecuritiesList2(props.securityTypeList, selectedSecurityGroup);
        let foundMonth = monthsOptionsList.find(obj => obj.value === month)
        let monthNum = foundMonth['id'] - 1;

        // create a base64 string that holds all the variables - this seems easier than passing it all seperately to flask
        let qvars = window.btoa(`${id}|${monthNum}|${day}|${years}|${pyears}|${min_sr}|${avg_ret}|${min_mfe}|${day_range}|${min_mfe_pct}|${initialStatus}|${minPrice}`);

        console.log('set cookie qvars=', qvars)

        let asURL = appserverURL();
        var url = `${asURL}/populate_portfolio/${qvars}/${props.selectedPortfolio}/${action}`; // action is either count or populate
        url += '?token=' + token;

        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                console.log('populate_portfolio returned ', data)
                SetDisplayWorking('none');
                SetOppCount(data['count'])

                if (action === 'add' || action === 'remove') {

                    props.SetShowPopulatePortfolio(false);
                    props.SetReportsList([]);

                    if (action === 'add') props.SetNumReportsCreated(props.numReportsCreated + data['count']);
                    if (action === 'remove') props.SetNumReportsCreated(props.numReportsCreated - data['count']);

                }

            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                } else {
                    console.log('Error:', error.message); // handle any other error response
                }
            });


        // also save the defaults in a cookie for next time this dialog is added
        setCookie('populate_portfolio_qvars', qvars, 30);

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleStatusClicked = (event) => {

        let tmp = initialStatus;

        tmp++;

        if (tmp >= Object.keys(statusColor).length) tmp = 0;
        SetInitialStatus(tmp);

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const downloadPortfolioCSV = () => {
        // downloads a csv with the content of props.reportsList
        // 

        // <CSVLink data={csvData} filename={props.symbol + " TradeWave Opportunity csv report" + mqx + ".csv"}  >
        //     <BsTable size={16} style={{ fill: "white" }} />
        // </CSVLink>
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div style={DashboardCover} onClick={() => { props.SetShowTradeReport(false); }}>

            <div style={popupDialogStyle} onClick={(e) => { e.stopPropagation(); }}>

                <div style={{ width: '100%', height: '12%', backgroundColor: 'gray', display: 'flex' }}>
                    <div style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'transparent' }}></div>
                    <div className='div_basic' style={{ height: '100%', width: titleCenterDivWidth, backgroundColor: 'transparent' }}><span style={{ fontSize: title_text_size, color: 'whitesmoke' }}>Portfolio Trade Report</span></div>
                    <div className='div_basic' onClick={() => { props.SetShowTradeReport(false); }} style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'lightgray' }}><GrClose size={grclose_iconsize} /></div>
                </div>

                <div className='div_basic' style={{ width: '100%', height: '88%', backgroundColor: 'transparent', flexDirection: 'column' }}>

                    <div className='div_basic' style={{ width: '100%', height: '85%', backgroundColor: 'transparent' }}>

                    </div>

                    <div className='div_basic' style={{ width: '100%', height: '15%', backgroundColor: 'transparent', borderTop: '1px solid lightgray' }}>
                        <div className='div_basic' style={{ width: '30%', height: '100%', backgroundColor: 'transparent', justifyContent: 'left', fontSize: charIndicatorFontSize }}>
                            {/* <span>&nbsp;# Opportunities:</span><span >{oppCount}</span> */}

                        </div>

                        <div className='div_basic' style={{ width: '30%', height: '100%', backgroundColor: 'transparent', justifyContent: 'center', fontSize: charIndicatorFontSize }}>
                            <span style={{ color: 'white', backgroundColor: 'red', paddingLeft: '7px', paddingRight: '7px', display: displayWorking }}>working ...</span>
                        </div>

                        <div style={{ display: 'flex', width: '40%', height: '100%', justifyContent: 'center', alignItems: 'center', backgroundColor: 'transparent' }} >
                            <CSVLink data={props.reportsList} filename={"portfolio.csv"} style={{ width: protfolio_csv_width, height: button_height, fontSize: buttonTextFont }}>Portfolio CSV</CSVLink>
                        </div>
                    </div>



                </div>

            </div >
        </div>
    )
}
export default PortfolioTradeReport 
