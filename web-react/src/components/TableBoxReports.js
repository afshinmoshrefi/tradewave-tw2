
// test if selected portfolio is a autoTrade portfolio:
// selectedPortfolioName[0] === '&'

import React, { useEffect, useState, useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
// import { IoIosArrowDown, IoIosArrowUp } from "react-icons/io";
import { BsTrash3, BsChevronExpand, BsChevronDown, BsChevronUp, BsFillStopFill } from "react-icons/bs";
// import { FaSquareFull } from "react-icons/fa";
import { AiOutlineDollarCircle } from "react-icons/ai";
import { BiSolidSquare, BiSquare } from "react-icons/bi"

import { IoReloadCircle, IoReloadOutline, IoRefreshSharp } from "react-icons/io5";
import { HiDocumentReport, HiOutlineDocumentReport } from "react-icons/hi";
import { BiCalendar } from "react-icons/bi";
import Tippy from '@tippyjs/react'
import './styles/TableBox.css'
import { getByPlaceholderText } from '@testing-library/react';
import { AiFillAndroid } from "react-icons/ai";
import TextBox from './TextBox'
import { getTodayDate } from './Common'
import { incrementDate } from './Common'
import { getCookie, setCookie } from './Common'
import { statusColor } from './Common'
import { PiStrategyFill } from "react-icons/pi";
import { IoIosAirplane } from "react-icons/io";
import { FiType } from "react-icons/fi";
import { TbReportSearch } from "react-icons/tb";
import { TbReportMoney } from "react-icons/tb";
import { userlist_amp, userlist_auto } from './Common';
import { BiSolidReport } from "react-icons/bi";
import { RiArticleLine, RiArticleFill } from "react-icons/ri";  // for news article switches <RiArticleLine />  

function zfill(str, width) {
    const padding = width - str.length;
    if (padding > 0) {
        return '0'.repeat(padding) + str;
    } else {
        return str;
    }
}

// clickedRowIndex is for when tablebox is refershed to keep the selected row intact if -1 no row has been selected
const TableBoxReports = ({ table_data, handlerRowClicked, getCurValue, handlerKeyDown, rowIndexDRclicked, clickedRowIndex, SetRowIndexDRclicked, filterText, handlerLoadClicked, handlerDelClicked, handlerLinkClicked, handlerRefreshClicked, handlerCreateCalendarEvent, tooltipSW, SetOppTableLength, securityTypeList, handleBlur, selectedPortfolioID, showDiv, setShowDiv, handlerStatusClicked, icon_status_size, selectedPortfolioName, newsToggle, PublishArticle }) => {


    // console.log('sssssssssssssssssssssssssssssssssssssss', selectedPortfolioName, selectedPortfolioName[0])

    const { rdd, browserH, browserW, tableTextSize, tableTitleTextSize, resourceObj, loggedinUser, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    const [tableDataProcessed, SetTableDataProcessed] = useState(table_data)


    const [colSorted, SetColSorted] = useState('');
    const [sortedDir, SetSortedDir] = useState('a');

    const [tableTitleDict, SetTableTitleDict] = useState({})
    const [tableTitleTooltip, SetTableTitleTooltip] = useState({})

    const [delayTextRender, SetDelayTextRender] = useState(false); // used for share update to stop flashing info text



    var secondColSort = 'date' // this is not generic only for this  have to move it to parent

    // use these colors to alter the selected row color when its over lighgreen and pink
    var selected_color_over_lightgreen = 'rgb(159, 227, 187)';
    var selected_color_over_pink = 'rgb(214, 204, 217)';



    // desktop values are default
    var rowHeight = '3vh';
    // var tableFont = tableTextSize;
    var tableFont = '0.7vw';
    // var titleFont = tableTitleTextSize;
    var titleFont = '0.75vw';

    var icon_calendar_size = 18;
    var icon_trash_size = 14;
    var icon_load_size = 15;
    var icon_report_size = 19;

    // var icon_status_size = 17;

    var infoFont1 = '1vw'; // this is for text before any opps added
    var infoFont2 = '2vw'; // this is for a enlarged red +


    var total_price_width = 5;
    var shares_width = 2;

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
        tableFont = '2.7vw';
        rowHeight = '4.5vh';
        titleFont = '2.6vw';
        infoFont1 = '4.8vw';
        infoFont2 = '8vw';
        total_price_width = 3;
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
        tableFont = '1.5vw';
        titleFont = '1.5vw';
        icon_calendar_size = 17;
        icon_trash_size = 14;
        icon_load_size = 16;
        icon_report_size = 19;
        infoFont1 = '1.8vw';
        infoFont2 = '3.4vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) {
        if (browserH >= 1024) {
            icon_calendar_size = 27;
            icon_trash_size = 23;
            icon_load_size = 26;
            icon_report_size = 27;
            tableFont = '1.9vw';
            titleFont = '1.7vw';
            infoFont1 = '3vw';
            infoFont2 = '6vw';
        }
        else {
            tableFont = '2.0vw';
            titleFont = '1.7vw';
        }

    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) {
        tableFont = '1.0vw';
        titleFont = '1.0vw'
        infoFont1 = '1.5vw';
        infoFont2 = '3vw';
    }
    //-------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        // first get the sorted title and direction from the cookie for this portfolio

        let cookie = getCookie(`port_${selectedPortfolioID}`)

        if (cookie !== null) {
            SetColSorted(cookie.split(',')[0]);
            SetSortedDir(cookie.split(',')[1]);
        }



        // columns to be displayed on reports dashboard
        // date ticker days DIR sharpe_Ratio years group slug

        var tmp = JSON.parse(JSON.stringify(table_data)) //copy the json object to tmp

        // console.log('tmp=', tmp)

        var tmp2 = []; // tmp2 changes the order of the columns that comes from tmp
        var tmpTT = []

        for (let i = 0; i < tmp.length; i++) {


            let group = resourceObj[parseInt(tmp[i]['resourceID'])]
            if (group === 'FUTURES & COMMODITIES') {
                group = 'F&C'
            }
            else if (group === 'RUSSELL 1000 STOCKS') {
                group = 'RUSSELL 1000'
            }
            else if (group === 'NASDAQ 100 STOCKS') {
                group = 'NASDAQ 100'
            }
            else if (group === 'GOVERNMENT BONDS') {
                group = 'GOV BONDS'
            }

            let date2 = incrementDate(tmp[i]['date'], tmp[i]['days_hold'] - 1)
            let opp_years = tmp[i]['years'].toUpperCase();
            if (opp_years === 'PE0') opp_years = 'PE';

            let opp_dir = tmp[i]['direction']

            if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { //smartphones only - make long L and short S
                if (opp_dir === 'long') opp_dir = 'L';
                else if (opp_dir === 'short') opp_dir = 'S';
            }

            // console.log(tmp[0])

            let slug = tmp[i]['slug'];
            let orders = tmp[i]['orders'];
            let positions = tmp[i]['positions']
            let has_orders = orders === undefined ? false : true;
            // let has_positions = positions === undefined || positions.length == 0 ? false : true;
            // console.log('orders=',orders)
            // if tmp[i].hasOwnProperty('orders'){

            // }
            let newobj = {
                id: tmp[i]['id'], // this id preserves the order based on the original list - this is not dr_id
                S: tmp[i]['status'],
                Date1: tmp[i]['date'],
                Date2: date2,
                days: parseInt(tmp[i]['days_hold']),
                ticker: tmp[i]['symbol'],
                DIR: opp_dir,
                sharpe_Ratio: parseFloat(tmp[i]['sharpe_ratio']),
                years: opp_years,
                group: group,
                load: 'x',
                slug: slug,
                refresh: 'x', // replaced refresh with calendar - didn't change the names just the icons 
                X: 'X',
                num: parseInt(tmp[i]['num_shares']),
                I: '$' + Math.ceil(tmp[i]['num_shares'] * tmp[i]['price1']).toString(),
                G: tmp[i]['gain_loss'].toFixed(1) + '%',
                orders: has_orders,
                article_exists: tmp[i]['article_exists'] ? true : false,
                article_queued: tmp[i]['article_queued'] ? true : false,
            }


            //###############################################################################################
            // column restrictions by defice is implemented by deleting the column from the list of objects
            //###############################################################################################
            // delete newobj.orders;
            if (rdd.isMobile && browserH > browserW) { // mobile portrait
                delete newobj.group;
                delete newobj.sharpe_Ratio;
                delete newobj.years;
                delete newobj.days;
                delete newobj.num;

            }

            tmp2.push(newobj)
        }

        // console.log('tmp2=', tmp2)


        if (tmp2.length > 0 && colSorted !== '') {
            var colType = typeof (tmp2[0][colSorted])
            if (colSorted === 'years') colType = 'string'; // sepcial type because years could be numbers and PE, PE1, PE2, PE3

            tmp2.sort((a, b) => {
                var ret;
                if (colType === 'number') {
                    if (sortedDir === 'a') ret = a[colSorted] - b[colSorted];
                    else if (sortedDir === 'd') ret = b[colSorted] - a[colSorted];
                }
                else {
                    if (colSorted === 'years') { // years is a spcial case - its numbers and PE PE1 PE2 and PE3 - so sorting has to be custom
                        let aa = a[colSorted];
                        let bb = b[colSorted];
                        aa = zfill(aa, 3)
                        bb = zfill(bb, 3)

                        if (sortedDir === 'a') {
                            // console.log('aa,bb', aa, bb)
                            if (aa < bb) ret = -1;
                            else if (aa > bb) ret = 1;
                            else ret = aa - bb;
                        }
                        else if (sortedDir === 'd') {
                            if (aa < bb) ret = 1;
                            else if (aa > bb) ret = -1;
                            else ret = aa - bb;
                        }
                    }
                    else {
                        if (sortedDir === 'a') {
                            if (a[colSorted] < b[colSorted]) ret = -1;
                            else if (a[colSorted] > b[colSorted]) ret = 1;
                            else ret = a[secondColSort] - b[secondColSort];
                        }
                        else if (sortedDir === 'd') {
                            if (a[colSorted] < b[colSorted]) ret = 1;
                            else if (a[colSorted] > b[colSorted]) ret = -1;
                            else ret = a[secondColSort] - b[secondColSort];
                        }
                    }
                }
                return (ret)
            })
        }


        // now find and set the SetRowIndexDRclicked based on what row was selected before
        for (let i = 0; i < tmp2.length; i++) {
            if (tmp2[i]['id'] === clickedRowIndex) {
                SetRowIndexDRclicked(i); // set the index of the selected row for display based on the sorted data
                break;  // found it - now i is the UI location of the row
            }
        }

        // console.log('tmp22222222222222222222222222222222222222=',tmp2)

        SetTableDataProcessed(tmp2)

        SetOppTableLength(tmp.length)

        // the condition that status only changes should not kill the selected row

        //  SetRowIndexDRclicked(null)

        // this is to adjust the width of symbol column when there is a really long ticker in one of the rows
        let longest_ticker = 0;
        for (let key in tmp2) {
            if (tmp[key]['symbol'].length > longest_ticker) longest_ticker = tmp[key]['symbol'].length;
            if (longest_ticker >= 10) break;
        };

        let daysout_title = 'Hold-Days'
        if (longest_ticker >= 10) daysout_title = 'Days';  // when a ticker is too long, it will screw up the table.  
        // reducing width of title "Days-Hold" to "Days" fixes it
        daysout_title = 'Days'; // just make it days 9/19/2022
        //lazy lookup table to change the table titles

        var tmpDict = {}
        var tmpDict_tt = {}

        // console.log('tttttttttttttttttttttttttttmpDict',tmpDict)


        if (tmp2.length > 0) {
            for (var i = 0; i < Object.keys(tmp2[0]).length; i++) {
                var k = Object.keys(tmp2[0])[i]

                if (rdd.isMobile && browserH > browserW) {
                    if (k === 'days') { tmpDict['days'] = 'Day'; tmpDict_tt['daysOut'] = 'Number of calendar days to hold the security for the opportunity.  After clicking an opportunity, you can see the date range determined by start-date and days-hold on the header of seasoanl viewer. Click to sort by Days-Hold' }
                    else if (k === 'Date') { tmpDict['Date'] = 'Date'; tmpDict_tt['date'] = 'Start date of the wave opportunity' }

                    else if (k === 'Date1') { tmpDict['Date1'] = 'Entry'; tmpDict_tt['Date1'] = 'Start date of the Date Range Opportunity' }
                    else if (k === 'Date2') { tmpDict['Date2'] = 'Exit'; tmpDict_tt['Date2'] = 'End date of the Date Range Opportunity' }

                    else if (k === 'ticker') { tmpDict['ticker'] = 'TKR'; tmpDict_tt['symbol'] = 'Ticker symbol for the opportunity. click to sort by Ticker symbol' }
                    else if (k === 'years') { tmpDict['years'] = 'Yrs'; tmpDict_tt['lOrS'] = 'Direction of the opportunity, can be Long or Short. Click to sort by opportunity direction' }
                    else if (k === 'sharpe_Ratio') { tmpDict['sharpe_Ratio'] = 'Sharpe Ratio'; tmpDict_tt['sharpe_ratio'] = 'Sharpe ratio helps qualify the quality of the opportunity.  Sharpe Ratio higher than 1 shows the strategy to have stable return. Higher Sharpe Ratio is better.  Below 1 means the strategy has less stable returns. Click to sort by Sharpe-ratio' }
                    else if (k === 'group') { tmpDict['group'] = 'Group'; tmpDict_tt['date'] = 'Start date of the wave opportunity' }
                    else if (k === 'slug') { tmpDict['slug'] = 'Link'; tmpDict_tt['slug'] = 'Start date of the wave opportunity' }

                    else if (!rdd.isTablet && k === 'DIR') { tmpDict['DIR'] = ''; tmpDict_tt['DIR'] = 'direction' } // 12/3/2023


                    else tmpDict[k] = k
                }
                else if (rdd.isMobile && browserH < browserW) {
                    if (k === 'days') { tmpDict['days'] = 'Day'; tmpDict_tt['daysOut'] = 'Number of calendar days to hold the security for the opportunity. Date1 + Days = Date2. Click to sort the opportunities by # of Days.' }
                    else if (k === 'Date') { tmpDict['Date'] = 'Date'; tmpDict_tt['date'] = 'Start date of the wave opportunity' }
                    else if (k === 'ticker') { tmpDict['ticker'] = 'TKR'; tmpDict_tt['symbol'] = 'Ticker symbol for the opportunity. click to sort by Ticker symbol' }
                    else if (k === 'years') { tmpDict['years'] = 'Yrs'; tmpDict_tt['lOrS'] = 'Direction of the opportunity, can be Long or Short. Click to sort by opportunity direction' }
                    else if (k === 'sharpe_Ratio') { tmpDict['sharpe_Ratio'] = 'SR'; tmpDict_tt['sharpe_ratio'] = 'Sharpe ratio helps qualify the quality of the opportunity.  Sharpe Ratio higher than 1 shows the strategy to have stable return. Higher Sharpe Ratio is better.  Below 1 means the strategy has less stable returns. Click to sort by Sharpe-ratio' }
                    else if (k === 'group') { tmpDict['group'] = 'Group'; tmpDict_tt['date'] = 'Start date of the wave opportunity' }
                    else if (k === 'slug') { tmpDict['slug'] = 'Link'; tmpDict_tt['slug'] = 'Start date of the wave opportunity' }

                    else tmpDict[k] = k
                }
                else {
                    // these are exceptions and tooltips
                    if (k === 'days') { tmpDict['days'] = 'Days'; tmpDict_tt['days'] = 'Number of calendar days to hold the security for this opportunity. Click the title to sort the list of opportunities by days' }
                    else if (k === 'Date1') { tmpDict['Date1'] = 'Entry Date'; tmpDict_tt['Date1'] = 'Start date of the Date Range Opportunity' }
                    else if (k === 'Date2') { tmpDict['Date2'] = 'Exit Date'; tmpDict_tt['Date2'] = 'End date of the Date Range Opportunity' }
                    else if (k === 'ticker') { tmpDict['ticker'] = 'Ticker'; tmpDict_tt['ticker'] = 'Ticker symbol for the opportunity. click to sort by Ticker symbol' }

                    else if (k == 'DIR') { tmpDict['DIR'] = 'DIR'; tmpDict_tt['DIR'] = 'This is the recommended direction for this opportunity.  Direction is set to long when the number of historical gains in the analysis years are equal or larger than years with loses.' }

                    else if (k === 'years') { tmpDict['years'] = 'Years'; tmpDict_tt['years'] = 'Number of historical years for analyzing this opportunity.  Click Years to sort the list by number of years' }
                    else if (k === 'sharpe_Ratio') { tmpDict['sharpe_Ratio'] = 'SR'; tmpDict_tt['sharpe_Ratio'] = 'Sharpe ratio helps qualify the quality of the opportunity.  Sharpe Ratio higher than 1 shows the strategy to have stable return. Higher Sharpe Ratio is better.  Below 1 means the strategy has less stable returns. Click to sort by Sharpe Ratio' }

                    else if (k === 'group') { tmpDict['group'] = 'Group'; tmpDict_tt['group'] = 'This is the Financial Group the opportunity Ticker symbol belongs to.  Click the title to sort by Financial Group+' }

                    else if (k === 'slug') {
                        tmpDict['slug'] = 'Link';
                        if (newsToggle === false) {
                            tmpDict_tt['slug'] = 'Click the link to view the Web Report for this Date-Range-Opportunity.  If the web page for the Date-Range-Report is unavailable, it has been automatically deleted by the server 30 days after the opportunity end date.  To recreate the web report, click the Refresh icon to the right of the link icon'
                        }
                        else {
                            tmpDict_tt['slug'] = 'Click for News Article Management'
                        }
                    }

                    else if (k === 'S') { tmpDict['S'] = 'Click to change Filter Flags'; tmpDict_tt['S'] = 'Filter Flags are discretionary labels that can be set for quick reminders and categorization.  You can also set the Flags in order to segment your portfolio.  For example if you assign 3 opportunities with Red flags, you can set "Total Invested" Flag on the bottom left row, to red and view the statistics for only the selected opportunities with red flags.  You can change the Flag by clicking on it.  Flag is off when white outline square is displayed.' }
                    else if (k === 'I') { tmpDict_tt['I'] = 'Current value of the investment'}
                    else if (k === 'refresh') { tmpDict_tt['refresh'] = 'Easily schedule the opportunity Date Range by adding it to your Google Calendar. You can create two events - one for the start and the other for the end dates of this opportunity. Keep track of your progress and stay organized with Trade Seasonal Dashboard' }
                    else if (k === 'load') { tmpDict_tt['load'] = 'Click to load the Date-Range-Opportunity in the Seasonal Viewer' }
                    else if (k === 'X') { tmpDict_tt['X'] = 'Click to remove the Opportunity from the list' }
                    // else if (k === 'DIR') { tmpDict_tt['DIR'] = 'Direction represents the optimum direction of the opportunity.  When direction is long, the date range has shown historically bullish results on the date range, when direction is short, the date range has shown hisotrically bearish results on this date range'}
                    else if (k === 'id') { tmpDict_tt['id'] = 'This id is an identifier that shows the opportunity on the list.  It is regenerated everytime the list is displayed.  It does not have any significance in the system. It just helps to navigate the list better' }
                    else if (k === 'num') { tmpDict_tt['num'] = 'Enter number of shares from 1 to 10,000 - the shares will be used to calculate the total investment and profit/loss for the wave opportunity.  Set it to 0 to eliminate it from the total investment calculation.' }
                    else if (k === 'G') { tmpDict_tt['G'] = 'The Gain and Loss percentage is the percentage of profit or loss that has been made on the financial instrument, calculated based on the purchase date and the end date of the opportunity. If the current date falls within the date range of the opportunity, the opportunity is considered active. The percentage gain or loss of an active trade is determined by the last available price of the financial instrument' }

                    else tmpDict[k] = k
                }
            }


            SetTableTitleDict(tmpDict)
            SetTableTitleTooltip(tmpDict_tt)

        }

    }, [sortedDir, colSorted, filterText, table_data])
    //-------------------------------------------------------------------------------------------------------------------
    const handleTitleClicked = (title) => (event) => {


        let dir = 'a';

        if (colSorted !== title) {
            SetColSorted(title)
            SetSortedDir('a');
            dir = 'a';
        }
        else {
            if (sortedDir === 'a') {
                SetSortedDir('d');
                dir = 'd';
            }
            else {
                SetSortedDir('a');
                dir = 'a';
            }
        }

        setCookie(`port_${selectedPortfolioID}`, `${title},${dir}`, 300); // save selected sorted title and direction in a cookie for the current portfolio

    }

    //-------------------------------------------------------------------------------------------------------------------
    const tableStyle = {
        fontSize: tableFont,
    }
    //-------------------------------------------------------------------------------------------------------------------
    const tableTDstyle = {
        verticalAlign: 'middle',
        height: rowHeight,
        // backgroundColor:'red'
    }
    //-------------------------------------------------------------------------------------------------------------------
    const iconFillColor = tc.text;
    //-------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------
    const getTDBackColor = (key, row, index) => {
        var tdc = 'transparent';


        // it was really hard to do this if statement in just 2 so I did it in 4


        if (index === rowIndexDRclicked) {


            if ((key === 'G' && parseFloat(row['G']) > 0)) {
                tdc = selected_color_over_lightgreen;
            }

            else if ((key === 'G' && parseFloat(row['G']) < 0)) {
                tdc = selected_color_over_pink;
            }


            else if (key === 'DIR' && (row['DIR'] === 'long' || row['DIR'] === 'L')) {
                tdc = selected_color_over_lightgreen;
            }

            else if (key === 'DIR' && (row['DIR'] === 'short' || row['DIR'] === 'S')) {
                tdc = selected_color_over_pink;
                // console.log('tdc now is for short ',tdc)
            }

            // if(key === 'DIR')console.log('===',index,key,tdc)

            return tdc;
        }

        // console.log('others')

        var lcolor = 'pink';
        var gcolor = 'lightgreen';
        var gl = parseFloat(row['G'])

        if (key === 'G' && gl > 0) tdc = gcolor;
        else if (key === 'G' && gl < 0) tdc = lcolor;
        else if (key === 'DIR' && (row['DIR'] === 'long' || row['DIR'] === 'L')) tdc = gcolor;
        else if (key === 'DIR' && (row['DIR'] === 'short' || row['DIR'] === 'S')) tdc = lcolor;

        // if(key === 'DIR')console.log(key,tdc)

        return tdc
    }
    //-------------------------------------------------------------------------------------------------------------------
    const getInvestment = (row) => {

        // console.log('getInvestment row=',row);

        let today_date = getTodayDate();
        let td = JSON.parse(JSON.stringify(table_data));
        if (td.length === 0) return '';

        let idx = row['id'];

        // console.log('getInvestment Index=',idx)

        // console.log('getInvestment td=',td)
        // console.log('-----------------',today_date)

        if (td[idx]['date'] > today_date) return '$0';
        let price = parseFloat(td[idx]['price1']);
        let shares = parseInt(td[idx]['num_shares']);
        let investment = Math.ceil(shares * price);
        investment = investment.toLocaleString();
        return '$' + investment;
    }
    //-------------------------------------------------------------------------------------------------------------------

    const getPrice = (row) => {

        // console.log('getPrice row=',row);

        let today_date = getTodayDate();
        let td = JSON.parse(JSON.stringify(table_data));
        if (td.length === 0) return '';
        let idx = row['id'];
        if (td[idx]['date'] > today_date) return '$0';
        let price = parseFloat(td[idx]['price1']);

        return '$' + price;
    }

    //-------------------------------------------------------------------------------------------------------------------
    // adding a delay to display the text when there are no opportunities saved - otherwise it will blink it for a sec 
    useEffect(() => {
        const timer = setTimeout(() => {
            setShowDiv('flex');
        }, 1000); // 1000ms = 1s delay
        SetDelayTextRender(false);
        return () => clearTimeout(timer);
    }, [tableDataProcessed.length, delayTextRender, selectedPortfolioID])
    //-------------------------------------------------------------------------------------------------------------------
    return (

        <div tabIndex="0" onKeyDown={handlerKeyDown} style={{ width: '100%' }}>

            {tableDataProcessed.length > 0
                ?
                <table style={tableStyle} >

                    {
                        rdd.isMobile && browserH > browserW ? (
                            <colgroup>
                                <col style={{ width: '1%' }} />{/* id     */}
                                <col style={{ width: '1%' }} />{/* status     */}
                                <col style={{ width: '16%' }} />{/* date   */}
                                <col style={{ width: '16%' }} />{/* date   */}
                                <col style={{ width: '10%' }} />{/* Ticker */}
                                <col style={{ width: '5%' }} />{/* DIR    */}
                                <col style={{ width: '6%' }} />{/* go     */}
                                <col style={{ width: '6%' }} />{/* slug   */}
                                <col style={{ width: '6%' }} />{/* refresh   */}
                                <col style={{ width: '6%' }} />{/* del    */}
                                <col style={{ width: '5%' }} />{/* %    */}
                                <col style={{ width: '3%' }} />{/* # shares    */}
                            </colgroup>
                        ) : rdd.isMobile && !rdd.isTablet && browserH < browserW ? (
                            <colgroup>
                                <col style={{ width: '1%' }} />{/* id     */}
                                <col style={{ width: '1%' }} />{/* status     */}
                                <col style={{ width: '11%' }} />{/* date   */}
                                <col style={{ width: '11%' }} />{/* date   */}
                                <col style={{ width: '8%' }} />{/* Ticker */}
                                <col style={{ width: '6%' }} />{/* Days   */}
                                <col style={{ width: '6%' }} />{/* DIR    */}
                                <col style={{ width: '6%' }} />{/* Sharpe */}
                                <col style={{ width: '6%' }} />{/* years  */}
                                <col style={{ width: '14%' }} />{/* group     */}
                                <col style={{ width: '5%' }} />{/* go   */}
                                <col style={{ width: '5%' }} />{/* report   */}
                                <col style={{ width: '5%' }} />{/* calendar    */}
                                <col style={{ width: '5%' }} />{/* trash   */}
                                <col style={{ width: '4%' }} />{/* shares   */}
                                <col style={{ width: '4%' }} />{/* total_price    */}
                                <col style={{ width: '4%' }} />{/* %    */}
                            </colgroup>
                        ) : (
                            <colgroup>
                                <col style={{ width: '1%' }} />{/* this is for index to be used later */}
                                <col style={{ width: '1%' }} />{/* status     */}
                                <col style={{ width: '10%' }} />
                                <col style={{ width: '10%' }} />
                                <col style={{ width: '7%' }} />
                                <col style={{ width: '7%' }} />
                                <col style={{ width: '6%' }} />
                                <col style={{ width: '5%' }} />{/* sharpe ratio */}
                                <col style={{ width: '7%' }} />
                                <col style={{ width: '14%' }} />
                                <col style={{ width: '4%' }} />
                                <col style={{ width: '4%' }} />
                                <col style={{ width: '4%' }} />{/* refresh   */}
                                <col style={{ width: '4%' }} />
                                <col style={{ width: '4%' }} />
                                <col style={{ width: '7%' }} />
                                <col style={{ width: '5%' }} />
                            </colgroup>
                        )
                    }

                    <thead>
                        <tr style={{ fontSize: titleFont }}>
                            {Object.keys(tableDataProcessed[0])
                                .filter((title) => title !== 'article_exists' && title !== 'article_queued')
                                .map((title) => {
                                    // console.log(title); // Add this line for debugging
                                    return (
                                        <Tippy disabled = {!tooltipSW} key={title} placement={'bottom'} content={
                                            <div theme="tw" >
                                                {tooltipSW ? tableTitleTooltip[title] : ''}
                                            </div>
                                        }>
                                            {title === 'X' ?
                                                <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}><BsTrash3 size={icon_trash_size} style={{ verticalAlign: "middle", fill: tc.text }} /></th>
                                                : title === 'slug' ?
                                                    newsToggle === true
                                                        ? <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}><RiArticleFill size={icon_report_size} style={{ fill: UITheme === 'dark' ? 'cyan' : '#2563EB', verticalAlign: "middle" }} /></th>
                                                        : (selectedPortfolioName[0] === '&'
                                                            ? <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}><BiSolidReport size={icon_report_size} style={{ verticalAlign: "middle", fill: tc.text }} /></th>
                                                            : <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}><HiDocumentReport size={icon_report_size} style={{ verticalAlign: "middle", fill: tc.text }} /></th>
                                                        )
                                                    : title === 'orders' ?
                                                        <th key={title} style={{ display: 'none' }}></th>
                                                        : title === 'S' ?
                                                            <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}><BiSquare size={icon_status_size} style={{ fill: tc.textSecondary, verticalAlign: "middle" }} /></th>
                                                            : title === 'load' ?
                                                                <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}><IoReloadOutline size={icon_load_size} style={{ verticalAlign: "middle", fill: tc.text }} /></th>
                                                                : title === 'id' ?
                                                                    <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}></th>
                                                                    : title === 'G' ?
                                                                        <th key={title} style={{ backgroundColor: tc.tableHeaderBg, color: tc.text }}>%</th>
                                                                        : title === 'num' ?
                                                                            <th key={title} style={{ backgroundColor: tc.tableHeaderBg, color: tc.text }}>#</th>
                                                                            : title === 'I' ?
                                                                                <th key={title} style={{ backgroundColor: tc.tableHeaderBg, color: tc.text }}>$</th>
                                                                                : title === 'refresh' ?
                                                                                    <th key={title} style={{ backgroundColor: tc.tableHeaderBg }}>
                                                                                        {selectedPortfolioName[0] === '&'
                                                                                            ? <IoIosAirplane size={18} style={{ fill: tc.text, verticalAlign: "middle" }} />
                                                                                            : <BiCalendar size={icon_calendar_size} style={{ verticalAlign: "middle", fill: tc.text }} />
                                                                                        }
                                                                                    </th>
                                                                                    :
                                                                                    <th key={title} style={{ backgroundColor: title === colSorted ? tc.statLabelBg : tc.tableHeaderBg, color: tc.text }} onClick={handleTitleClicked(title)}>
                                                                                        {tableTitleDict[title]} {title === colSorted ?
                                                                                            (sortedDir === 'a' ? <BsChevronDown /> : <BsChevronUp />)
                                                                                            : <BsChevronExpand />}
                                                                                    </th>
                                            }
                                        </Tippy>
                                    )
                                })}
                        </tr>
                    </thead>


                    <tbody>
                        {tableDataProcessed.map((row, indexR) => {
                            // console.log("index:", index); // add this console.log statement for debugging
                            return (
                                <tr
                                    key={`row-${indexR}`}
                                    id={indexR}
                                    onClick={handlerRowClicked(indexR)}
                                    className={rowIndexDRclicked === indexR ? "selected" : "stripes"}
                                    style={{ backgroundColor: rowIndexDRclicked === indexR ? 'rgba(173,216,230,0.5)' : tc.panelBg }}
                                >
                                    {Object.keys(row)
                                        .filter((key) => key !== 'article_exists' && key !== 'article_queued')
                                        .map((key, indexC) => (
                                            <Tippy disabled  key={`tippy-${key}-${indexC}`} placement={'left'} delay={500} content={
                                                key === 'G' ? (
                                                    <div style={{ borderRadius: '10px', backgroundColor: 'black', color: 'linen', display: 'flex', flexWrap: 'wrap', height: '75px', width: '170px', fontFamily: 'sans-serif', fontSize: '0.6vw', paddingTop: '8px', paddingBottom: '6px' }}>
                                                        <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'right', width: '50%', height: '25%', backgroundColor: 'transparent' }}>Investment</div>
                                                        <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '50%', height: '25%', backgroundColor: 'transparent' }}>{getInvestment(row)}</div>

                                                        <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'right', width: '50%', height: '25%', backgroundColor: 'transparent' }}>Share Price</div>
                                                        <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '50%', height: '25%', backgroundColor: 'transparent' }}>{getPrice(row)}</div>

                                                        <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'right', width: '50%', height: '25%', backgroundColor: 'transparent' }}>Current Value</div>
                                                        <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '50%', height: '25%', backgroundColor: 'transparent' }}>{getCurValue(row)}</div>
                                                    </div>
                                                ) : null
                                            }>

                                                <td key={`col-${key}-${indexC}`} style={{ verticalAlign: 'middle', height: rowHeight, backgroundColor: getTDBackColor(key, row, indexR), color: key === 'id' ? 'transparent' : (key === 'G' && parseFloat(row['G']) === 0) ? (UITheme === 'dark' ? 'lightgray' : 'black') : (key === 'DIR' || key === 'G') ? 'black' : tc.text, display: key === 'orders' ? 'none' : 'table-cell' }}>

                                                    {key === "slug" ? (

                                                        newsToggle === true
                                                            ?
                                                            (
                                                                row.article_queued === true
                                                                    ? <RiArticleFill size={icon_report_size} style={{ fill: "#F4B400", verticalAlign: "middle" }} onClick={(event) => PublishArticle()} />
                                                                    : row.article_exists === true
                                                                        ? <RiArticleFill size={icon_report_size} style={{ fill: UITheme === 'dark' ? 'cyan' : '#2563EB', verticalAlign: "middle" }} onClick={(event) => PublishArticle()} />
                                                                        : <RiArticleLine size={icon_report_size} style={{ fill: tc.text, verticalAlign: "middle" }} onClick={(event) => PublishArticle()} />
                                                            )
                                                            : selectedPortfolioName[0] === '&'
                                                                ? <BiSolidReport size={icon_report_size} style={{ fill: selectedPortfolioName[0] === '&' && userlist_auto.includes(loggedinUser) ? tc.text : "lightgray", verticalAlign: "middle" }} onClick={(event) => handlerLinkClicked(indexR, event)} />
                                                                : <>
                                                                    <HiDocumentReport size={icon_report_size} style={{ fill: iconFillColor, verticalAlign: "middle" }} onClick={(event) => handlerLinkClicked(indexR, event)} />
                                                                    <IoRefreshSharp size={icon_report_size - 5} style={{ fill: iconFillColor, verticalAlign: "middle", marginLeft: '0.3vw' }} onClick={(event) => handlerRefreshClicked(indexR, event)} />
                                                                </>

                                                    ) : key === "X" ? (
                                                        <BsTrash3
                                                            size={icon_trash_size}
                                                            style={{ fill: iconFillColor, verticalAlign: "middle" }}
                                                            onClick={(event) => { setShowDiv('none'); handlerDelClicked(indexR, event, row['orders']) }}
                                                        />
                                                    ) : key === "load" ? (
                                                        <IoReloadOutline
                                                            size={icon_load_size}
                                                            style={{ fill: iconFillColor, verticalAlign: "middle" }}
                                                            onClick={(event) => handlerLoadClicked(indexR, event)}
                                                        />
                                                        // G is gain and loss pct - in mobile portrait numbers don't show but the color does - to save space 
                                                    ) : key === "G" && rdd.isMobile && !rdd.isTablet && browserH > browserW ? (

                                                        <div></div>

                                                    ) : key === "G" && (!rdd.isMobile || rdd.isTablet || (rdd.isMobile && !rdd.isTablet && browserH < browserW)) ? (

                                                        <div>{row[key]}</div>

                                                    ) : key === "refresh" ? (


                                                        selectedPortfolioName[0] === '&'
                                                            ? (<IoIosAirplane size={18} style={{ fill: selectedPortfolioName[0] === '&' && row['orders'] ? 'darkorange' : selectedPortfolioName[0] === '&' && userlist_auto.includes(loggedinUser) ? tc.text : "lightgray", verticalAlign: "middle" }} onClick={(event) => handlerCreateCalendarEvent(indexR, event)} />)
                                                            : (<BiCalendar size={icon_calendar_size} style={{ fill: iconFillColor, verticalAlign: "middle" }} onClick={(event) => handlerCreateCalendarEvent(indexR, event)} />)


                                                    ) : key === "num" ? (
                                                        <TextBox name='shares' width={shares_width} text={row[key]} tbBlur={(event) => { setShowDiv('none'); SetDelayTextRender(true); handleBlur('shares', row[key], event) }} />

                                                    ) : key === "S" ? (
                                                        row[key] === '0' ?

                                                            <BiSquare
                                                                size={icon_status_size}
                                                                style={{ fill: 'lightgray', verticalAlign: "middle" }}
                                                                onClick={(event) => handlerStatusClicked(indexR, event, row[key], statusColor)} />
                                                            :
                                                            <BiSolidSquare
                                                                size={icon_status_size}
                                                                style={{ fill: statusColor[row[key]], verticalAlign: "middle" }}
                                                                onClick={(event) => handlerStatusClicked(indexR, event, row[key], statusColor)} />

                                                    ) : key === "I" ? (
                                                        <TextBox name='total_price' width={total_price_width} text={row[key]} tbBlur={(event) => { setShowDiv('none'); SetDelayTextRender(true); handleBlur('total_price', row[key], event) }} />

                                                    ) : (
                                                        row[key]
                                                    )}
                                                </td>
                                            </Tippy>
                                        ))}
                                </tr>
                            );
                        })}
                    </tbody>

                </table>
                :

                <div style={{ fontSize: infoFont1, display: showDiv, height: '100%', width: '100%', backgroundColor: 'transparent', flexDirection: 'column', color: tc.text }}>
                    <p style={{ lineHeight: "1.2em", marginLeft: '0.5em', marginRight: '0.5em' }}>Welcome to Trade Wave Portfolio Manager. Here, you can easily manage your long-term and short-term investment opportunities.</p>

                    <p style={{ lineHeight: "1.2em", marginLeft: '0.5em', marginRight: '0.5em' }}>To add a new opportunity, select and display it on the Wave Viewer, then click the Plus sign <span style={{ color: 'red', fontSize: infoFont2, verticalAlign: 'middle' }}>+</span> above the Gain-Loss bar chart. This will save the opportunity to your portfolio, allowing you to track it over time.</p>

                    <p style={{ lineHeight: "1.2em", marginLeft: '0.5em', marginRight: '0.5em' }}>A colored flag can be set for each of opportunities by clicking the square on the left side of the opportunity.  Flags are used for marking specific opportunites.  By clicking the flag icon next to Total Invested on the bottom left, you can view information about the collection of opportunities with the same flag.</p>


                    <p style={{ lineHeight: "1.2em", marginLeft: '0.5em', marginRight: '0.5em' }}>The Portfolio Manager lets you monitor the profit and loss of each opportunity over time. You can also add a Google Calendar event for the start and end dates of each opportunity.
                        A custom web report is automatically generated for each opportunity.  These reports can be shared by simply clicking one of the share icons on the reports.</p>

                    <p style={{ lineHeight: "1.2em", marginLeft: '0.5em', marginRight: '0.5em' }}>Bottom section of the Portfolio Manager, shows the overall profit and loss for each of your portfolios in the bottom window. This tool is a powerful way to keep track of your opportunities and monitor your progress over time. Start taking advantage of the many benefits of the Opportunities Table in Trade Wave today!</p>
                </div>

            }




        </div>
    )
}

export default TableBoxReports
