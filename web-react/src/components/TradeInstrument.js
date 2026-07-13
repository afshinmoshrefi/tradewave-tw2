// AddGC is the dialog that displays when user clicks the add to google calendar icon in Opportunities Manager 
// Is uses the new GIS authentication method to communicate with Google Calendar

// about loading date to javascript:  d = new Date(d)
// I add time of 6AM to it and the timezone offset of the local time
// otherwise, it would screwup when calculating date to the next monday

// console.cloud.google.com to setup the APIs

// which credit spread is teh default one to use should come from appserver for the purpose of automaiton without UI 1/2/2024

// 1) which cs select, 2) risk capital / # option_contracts / account size - should be calculated and sent along with credit spread lists

import React, { useEffect, useState, useContext, useRef } from 'react';
import jwt_decode from "jwt-decode";
import { UserContext } from './UserContext'
import './styles/InfoPopup.css';
import CheckBox from './CheckBox';
// import TextBox from './TextBox';
import { getAllEventTimes } from './Common'
import SelectBox from './SelectBox'
import ExitOrderDialog from './ExitOrderDialog'
import TextBox from './TextBox';
import RiskProfileChart from './RiskProfileChart'
import Tippy from '@tippyjs/react'
import { getCookie, setCookie } from './Common'
import { GrClose } from "react-icons/gr";
import { appserverURL } from './Common';
import { TbDelta } from "react-icons/tb";
import { BsLock, BsUnlock } from "react-icons/bs";
import { getTodayDate, daysBetweenDates } from './Common';

import { BsFillCaretUpFill, BsFillCaretDownFill, BsFillCaretLeftFill, BsFillCaretRightFill } from "react-icons/bs";
import { MdOutlineCancel } from "react-icons/md";
import { ImExit } from "react-icons/im";

const ACCESS_TOKEN_SANDBOX = 'juuDvsbuylkcpM0aUc85JFABSTSB';
const ACCESS_TOKEN_PROD = 'SUbfMTAXLCda3o2NEixco0GkEGfv';

const showStreamingMessages = true; //  these are console.logs for streaming quotes and account

const frequency_update = 500; // 1000 means update every second

// chatgpt wrote this function converts dates like 2024-09-18 to Sep 18 2024 
function convertDateFormat(inputDate) {
    // Create a Date object from the input date string
    var dateObject = new Date(inputDate);

    // Get month abbreviation and full year
    var monthAbbreviation = dateObject.toLocaleString('en-us', { month: 'short' });
    var fullYear = dateObject.getFullYear();

    // Format the output date string
    var outputDate = monthAbbreviation + ' ' + fullYear;

    return outputDate;
}

// Example usage
// var inputDate = '2024-09-18';
// var result = convertDateFormat(inputDate);
// console.log(result);




const TradeInstrument = (props) => {

    const { browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)

    // const local_timezone_offset = Intl.DateTimeFormat().resolvedOptions().timeZoneOffset;

    const [creditSpreadList, SetCreditSpreadList] = useState([]);
    const [stockPrice, SetStockPrice] = useState(0);
    const stockPriceRef = useRef(0); // trying to use this for riskprofile so that it doesn't constantly

    const [checkboxSelectionList, SetCheckboxSelectionList] = useState([]);

    // const [selectedCreditSpread, SetSelectedCreditSpread] = useState(0);
    const selectedCreditSpread = useRef(0);

    const [creditSpreadPriceList, SetCreditSpreadPriceList] = useState([0, 0, 0, 0, 0]);
    const [creditSpreadStore, SetCreditSpreadStore] = useState([]); // stores latest bid ask for each of the options for later reference 
    const [availableExpirationDates, SetAvailableExpirationDates] = useState([]);

    // const [selectedExpiration, SetSelectedExpiration] = useState(0);
    const selectedExpiration = useRef(0);


    const [perTradeCapital, SetPerTradeCapital] = useState([0, 0, 0, 0]); // [capital_available,per_trade_capital,num_contracts,trade_risk_capital]
    const [saveCSdict, SetSaveCSdict] = useState({}); // this saves the credit spread dict so when another expiration is selected we don't fetch
    const [numContracts, SetNumContracts] = useState(0); // this is for the textbox
    const [credit, SetCredit] = useState(0); // this is for the textbox
    const [tradeRiskCapital, SetTradeRiskCapital] = useState(0); // this is spread - credit * 100 * num_contracts
    const [spreadPrice, SetSpreadPrice] = useState(0);
    const [autoSelection, SetAutoSelection] = useState([-1, -1]); // [expiration_date_index,credit_spread_index]
    const [streamingSymbols, SetStreamingSymbols] = useState('');

    const [exitStockGain, SetExitStockGain] = useState(5);
    const [exitStockLoss, SetExitStockLoss] = useState(10);

    const [exitOptionGain, SetExitOptionGain] = useState(25);
    const [exitOptionLoss, SetExitOptionLoss] = useState(60);

    const [daysAfter, SetDaysAfter] = useState(14) // after this many days change the option gain %
    const [daysBefore, SetDaysBefore] = useState(7) // before this many days before option expiration get out of the position
    const [daysAfterGain, SetDaysAfterGain] = useState(1)

    // const [creditLock, SetCreditLock] = useState(false);
    const creditLock = useRef(false);

    const [tradePositions, SetTradePositions] = useState([])
    const [tradeOrders, SetTradeOrders] = useState([]); // if auto-trading portfolio name starting with & query for orders from brokerage
    const [stockPriceBackgroundColor, SetStockPriceBackgroundColor] = useState('black'); // used to change price background to red or green based on price direction

    // these 4 state variables define what is being displayed in postions and orders
    const [displayedPositionIndex, SetDisplayedPositionIndex] = useState(0);
    const [displayedPosition, SetDisplayedPosition] = useState([]);
    const [displayedPositionSymbols, SetDisplayedPositionSymbols] = useState({});
    const [displayedPositionPrice, SetDisplayedPositionPrice] = useState({ 'long': 0, 'short': 0 });

    // const [showExitParametersDialog, SetShowExitParametersDialog] = useState('open'); // turns exit dialog on and off
    // const [listPossibleExitContractNumbers, SetListPossibleExitContractNumbers] = useState([]);
    const [selectedExitContractNumber, SetSelectedExitContractNumber] = useState(0);


    const [displayedPositionCost, SetDisplayedPositionCost] = useState(0); // this is per contract - negative is credit 
    const [displayedPositionSpread, SetDisplayedPositionSpread] = useState(0); // difference of strikes of long and short like $5 spread
    const [displayedPositionGainLoss, SetDisplayedPositionGainLoss] = useState(0); // shows % GL on the position display
    const [displayedPositionNumContracts, SetDisplayedPositionNumContracts] = useState(0); // shows # contracts on the position display
    const [displayedPositionToolTip, SetDisplayedPositionToolTip] = useState('');

    const [displayedOrderIndex, SetDisplayedOrderIndex] = useState(0);
    const [displayedOrder, SetDisplayedOrder] = useState([]);
    const [displayedOrderSymbols, SetDisplayedOrderSymbols] = useState({});
    const [displayedOrderPrice, SetDisplayedOrderPrice] = useState({ buy: 2, sell: 4 });
    const [positionStatus, SetPositionStatus] = useState([]); // status of each position - open or closed

    const [forceRefresh, SetForceRefresh] = useState(false); // used to force refresh of orders data after an order is placed

    const [riskProfileAtExpiration, SetRiskProfileAtExpiration] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [riskProfileNow, SetRiskProfileNow] = useState([121.02, 117.92, 34.73, 31.65, 14.13, 21.36, 23.56, 25.02, 21.85, 1.17, 6.29, 24.07])
    const [riskProfileLabels, SetRiskProfileLabels] = useState(['2009', '2010', '2011', '2000', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020'])

    const [marketOpen, SetMarketOpen] = useState(false);  // holds wether market is open for live quotes


    const waveEndActionsList = [
        { id: 0, value: "No Action", label: "No Action" },
        { id: 1, value: "Exit Position", label: "Exit Position" },
    ]


    const [waveEndAction, SetWaveEndAction] = useState('No Action')

    const earlyExcerciseActionsList = [
        { id: 0, value: "No Action", label: "No Action" },
        { id: 1, value: "Exit Position", label: "Exit Position" },
        { id: 2, value: "Covered Call", label: "Covered Call" },
    ]
    const [earlyExcerciseAction, SetEarlyExcerciseAction] = useState('No Action')

    const dialogRef = useRef(null);

    // tracks pending post-order SetForceRefresh timers so they can be cleared on unmount
    // (avoids setState on an unmounted component if the dialog closes within 2s of an order action)
    const refreshTimers = useRef([]);

    const [creditSpreadListBackgroundColor, SetCreditSpreadListBackgroundColor] = useState('RGB(225, 242, 242)')

    const BADSELECTIONCOLOR = 'RGB(255, 230, 230)';
    const ORDERDIVCOLOR = 'rgb(255,233,233)'
    // const ORDERDIVCOLOR = 'rgb(221, 221, 187)'
    const POSITIONDIVCOLOR = 'rgb(232,255,232)'
    // const POSITIONDIVCOLOR = 'rgb(245, 245, 220)'
    // const [lastUpdateTime, SetLastUpdateTime] = useState(0); // used to reduce updating quotes more than once
    //------------------------------------------------------------------------
    // device specific 
    //------------------------------------------------------------------------

    var textFontSize = '0.8vw';
    var title_width = '92%';
    var title_close_width = '4%';
    var closeIconSize = 18;
    var title_height = '8%';
    var body_height = '92%';
    var button_font_size = '0.9vw';
    var column_width = '50%';
    var word_credit = ' Credit'; // this is for display - its set to blank for mobile because of lack of space
    var rowHeight = '20%', infoRowHeight = '9%'; // infoRowHeight is for the right side window - bottom on mobile 
    var flexDirection = 'row', bodyHeight = '100%'; // this is to put the 2 columns side by side on desktop and up down on mobile portrait
    var rightBottomHeight = '53%';

    var CSW = ['8%', '70%', '22%']; // credit spread width - defines width of the 3 cells checkbox-description-credit  - updated for mobile

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { bodyHeight = '50%'; flexDirection = 'column'; textFontSize = '3.3vw'; title_width = '80%'; title_close_width = '10%'; closeIconSize = 20; title_height = '5%'; body_height = '95%'; button_font_size = '3.5vw'; column_width = '100%'; word_credit = ''; CSW = ['8%', '78%', '14%'] }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { textFontSize = '1.5vw'; button_font_size = '1.5vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { textFontSize = '2vw'; title_height = '5%'; body_height = '95%'; button_font_size = '2vw' }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { textFontSize = '1.4vw' }


    // this useEffect is for debug
    useEffect(() => {

        console.log('###########################################')
        console.log('exitStockGain=', exitStockGain);
        console.log('exitOptionGain=', exitOptionGain)
        console.log('daysAfter=', daysAfter)
        console.log('daysAfterGain=', daysAfterGain)
        console.log('daysBefore=', daysBefore)

        console.log("waveEndAction=", waveEndAction)
        console.log("earlyExcerciseAction=",earlyExcerciseAction )

        console.log('###########################################')


        // data['exitStockGain']  = exitStockGain || 0; // || 0 sets variable to 0 when a empty string is returned
        // data['exitOptionGain'] = exitOptionGain || 0;
        // data['daysAfter']      = daysAfter || 0;
        // data['daysAfterGain']  = daysAfterGain || 0;
        // data['daysBefore']     = daysBefore || 0;
        // data['waveEndAction']  = waveEndAction;
        // data['earlyExcerciseAction'] = earlyExcerciseAction;


    }, [exitStockGain, exitStockLoss, exitOptionGain, exitOptionLoss, daysAfter, daysBefore, daysAfterGain])




    //-------------------------------------------------------------------------------------------------------------------------------------
    // on unmount, clear any pending post-order refresh timers so we don't setState after the dialog closes
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {
        return () => {
            refreshTimers.current.forEach(t => clearTimeout(t));
        };
    }, []);
    //-------------------------------------------------------------------------------------------------------------------------------------
    // query for is market open or closed - state variable is to be used for streaming quotes
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        let asURL = appserverURL()
        let url = `${asURL}/get_trading_clock?token=${token}`

        fetch(url)
            .then((res) => {
                return res.json();
            })
            .then((g) => {

                let str_market_open = g['market_open_state'] === 'false' ? false : true;
                SetMarketOpen(str_market_open);
                console.log('market open =', str_market_open)
            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
            })


    }, [])
    //------------------------------------------------------------------------------------
    // this useEffect just reads the credit spread dictionary and stores it in saveCSdict 
    //------------------------------------------------------------------------------------
    useEffect(() => {

        let num_strikes = 5;
        let opp_symbol = props.googleCalendarDict['ticker'];
        let opp_start_date = props.googleCalendarDict['date1'];
        let opp_days = props.googleCalendarDict['days'];
        let direction = props.googleCalendarDict['direction'];

        let asURL = appserverURL()
        let url = `${asURL}/get_creditspreads_data/${opp_symbol}/${opp_start_date}/${opp_days}/${num_strikes}?token=${token}`


        console.log('url=', url)

        fetch(url)
            .then((res) => {
                return res.json();
            })
            .then((g) => {

                // console.log('------------------------------------------ get_creditspreads_data g=', g)

                SetSaveCSdict(g);

                let tmp = g['auto_selection']

                if (props.googleCalendarDict['direction'] === 'long') { // reason for props.googleCalendarDict['direction'] - I reused the component calendar notfication dialog didn't change vars
                    console.log('selectedExpiration.current=', selectedExpiration.current)
                    if (g['auto_selection']['bullish'][selectedExpiration.current] === -1) {
                        SetCreditSpreadListBackgroundColor(BADSELECTIONCOLOR);
                        SetAutoSelection([0, 0]);
                    }
                    else {
                        SetAutoSelection(g['auto_selection']['bullish']);
                        selectedExpiration.current = g['auto_selection']['bullish'][0];
                    }

                }
                else {
                    if (g['auto_selection']['bearish'][selectedExpiration.current] === -1) {
                        SetCreditSpreadListBackgroundColor(BADSELECTIONCOLOR);
                        SetAutoSelection([0, 0]);
                    }
                    else {
                        SetAutoSelection(g['auto_selection']['bearish']);
                        selectedExpiration.current = g['auto_selection']['bearish'][0];
                    }
                }

                let expiration_list = Object.keys(g['creditspreads_dict']);
                let long_or_short = props.googleCalendarDict['direction'];
                var symbols = '';
                for (let i = 0; i < expiration_list.length; i++) {
                    if (long_or_short === 'long') {
                        for (let j = 0; j < g['creditspreads_dict'][expiration_list[i]]['bullish_creditspreads'].length; j++) {
                            let s;

                            s = g['creditspreads_dict'][expiration_list[i]]['bullish_creditspreads'][j]['buy']['symbol']
                            symbols += s + ',';
                            s = g['creditspreads_dict'][expiration_list[i]]['bullish_creditspreads'][j]['sell']['symbol']
                            symbols += s + ',';
                        }
                    }
                    else {
                        for (let j = 0; j < g['creditspreads_dict'][expiration_list[i]]['bearish_creditspreads'].length; j++) {
                            let s;
                            s = g['creditspreads_dict'][expiration_list[i]]['bearish_creditspreads'][j]['buy']['symbol']
                            symbols += s + ',';
                            s = g['creditspreads_dict'][expiration_list[i]]['bearish_creditspreads'][j]['sell']['symbol']
                            symbols += s + ',';
                        }
                    }
                }
                symbols = symbols + props.googleCalendarDict['ticker']
                SetStreamingSymbols(symbols);

                // console.log('streaming symbols=', symbols)

                // SetCreditSpreadListBackgroundColor('RGB(225, 242, 242)'); // reset background color of credit spread list display - in case it was red or pink or somethign due to problem credits prad

            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
            })

    }, []);
    //-------------------------------------------------------------------------------------
    // this useEffect manages assigment of creditspreads based on expiration date selected
    //-------------------------------------------------------------------------------------
    useEffect(() => {


        if (autoSelection[1] !== -1) {


            var initialSelectedIndex = autoSelection[1]; // this is from auto selection coming back from appserver

            selectedCreditSpread.current = initialSelectedIndex;

            if (Object.keys(saveCSdict).length > 0) {

                let g = saveCSdict;

                let expiration_list = Object.keys(g['creditspreads_dict'])
                SetAvailableExpirationDates(expiration_list);

                let tmp = props.googleCalendarDict['direction'] === 'long' ? g['creditspreads_dict'][expiration_list[selectedExpiration.current]]['bullish_creditspreads'] : g['creditspreads_dict'][expiration_list[selectedExpiration.current]]['bearish_creditspreads']


                SetCreditSpreadList(tmp);
                let cb_list = Array(tmp.length).fill(false); // value of each displayed checkbox
                cb_list[initialSelectedIndex] = true; // these are initial values for the checkboxes for selections
                SetCheckboxSelectionList(cb_list);
                let price = g['stock_quote']['last'];

                // console.log('stock price =',price)

                SetStockPrice(price.toFixed(2));
                let pl = [];
                let bidask_store = []; // this is for SetCreditSpreadStore - to save bid ask for later calculations
                for (let i = 0; i < tmp.length; i++) {

                    let buy_price = (tmp[i]['buy']['bid'] + tmp[i]['buy']['ask']) / 2;
                    let sell_price = (tmp[i]['sell']['bid'] + tmp[i]['sell']['ask']) / 2;
                    let cs_price = sell_price - buy_price;
                    pl.push(cs_price.toFixed(2));

                    let tmpBidAsk = { 'buy_bid': tmp[i]['buy']['bid'], 'buy_ask': tmp[i]['buy']['ask'], 'sell_bid': tmp[i]['sell']['bid'], 'sell_ask': tmp[i]['sell']['ask'] }
                    bidask_store.push(tmpBidAsk);
                }
                SetCreditSpreadPriceList(pl);
                SetCreditSpreadStore(bidask_store);
                SetPerTradeCapital([g['capital_available'], g['per_trade_capital'], 0, 0])


                // set values for the initially selected creditspread
                let credit = pl[initialSelectedIndex];
                SetCredit(credit);
                let sell_strike = tmp[initialSelectedIndex]['sell']['strike'];
                let buy_strike = tmp[initialSelectedIndex]['buy']['strike'];
                let spread = Math.abs(sell_strike - buy_strike);

                SetSpreadPrice(spread)
                let risk_per_cont = (spread - credit) * 100; // 100 shares per contract
                let numContracts;
                if (perTradeCapital[1] === 0) numContracts = 1;
                else numContracts = parseInt(g['per_trade_capital'] / risk_per_cont);

                SetNumContracts(numContracts);
                let trade_total_risk = numContracts * risk_per_cont;
                SetTradeRiskCapital(trade_total_risk);


            }

        }
        else { // this is when there is auto selection returns -1 means all creditspread filter tests failed
            // SetCreditSpreadList(tmp);
        }
    }, [autoSelection, selectedExpiration.current, saveCSdict, streamingSymbols]);
    //-----------------------------------------------------------------------------
    // process line for streaming
    //-----------------------------------------------------------------------------
    const process_streaming_line = (line) => {
        // console.log(typeof(line))
        // console.log('lllllllllllllllllllllllline=',line)

        let tmp = JSON.parse(line); // make it an Object
        let bid = tmp['bid'];
        let ask = tmp['ask'];
        let symbol = tmp['symbol'];




        if (bid === undefined || ask === undefined) return; // no quotes in this line - its probably a trade that doesn't have bid and ask

        // console.log('line=',line)
        // console.log('bid and ask = ',bid,ask)

        // update the stock price coming live to us


        if (symbol === props.googleCalendarDict['ticker']) {
            let new_stock_price = (bid + ask) / 2;
            // stock_price = stock_price.toFixed(2);
            if (new_stock_price !== 0.0 && Math.abs(new_stock_price - stockPrice) < stockPrice * 0.1) { // checking if the new stock priice change is less than 10% of the previous stock price. this will remove rogue quotes
                SetStockPrice(new_stock_price.toFixed(2));
            }
        }
        // update the options price coming live to us
        else {


            // console.log('lllllllllllllllllllllllline=', line)

            // update option prices for displayed postion
            if (tradePositions.length > 0) {
                let dp = tradePositions[displayedPositionIndex]

                let long_option_symbol = dp['leg0']['symbol']
                let short_option_symbol = dp['leg1']['symbol']

                if (symbol === long_option_symbol) {
                    // console.log('streaming long position displayedPositionPrice=',displayedPositionPrice)
                    let tmp_dict = JSON.parse(JSON.stringify(displayedPositionPrice)); // deep copy

                    // console.log('long option symbol tmp_dict=', tmp_dict)

                    tmp_dict = { 'long': (bid + ask) / 2, 'short': tmp_dict['short'] }

                    // console.log('long_option changed ...', tmp_dict['long'], tmp_dict['short'])

                    SetDisplayedPositionPrice(tmp_dict);
                    //###################################################################################
                    let position_value = -tmp_dict['short'] + tmp_dict['long']; // this is causing NaN
                    //###################################################################################

                    let risk_capital = displayedPositionSpread * 100 + displayedPositionCost; // position_cost should be negative due to credit

                    if (risk_capital > 0) {

                        // console.log('about risk_capital - long option ',displayedPositionSpread,displayedPositionCost)

                        // let positionContracts = displayedPositionNumContracts; // just did this state variable 1/29/2024

                        let gain_loss = -displayedPositionCost + position_value;
                        let pct_gain_loss = ((gain_loss * 100 * displayedPositionNumContracts / risk_capital) * 100).toFixed(2);

                        // console.log('^^^^^^^^^^^^ displayedPositionGainLoss - long option',
                        //     '\n 1)', displayedPositionGainLoss,
                        //     '\n 2)', gain_loss,
                        //     '\n 3)', displayedPositionNumContracts,
                        //     '\n 4)', risk_capital,
                        //     '\n 5)', displayedPositionCost,
                        //     '\n 6)', position_value
                        // )


                        SetDisplayedPositionGainLoss(pct_gain_loss); // streming long option
                    }
                    // SetDisplayedPositionToolTip(
                    //     `${displayedPositionNumContracts} contracts, 
                    //     ${displayedPositionSpread} spread, 
                    //     ${displayedPositionCost} credit, 
                    //     $${gain_loss}${gain_loss > 0 ? 'Profit' : 'Loss'},
                    //     ${pct_gain_loss}${pct_gain_loss > 0 ? 'Profit' : 'Loss'} ,
                    //     ${risk_capital} Risk Capital
                    //     `
                    // )

                }
                else if (symbol === short_option_symbol) {
                    let tmp_dict = JSON.parse(JSON.stringify(displayedPositionPrice));

                    tmp_dict = { 'long': tmp_dict['long'], 'short': (bid + ask) / 2 }; // mark price

                    // console.log('short option symbol tmp_dict=', tmp_dict)

                    // console.log('short_option changed ...', tmp_dict['long'], tmp_dict['short'])

                    SetDisplayedPositionPrice(tmp_dict);

                    let position_value = -tmp_dict['short'] + tmp_dict['long'];
                    let risk_capital = displayedPositionSpread * 100 + displayedPositionCost; // position_cost should be negative due to credit
                    if (risk_capital > 0) {

                        let gain_loss = -displayedPositionCost + position_value;
                        let pct_gain_loss = ((gain_loss * 100 * displayedPositionNumContracts / risk_capital) * 100).toFixed(2);


                        // console.log('about risk_capital - short option ',displayedPositionSpread,displayedPositionCost)

                        // console.log('-----------------------------------------------short option----------------------')
                        // console.log('position_value=', position_value);
                        // console.log('risk_capital=', risk_capital);
                        // console.log('gain_loss=', gain_loss);
                        // console.log('pct_gain_loss=', pct_gain_loss);

                        SetDisplayedPositionGainLoss(pct_gain_loss); // streami9ng short option

                        // console.log('&&&&&&&&&&&&&& displayedPositionGainLoss - short option',
                        //     '\n 1)', displayedPositionGainLoss,
                        //     '\n 2)', gain_loss,
                        //     '\n 3)', displayedPositionNumContracts,
                        //     '\n 4)', risk_capital,
                        //     '\n 5)', displayedPositionCost,
                        //     '\n 6)', position_value
                        // )
                    }
                }


            }

            // update option prices for displayed creditspread lists
            for (let i = 0; i < creditSpreadList.length; i++) {
                let buy_option_symbol = creditSpreadList[i]['buy']['symbol']
                let sell_option_symbol = creditSpreadList[i]['sell']['symbol']

                if (symbol === buy_option_symbol || symbol === displayedOrderSymbols['buy']) {
                    // calculate a new spread price
                    let sell_bid, sell_ask;

                    if (creditSpreadStore.length > 0) {
                        sell_bid = creditSpreadStore[i]['sell_bid'];
                        sell_ask = creditSpreadStore[i]['sell_ask'];
                    }
                    else {
                        sell_bid = creditSpreadList[i]['sell']['bid']; // these values are from existing object stored
                        sell_ask = creditSpreadList[i]['sell']['ask'];
                    }

                    let sell_price = (sell_bid + sell_ask) / 2;
                    let buy_price = (bid + ask) / 2; // this is a new price
                    let cs_price = sell_price - buy_price;
                    // now update the creditSpreadList and saveCSdict with new values

                    if (symbol === buy_option_symbol) {
                        let pl = [...creditSpreadPriceList]; // copy first - mutating + setting the same ref makes React bail out
                        pl[i] = cs_price.toFixed(2);
                        SetCreditSpreadPriceList(pl)
                        // update creditSpreadStore with the newest values
                        let tmpBA = { 'buy_bid': bid, 'buy_ask': ask, 'sell_bid': sell_bid, 'sell_ask': sell_ask };
                        let tmpCSS = [...creditSpreadStore];
                        tmpCSS[i] = tmpBA;
                        SetCreditSpreadStore(tmpCSS);
                        if (i === selectedCreditSpread.current && !creditLock.current) {
                            // console.log('streaming 1 is updating credit', i, selectedCreditSpread.current, creditLock.current)
                            SetCredit(pl[selectedCreditSpread.current]);
                        }
                    }
                    if (symbol === displayedOrderSymbols['buy']) {
                        let tmpd = { ...displayedOrderSymbols }; //copying
                        tmpd['buy'] = buy_price;

                        SetDisplayedOrderPrice(tmpd)
                    }
                    break;
                }
                else if (symbol === sell_option_symbol || symbol === displayedOrderSymbols['sell']) {
                    // calculate a new spread price
                    let buy_bid, buy_ask;
                    if (creditSpreadStore.length > 0) { // credit spread store is storage updated everytime there si noew quote
                        buy_bid = creditSpreadStore[i]['buy_bid'];
                        buy_ask = creditSpreadStore[i]['buy_ask'];
                    }
                    else { // creditSpreadList is storage for the values when first queried
                        buy_bid = creditSpreadList[i]['buy']['bid']; // these values are from existing object stored
                        buy_ask = creditSpreadList[i]['buy']['ask'];
                    }
                    let buy_price = (buy_bid + buy_ask) / 2;
                    let sell_price = (bid + ask) / 2;
                    let cs_price = sell_price - buy_price;
                    if (symbol === sell_option_symbol) {
                        let pl = [...creditSpreadPriceList]; // copy first - mutating + setting the same ref makes React bail out
                        pl[i] = cs_price.toFixed(2);
                        SetCreditSpreadPriceList(pl)
                        // update creditSpreadStore with the newest values
                        let tmpBA = { 'buy_bid': buy_bid, 'buy_ask': buy_ask, 'sell_bid': bid, 'sell_ask': ask };
                        let tmpCSS = [...creditSpreadStore];
                        tmpCSS[i] = tmpBA;
                        SetCreditSpreadStore(tmpCSS);
                        if (i === selectedCreditSpread.current && !creditLock.current) {
                            // console.log('streaming 2 is updating credit', i, selectedCreditSpread.current, creditLock.current)
                            SetCredit(pl[selectedCreditSpread.current]);
                        }
                    }

                    if (symbol === displayedOrderSymbols['sell']) {
                        let tmpd = { ...displayedOrderSymbols }; //copying
                        tmpd['sell'] = buy_price;

                        SetDisplayedOrderPrice(tmpd)
                    }

                    break;
                }
            }
        }

    }
    //#################################################################################
    //-----------------------------------------------------------------------------
    // this is the ****QUOTES**** streaming useEffect
    //-----------------------------------------------------------------------------
    //#################################################################################
    // const abortController = new AbortController(); // Create an AbortController instance
    var socketQ = useRef(null);

    useEffect(() => {

        // marketOpen is a state variable set by fetching clock from the brokerage - its false when market closes
        // which is when we don't need streaming quotes 

        // props.switchStreamingQuotes is a switch turn streaming quotes on and off
        if (props.switchStreamingQuotes && marketOpen && streamingSymbols.length > 0) {


            const establishSession = async () => {

                const sessionResponse = await fetch('https://api.tradier.com/v1/markets/events/session', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${ACCESS_TOKEN_PROD}`,
                        'Content-Length': '0',
                        'Accept': 'application/json',
                    },
                });

                const sessionId = (await sessionResponse.json()).stream.sessionid;
                // console.log('Session ID:', sessionId);
                let symbols = streamingSymbols

                // console.log('hhhhhhhhhhhhhhhhhhhhhhh',streamingSymbols)
                // console.log('qqqqqqqqqqqqqqqqqqqqq',displayedPositionSymbols)

                if (displayedPositionSymbols.length > 0) {
                    symbols = symbols + ',' + displayedPositionSymbols
                }

                symbols = symbols.split(',');

                // PAYLOAD       = '{"symbols":  ["TSLA"], "filter": ["trade", "quote", "tradex"], "sessionid": "' + SESSION_ID + '", "linebreak": true, "validOnly": true}'
                let symbols_str = JSON.stringify(symbols);
                const PAYLOAD = '{"symbols": ' + symbols_str + ', "filter": ["trade", "quote", "tradex"], "sessionid": "' + sessionId + '", "linebreak": true, "validOnly": true}'

                // const PAYLOAD = `{"symbols": ${symbols} , "filter": ["trade", "quote", "tradex"], "sessionid": "${sessionId}", "linebreak": true, "validOnly": true}`
                // console.log('****************************** PAYLOAD=', PAYLOAD)

                socketQ.current = new WebSocket('wss://ws.tradier.com/v1/markets/events');


                // WebSocket event listeners
                socketQ.current.onopen = () => {
                    console.log('WebSocket connection opened for quotes');
                    // socketQ.current.send(JSON.stringify(symbolsPayload));
                    socketQ.current.send(PAYLOAD);
                    // if (socketQ.current.readyState === WebSocket.OPEN) {
                    //     socketQ.current.send(PAYLOAD);
                    // }
                };

                socketQ.current.onclose = (event) => {
                    console.log('WebSocket connection closed:', event.code, event.reason);
                };

                var last_update_time = 0;
                socketQ.current.onmessage = (event) => {
                    // console.log('WWWWWWWWWWWWWWWWWWWWWWWWWReceived message:', event.data); // Add this line to see the returned information from the server
                    let updateOrNot = false; // this is used to slow down the update to no more than 2 per second
                    const currentTimeInSeconds = parseInt(Math.floor(Date.now()));

                    if (parseInt((currentTimeInSeconds - last_update_time) / frequency_update) > 0) {
                        last_update_time = currentTimeInSeconds;
                        updateOrNot = true;
                    }

                    if (updateOrNot === true) {
                        process_streaming_line(event.data)
                    }

                    // console.log('Received message:', event.data);
                    // Handle incoming messages from the server
                    // process_streaming_line(event.data)
                };


            };

            establishSession();

            // Cleanup function: Abort the ongoing fetch operation when the component is unmounted
            return () => {
                console.log('Cleaning up: Aborting fetch operation.');
                if (socketQ.current) {
                    socketQ.current.close();
                }
            };

        }

    }, [streamingSymbols, selectedCreditSpread.current, creditLock.current, displayedPositionSymbols.length, tradePositions.length]);
    //#################################################################################
    //-----------------------------------------------------------------------------
    // this is the ****ACCOUNT**** streaming useEffect
    //-----------------------------------------------------------------------------
    //#################################################################################
    // const abortController = new AbortController(); // Create an AbortController instance
    var socketA = useRef(null);

    useEffect(() => {

        // marketOpen is a state variable set by fetching clock from the brokerage - its false when market closes
        // which is when we don't need streaming quotes 

        if (props.switchStreamingAccount) { // switch to turn streaming account on and off
            const establishSession = async () => {

                const sessionResponse = await fetch('https://sandbox.tradier.com/v1/accounts/events/session', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${ACCESS_TOKEN_SANDBOX}`,
                        'Content-Length': '0',
                        'Accept': 'application/json',
                    },
                });

                const sessionId = (await sessionResponse.json()).stream.sessionid;

                const account_payload = {
                    "events": ["order"],
                    "sessionid": sessionId,
                    "excludeAccounts": []
                }

                socketA.current = new WebSocket('wss://sandbox-ws.tradier.com/v1/accounts/events');


                // WebSocket event listeners
                socketA.current.onopen = () => {
                    // console.log('Account WebSocket connection opened');
                    // console.log('account_payload=', account_payload);

                    if (socketA.current.readyState === WebSocket.OPEN) {
                        socketA.current.send(JSON.stringify(account_payload));
                    } else {
                        if (showStreamingMessages) console.error('WebSocket connection is not open.');
                    }
                };


                socketA.current.onclose = (event) => {
                    if (showStreamingMessages) console.log('Account WebSocket connection closed:', event.code, event.reason);
                };

                var last_update_time = 0;
                socketA.current.onmessage = (event) => {
                    let return_Obj = JSON.parse(event.data)
                    if (return_Obj['event'] != 'heartbeat') {
                        console.log('account websocket received:', return_Obj)
                    }
                    if (return_Obj['event'] === 'order') {
                        console.log('refreshing orders in 2 seconds')
                        // wait 2 seconds and then refresh
                        const timeout = setTimeout(() => {
                            SetForceRefresh(true);
                        }, 2000);
                        refreshTimers.current.push(timeout); // track so an unmount can clear it
                    }
                };

            };

            establishSession();

            // Cleanup function: Abort the ongoing fetch operation when the component is unmounted
            return () => {
                if (showStreamingMessages) console.log('Cleaning up: Aborting fetch operation.');
                if (socketA.current) {
                    socketA.current.close();
                }
            };

        }

    }, [streamingSymbols, selectedCreditSpread.current, creditLock.current, displayedPositionSymbols.length, tradePositions.length]);
    //-------------------------------------------------------------------------------------------------------------------------------------
    // query for orders for this opportunity
    // this useEffect is run when first orders is queried and then when different orders are selected for viewing
    // when an existing order is being displayed, this useEffect does a fetch to get_quotes with the 2 option symbols
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        // only run it if there are orders for this opportunity

        // console.log('refreshing orders')

        let asURL = appserverURL()
        let url = `${asURL}/get_trade_orders?token=${token}`

        fetch(url)
            .then((res) => {
                return res.json();
            })
            .then((g) => {



                //- order ids are stored in the report dict for this opportunity  props.googleCalendarDict['order_id_list']
                let orderIdList = props.googleCalendarDict['order_id_list'];

                // orders
                let filtered_orders = g['orders'].filter(item => orderIdList.includes(item.id));
                SetTradeOrders(filtered_orders);

                // console.log('.........................g["orders"] returned:', filtered_orders)
                if (filtered_orders.length > 0) {
                    SetDisplayedOrderIndex(filtered_orders.length - 1) // set the displayedOrderIndex to the last order in the list because we want to display the last order placed initially
                }
                else {
                    SetDisplayedOrderIndex(0);
                }
                // set the position status for each position based on 
                // orders since position doesn't have a status field
                populatePositionStatus(filtered_orders);





            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
            })

        SetForceRefresh(false);

    }, [forceRefresh, props.googleCalendarDict['order_id_list'], displayedPositionIndex])
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this function sets th eposition status based on the orders
    //-------------------------------------------------------------------------------------------------------------------------------------
    const populatePositionStatus = (orders) => {

        // let status = [];
        // for (let i = 0; i < tradePositions.length; i++) {
        //     status.push('open');
        // }

        // for (let i = 0; i < orders.length; i++) {
        //     let o = orders[i];
        //     if (o['status'] === 'filled') {
        //         // let position_id = o['position_id'];
        //         // let position_index = tradePositions.findIndex(p => p['id'] === position_id);
        //         // if (position_index !== -1) {
        //         //     status[position_index] = 'closed';
        //         // }
        //     }
        // }
        // SetPositionStatus(status);

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // query for positions for this opportunity
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        let dr_id = props.googleCalendarDict['dr_id']
        let asURL = appserverURL()
        let url = `${asURL}/get_positions_for_dr_id/${dr_id}?token=${token}`

        fetch(url)
            .then((res) => {
                return res.json();
            })
            .then((g) => {

                // console.log('g["positions"] returned:', g['positions'])

                SetTradePositions(g['positions']);
                if (g['positions'].length > 0) {
                    SetDisplayedPositionIndex(g['positions'].length - 1); // set the position to the last position on the list if more than 1
                    // also set the SetDisplayedPositionSymbols for adding to the streaming symbols

                    let s0 = g['positions'].map(obj => obj['leg0']['symbol']).join(',');
                    let s1 = g['positions'].map(obj => obj['leg1']['symbol']).join(',');

                    SetDisplayedPositionSymbols(s0 + ',' + s1) // position symbols are used for streaming quotes


                    // set the cost per contract for the creditspread
                    let c0 = g['positions'][displayedPositionIndex]['leg0']['cost_basis'] / g['positions'][displayedPositionIndex]['leg0']['quantity'] / 100;
                    let c1 = g['positions'][displayedPositionIndex]['leg1']['cost_basis'] / g['positions'][displayedPositionIndex]['leg1']['quantity'] / 100;
                    SetDisplayedPositionCost(c0 - c1); // negative is a credit 

                    // console.log('postion cost =',c0-c1)

                    // set the qty of contracts for the displayed position
                    SetDisplayedPositionNumContracts(g['positions'][displayedPositionIndex]['leg0']['quantity']);


                    let custom_exit_fields = g['positions'][displayedPositionIndex]['custom_exit_fields']

                    console.log('ccccccccustom_eeeeeeeeeexit_fieldsssssssssss=', typeof (custom_exit_fields), custom_exit_fields)

                    SetExitStockGain(custom_exit_fields['exitStockGain'])
                    SetExitOptionGain(custom_exit_fields['exitOptionGain'])
                    SetDaysAfter(     custom_exit_fields['daysAfter'])
                    SetDaysAfterGain(custom_exit_fields['daysAfterGain'])
                    
                    SetWaveEndAction(custom_exit_fields['waveEndAction'])
                    SetEarlyExcerciseAction(custom_exit_fields['earlyExcerciseAction'])
                    SetDaysBefore(custom_exit_fields['daysBefore'])


                    
                }

            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
            })

        SetForceRefresh(false);

    }, [forceRefresh])
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useEffect retrieves the option quotes for the displaying ORDER 
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        // only run it if there are orders for this opportunity
        // console.log('-------------------', tradeOrders[0])

        if (tradeOrders.length > 0) {


            let o = tradeOrders[displayedOrderIndex];

            let option_symbol0 = o['leg'][0]['option_symbol'];
            let option_symbol1 = o['leg'][1]['option_symbol'];
            let symbols = `${option_symbol0},${option_symbol1}`
            let asURL = appserverURL()
            let url = `${asURL}/get_quotes_brokerage/${symbols}?token=${token}`

            fetch(url)
                .then((res) => {
                    return res.json();
                })
                .then((g) => {
                    // console.log('get quote returned', g)
                    // description of the credit spread by legs 0 and 1
                    let desc0 = o['leg'][0]['side'].replaceAll('_', ' ') + ` (${o['leg'][0]['quantity']}) ` + g['quotes'][0]['description']
                    let desc1 = o['leg'][1]['side'].replaceAll('_', ' ') + ` (${o['leg'][1]['quantity']}) ` + g['quotes'][1]['description']

                    SetDisplayedOrder({ row0: desc0, row1: desc1 });
                    let key0 = o['leg'][0]['side'].includes('buy') ? 'buy' : 'sell';
                    let key1 = o['leg'][1]['side'].includes('buy') ? 'buy' : 'sell';

                    let orderSymbols = { [key0]: o['leg'][0]['option_symbol'], [key1]: o['leg'][1]['option_symbol'] }
                    SetDisplayedOrderSymbols(orderSymbols)

                    let side0 = o['leg'][0]['side'], bid0 = o['leg'][0]['bid'], ask0 = o['leg'][0]['ask'];
                    let side1 = o['leg'][1]['side'], bid1 = o['leg'][1]['bid'], ask1 = o['leg'][1]['ask'];

                    let price0 = (bid0 + ask0) / 2;  //mark price
                    let price1 = (bid1 + ask1) / 2;  //mark price

                    let cs_price = side0.includes('buy') ? price1 - price0 : price0 - price1;


                    // SetDisplayedOrderPrice({ buy: 0, sell: 0, price: cs_price });

                })
                .catch(err => {
                    console.log('getResourcesObj error=', err.message)
                })
        }

    }, [displayedOrderIndex, tradeOrders.length])
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useEffect retrieves the option quotes for the displaying POSITION - not streaming 
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        // only run it if there are orders for this opportunity
        // console.log('-------------------', tradeOrders[0])

        if (tradePositions.length > 0) {


            let o = tradePositions[displayedPositionIndex];


            SetSelectedExitContractNumber(o['leg0']['quantity']); // initially all contracts are set by default for exit order


            let option_symbol0 = o['leg0']['symbol'];
            let option_symbol1 = o['leg1']['symbol'];

            // prefix is for putting a long or short and num contracts before the option description
            // removing quantity here because its dynamic by the exit dialog pull down 6/14/2024
            // let prefix0 = `long (${o['leg0']['quantity']}) `
            // let prefix1 = `short (${Math.abs(o['leg1']['quantity'])}) `
            let prefix0 = `long (**) `
            let prefix1 = `short (**) ` // ** is used to replace with contract number 

            let symbols = `${option_symbol0},${option_symbol1}`
            let asURL = appserverURL()
            let url = `${asURL}/get_quotes_brokerage/${symbols}?token=${token}`

            fetch(url)
                .then((res) => {
                    return res.json();
                })
                .then((g) => {

                    // console.log('gggggggggggggggggggggg=', g)

                    // description of the credit spread by legs 0 and 1
                    let desc0 = prefix0 + g['quotes'][0]['description']
                    let desc1 = prefix1 + g['quotes'][1]['description']

                    SetDisplayedPosition({ row0: desc0, row1: desc1 });
                    let long_bid = g['quotes'][0]['bid']
                    let long_ask = g['quotes'][0]['ask']
                    let short_bid = g['quotes'][1]['bid']
                    let short_ask = g['quotes'][1]['ask']

                    let tmp_dict = { 'long': (long_bid + long_ask) / 2, 'short': (short_bid + short_ask) / 2 };
                    SetDisplayedPositionPrice(tmp_dict);

                    let spread = g['quotes'][1]['strike'] - g['quotes'][0]['strike'];
                    SetDisplayedPositionSpread(spread);

                    //now set the SetDisplayedPositionGainLoss based on initial option quotes for the position
                    let position_cost = displayedPositionCost;

                    let position_value = -tmp_dict['short'] + tmp_dict['long'];

                    // console.log('------------X--------------position_value=', position_value)

                    let positionContracts = displayedPositionNumContracts; // just did this state variable 1/29/2024
                    // positionContracts = 2

                    let risk_capital = spread + position_cost; // position_cost should be negative due to credit
                    // console.log('------------X--------------risk_capital=', risk_capital)
                    let gain_loss = -position_cost + position_value;
                    // console.log('------------X--------------gain_loss=', gain_loss,risk_capital)

                    let pct_gain_loss = ((100 * gain_loss / risk_capital).toFixed(0));

                    // console.log('------------X--------------position_value=',gain_loss,risk_capital)
                    // console.log(displayedPosition)

                    SetDisplayedPositionGainLoss(pct_gain_loss); // not streaming

                    // SetDisplayedPositionToolTip(
                    //     `${displayedPositionNumContracts} contracts \n 
                    //     ${displayedPositionSpread} spread, \n
                    //     ${displayedPositionCost} credit, \n
                    //     $${gain_loss}${gain_loss > 0 ? 'Profit' : 'Loss'},\n
                    //     ${pct_gain_loss}${pct_gain_loss > 0 ? 'Profit' : 'Loss'} ,\n
                    //     ${risk_capital} Risk Capital
                    //     `
                    // )


                    //----------------------------------------------------------------------------------
                    // this is the writeup for the tooltip over the position P&L
                    //----------------------------------------------------------------------------------

                    const investmentDetails = (
                        <div style={{ borderRadius: '20px', backgroundColor: 'black', color: 'linen', display: 'flex', flexWrap: 'wrap', height: '100px', width: '200px', fontFamily: 'sans-serif', fontSize: '0.8vw', paddingTop: '8px', paddingBottom: '6px' }}>

                            <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'right', width: '50%', height: `33.33%`, backgroundColor: 'transparent' }}>
                                Risk Capital
                            </div>
                            <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '50%', height: `33.33%`, backgroundColor: 'transparent' }}>
                                ${(positionContracts * 100 * risk_capital).toFixed(0)}
                            </div>


                            <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'right', width: '50%', height: `33.33%`, backgroundColor: 'transparent' }}>
                                Position P&L
                            </div>
                            <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '50%', height: `33.33%`, backgroundColor: 'transparent' }}>
                                <span style={{ backgroundColor: gain_loss >= 0 ? 'green' : 'red', paddingRight: '5px', paddingLeft: '5px' }}>
                                    ${(100 * positionContracts * gain_loss).toFixed(0)}
                                </span>
                            </div>


                            <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'right', width: '50%', height: `33.33%`, backgroundColor: 'transparent' }}>
                                Initial Credit
                            </div>
                            <div style={{ padding: '2px', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '50%', height: `33.33%`, backgroundColor: 'transparent' }}>
                                ${(-100 * positionContracts * position_cost).toFixed(0)}
                            </div>





                        </div>
                    );

                    SetDisplayedPositionToolTip(investmentDetails);






                })
                .catch(err => {
                    console.log('getResourcesObj error=', err.message)
                })
        }

    }, [displayedPositionIndex, tradePositions.length, displayedPositionCost, displayedPositionNumContracts])
    //-------------------------------------------------------------------------------------------------------------
    // this useEffect is to retrieve the custom exit order for the current displayed position from live_trades
    //-------------------------------------------------------------------------------------------------------------
    useEffect(() => {

        //here

    }, [])
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
    // dynamically updates credit and traderiskcapital when lock on credit is off
    //-----------------------------------------------------------------------------
    useEffect(() => {
        if (!creditLock.current) {

            SetCredit(creditSpreadPriceList[selectedCreditSpread.current]);

            let risk_per_cont = (spreadPrice - creditSpreadPriceList[selectedCreditSpread.current]) * 100;
            let trade_total_risk = numContracts * risk_per_cont;
            if (Number.isNaN(trade_total_risk) === false) {
                SetTradeRiskCapital(trade_total_risk);
            }
        }
    }, [...creditSpreadPriceList, selectedCreditSpread.current, creditSpreadPriceList[selectedCreditSpread.current]]);
    //-----------------------------------------------------------------------------
    // event triggered when user selects a different creditspread
    //-----------------------------------------------------------------------------
    const checkboxChanged = (index) => {

        let tmp = [];

        for (let i = 0; i < checkboxSelectionList.length; i++) {
            if (i === index) {
                tmp.push(true);
                selectedCreditSpread.current = i;
            }
            else tmp.push(false);
        }

        // console.log('numcontracts=', numContracts)
        // console.log('buy', creditSpreadList[selectedCreditSpread]['buy']['description'], creditSpreadList[selectedCreditSpread]['buy']['symbol']);
        // console.log('sell', creditSpreadList[selectedCreditSpread]['sell']['description'], creditSpreadList[selectedCreditSpread]['sell']['symbol']);

        SetCheckboxSelectionList(tmp);
        // calculate number of contracts and total risk capital for creditspread [index]
        let tmpcredit = creditSpreadPriceList[index];
        let sell_strike = creditSpreadList[index]['sell']['strike'];
        let buy_strike = creditSpreadList[index]['buy']['strike'];
        let spread = Math.abs(sell_strike - buy_strike);
        SetSpreadPrice(spread)

        let risk_per_cont = Math.abs(spread - tmpcredit) * 100; // 100 shares per contract
        let per_trade_cap = perTradeCapital[1]
        let total_capital = perTradeCapital[0]
        let num_contracts;
        if (perTradeCapital[1] > 0) num_contracts = parseInt(per_trade_cap / risk_per_cont);
        else num_contracts = 1;
        let trade_risk = num_contracts * risk_per_cont

        // console.log('-----------',per_trade_cap,risk_per_cont)

        SetPerTradeCapital([total_capital, per_trade_cap, num_contracts, trade_risk])
        SetNumContracts(num_contracts)
        SetCredit(tmpcredit)
        SetTradeRiskCapital(trade_risk);
        creditLock.current = false;

    }
    //-----------------------------------------------------------------------------
    // when a different option expiration is selected this event runs
    //-----------------------------------------------------------------------------
    const handleExpirationClicked = (idx) => {
        selectedExpiration.current = idx;
        creditLock.current = false;
        SetForceRefresh(true); // force refresh here because for selectedExpiration I switched to reference because of streaming loop not seeing changes
    }
    //-----------------------------------------------------------------------------------------------
    // when place order on the trade dialog is pressed, a confirmation dialog is first displayed
    //-----------------------------------------------------------------------------------------------
    const handlePlaceOrder = () => {

        // guard - an empty creditSpreadList (auto_selection returned the [-1,-1] "none found"
        // sentinel) means there is nothing to index; bail so we don't crash on an empty array
        if (creditSpreadList.length === 0) return;

        let content;

        content = { // confirmation dialog box content
            'line1': ``,
            'line1j': 'center',
            'line2': `Buy (${numContracts}) ${creditSpreadList[selectedCreditSpread.current]['buy']['description']}`,
            'line2j': 'center',
            'line3': `Sell (${numContracts}) ${creditSpreadList[selectedCreditSpread.current]['sell']['description']}`,
            'line3j': 'center',
            'line4j': '',
            'line4': '',
            'line5': `Credit: $${credit} per contract`,
            'line5j': 'center',
            'line6': numContracts > 1
                ? `Risk / Contract: $${(tradeRiskCapital / numContracts).toFixed(0)} - Total Risk: $${tradeRiskCapital.toLocaleString()}`
                : `Total Risk: $${tradeRiskCapital.toLocaleString()}`,
            'line6j': 'center',
            'line7': `Available Capital After: $${(perTradeCapital[0] - tradeRiskCapital).toLocaleString()}`,
            'line7j': 'center'
        }


        props.SetDialogProp({ title: 'Place Order', contentText: content, button1Text: 'Cancel', button2Text: 'Place Order', coverDivColor: 'rgb(222,222,222,0)', placeCreditspreadTrade: placeNewCreditspreadTrade })
        props.SetDialogType('info-box');
        props.SetInfoBoxVisible(true);
    }
    //-----------------------------------------------------------------------------
    // Function to send buy & sell credit spread trades to backend - need data Obj
    //-----------------------------------------------------------------------------
    const SendCSTrade = (data) => {
        // console.log('data=', data)
        let asURL = appserverURL()
        let url = `${asURL}/place_creditspread_order?token=${token}`
        // console.log('url=', url)
        // console.log('SSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSendCSTrade')

        // post  the order data to the appserver
        fetch(url, {
            method: 'POST', // Specify the HTTP method
            headers: {
                'Content-Type': 'application/json',
            },
            // Add the request body if you have data to send
            body: JSON.stringify(data),
        })

            .then((res) => {
                if (!res.ok) {
                    throw new Error('server responded ' + res.status); // surface HTTP errors instead of parsing an error page as JSON
                }
                return res.json();
            })

            .then((g) => {

                // console.log('^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ after exit order return = ', g)

                if (g['order_status'] === 'error') {
                    console.log('error in placing order');

                    props.SetDialogProp({ title: 'Error Placing Order', contentText: g['message'], button1Text: 'Close', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                    props.SetDialogType('info-box');
                    props.SetInfoBoxVisible(true)

                }
                else {
                    let new_order_id = g['order_id']
                    let order_list = props.googleCalendarDict['order_id_list'];
                    let order_list_length = order_list.length;
                    order_list.push(new_order_id);  // add it to the order_list so it doesn't have to be reloaded 
                    let tmpObj = { ...props.googleCalendarDict }; // make a copy
                    tmpObj['order_id_list'] = order_list;
                    props.SetGoogleCalendarDict(tmpObj); // and update googleCalendarDict that is being reused for TradeInstrument

                    // if order_list_length was 0 and this is the first order, reload the reports_list so that it can change the color of 
                    // the airplane to orange
                    if (order_list_length === 0) {
                        props.SetReportsList([]);
                    }

                    // wait 2 seconds and then refresh - try without this - I don't think I need it
                    const timeout = setTimeout(() => {
                        SetForceRefresh(true);
                    }, 2000);
                    refreshTimers.current.push(timeout); // track so an unmount can clear it

                }

            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
                // the order POST failed or returned a non-JSON error page - the trade may or may not
                // have reached the broker, so warn the trader instead of failing silently
                props.SetDialogProp({ title: 'Error Placing Order', contentText: 'Order failed or its status is unknown - please check your broker account before retrying.', button1Text: 'Close', button2Text: '', coverDivColor: 'rgb(222,222,222,0)' })
                props.SetDialogType('info-box');
                props.SetInfoBoxVisible(true)
            })
    }
    //-----------------------------------------------------------------------------
    // Create a new credit spread sell order to open a position
    // triggered when a credit spread is selected on the list of availabe CS
    // then when its confirmed in the dialog box, runs this function
    //-----------------------------------------------------------------------------
    const placeNewCreditspreadTrade = () => {

        // console.log('placeNewCreditspreadTrade from dialog bog button click')
        console.log('xxxxxxxxxxxxxx',typeof(credit),credit)
        let cs = creditSpreadList[selectedCreditSpread.current];

        // create the place order dictionary 
        let data = {
            'class': 'multileg',
            'symbol': props.googleCalendarDict['ticker'],
            'type': 'credit',
            'duration': 'day',
            'price': credit,
            'option_symbol[0]': cs['buy']['symbol'],
            'side[0]': 'buy_to_open',
            'quantity[0]': numContracts.toString(),
            'option_symbol[1]': cs['sell']['symbol'],
            'side[1]': 'sell_to_open',
            'quantity[1]': numContracts.toString(),
            'dr_id': props.googleCalendarDict['dr_id']  // this is report id used to store info about this opportunity
        }
        SendCSTrade(data);
    }
    //-----------------------------------------------------------------------------
    // Enters an exit credit spread order
    // triggered when exit icon on POSITIONs is pressed - updated and confirmed
    // this 2 funcs are here because I couldn't pass type-I made 2 different funcs
    //-----------------------------------------------------------------------------
    const placeExitCreditspreadMarket = () => {
        placeExitCreditspreadTrade('market');
    }
    //-----------------------------------------------------------------------------
    const placeExitCreditspreadConditional = () => {
        placeExitCreditspreadTrade('full-exit-order');
    }
    //#############################################################################
    //-----------------------------------------------------------------------------
    // this is where basic and conditional exit orders are placed
    // invoked after exit is confirmed on the dialog box of the "Custom Exit Order"
    //-----------------------------------------------------------------------------
    //#############################################################################
    const placeExitCreditspreadTrade = (type) => {


        // let cs = creditSpreadList[selectedCreditSpread.current];
        // exit order is for the displayed Position in the light green box
        let cs = tradePositions[displayedPositionIndex];

        // console.log('full exit order is invoked and dialog box is confirmed - cs=', cs)


        // selectedExitContractNumber  // this is the number of contracts selected, couple all contracts or partial
        // displayedPosition  // this is the postion that is displayed
        // displayedPositionIndex 

        // tradePositions 
        // exitStockGain 
        // exitStockLoss // removed it - it doesn't make sense
        // exitOptionGain 
        // exitOptionLoss // removed it - it doesn't make sense
        // daysAfter = { daysAfter }
        // daysAfterGain = { daysAfterGain }
        // daysBefore = { daysBefore }
        // waveEndAction
        // earlyExcerciseAction

        // SetDaysAfter
        // SetDaysAfterGain
        // SetDaysBefore
        // SetEarlyExcerciseAction
        // SetExitOptionGain
        // SetExitStockGain
        // SetEarlyExcerciseAction


        // let custom_exit_fields = {
        //     'exit_after_days': daysAfter,
        //     'exit_after_days_option_gain':daysAfterGain,
        //     'exit_before_expiration_days':daysBefore,
        //     'exit_early_excercise':earlyExcerciseAction,
        //     'exit_option_profit':exitOptionGain,
        //     'exit_stock_profit':exitStockGain,
        //     'exit_wave_end':waveEndAction
        // }

        // update_live_trades(custom_exit_fields)


        // console.log('positions=', tradePositions)
        // console.log('displayedPositionCost', displayedPositionCost)
        // console.log('displayedPositionSpread=', displayedPositionSpread)

        // position cost to achieve the desired % gain: exitOptionGain
        let risk_capital = displayedPositionSpread + displayedPositionCost // displayedPositionCost is negative because of credit
        let gain_capital = risk_capital * exitOptionGain / 100;
        let price = displayedPositionCost + gain_capital; // if stock has risen, price is smaller than displayedPositionCost by gain
        price = -price; // to close we switch credit(negative) to debit(positive)  
        // console.log('exitOptionGain=', exitOptionGain)

        // return // fix here

        let exitType = 'debit'; // typical type 

        if (type === 'market') {
            exitType = 'market';
            price = 0; // market order doesn't need a price
        }
        // create the place order dictionary 
        let data = {
            'class': 'multileg',
            'symbol': props.googleCalendarDict['ticker'],
            'type': exitType, // market, debit, credit, even
            'duration': 'gtc',
            'price': price.toFixed(2),
            'option_symbol[0]': cs['leg0']['symbol'],
            'side[0]': 'sell_to_close',
            'quantity[0]': selectedExitContractNumber.toString(),
            'option_symbol[1]': cs['leg1']['symbol'],
            'side[1]': 'buy_to_close',
            'quantity[1]': selectedExitContractNumber.toString(),

            // add all the conditional info needed



            'dr_id': props.googleCalendarDict['dr_id']  // this is report id used to store info about this opportunity
        }

        if (type !== 'market') { // add the conidtional parameters
            data['exitStockGain'] = exitStockGain || 0; // || 0 sets variable to 0 when a empty string is returned
            data['exitOptionGain'] = exitOptionGain || 0;
            data['daysAfter'] = daysAfter || 0;
            data['daysAfterGain'] = daysAfterGain || 0;
            data['daysBefore'] = daysBefore || 0;
            data['waveEndAction'] = waveEndAction;
            data['earlyExcerciseAction'] = earlyExcerciseAction;
        }



        console.log('exit data = ', data)
        SendCSTrade(data);

    }
    //#############################################################################
    //-------------------------------------------------------------------------------------------------------
    // update live_trades with new conditional exit parameters for the display position by dr_id
    //-------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------
    // this function advances the displayed order when clicking the right or left triangles over the order
    // inc can be a positive or a negative number - changing displayedOrderIndex
    //-------------------------------------------------------------------------------------------------------
    const handleAdvanceOrder = (inc) => {

        let tmp_index = displayedOrderIndex + inc;

        if (tmp_index > tradeOrders.length - 1) {
            tmp_index = 0;
        }
        else if (tmp_index < 0) {
            tmp_index = tradeOrders.length - 1;
        }
        SetDisplayedOrderIndex(tmp_index);
    }
    //-----------------------------------------------------------------------------
    // this function advances the displayed position 
    // inc can be a positive or a negative number - changing displayedPositionIndex
    //-----------------------------------------------------------------------------
    const handleAdvancePosition = (inc) => {

        let tmp_index = displayedPositionIndex + inc;

        if (tmp_index > tradePositions.length - 1) {
            tmp_index = 0;
        }
        else if (tmp_index < 0) {
            tmp_index = tradePositions.length - 1;
        }
        SetDisplayedPositionIndex(tmp_index);
    }
    //-----------------------------------------------------------------------------
    // user has changed onne of the textboxes in the trade dialog
    //-----------------------------------------------------------------------------
    const handleBlur = (event) => {

        let val = event.target.value;

        // solve for risk per contract - because I didn't save it anywhere so I have to calculate it

        if (event.target.id === 'num_option_contracts') {
            SetNumContracts(val)

            let sell_strike = creditSpreadList[selectedCreditSpread.current]['sell']['strike'];
            let buy_strike = creditSpreadList[selectedCreditSpread.current]['buy']['strike'];
            let spread = Math.abs(sell_strike - buy_strike);
            SetSpreadPrice(spread)

            let risk_per_cont = (spread - credit) * 100; // 100 shares per contract

            let trade_total_risk = val * risk_per_cont
            SetTradeRiskCapital(trade_total_risk);
        }

        if (event.target.id === 'credit') {

            let sell_strike = creditSpreadList[selectedCreditSpread.current]['sell']['strike'];
            let buy_strike = creditSpreadList[selectedCreditSpread.current]['buy']['strike'];
            let spread = sell_strike - buy_strike;
            SetSpreadPrice(spread)

            let risk_per_cont = (spread - val) * 100; // 100 shares per contract

            if (val > spread) val = spread - 0.1;  // keep the original credit subtract 10 cents - cannot get more credit than the spread

            SetCredit(val)
            let trade_total_risk = numContracts * risk_per_cont
            SetTradeRiskCapital(trade_total_risk);

        }

        if (event.target.id === 'auto_exit_gain_pct') {
            let tmp = val;

            if (!val.includes('%')) tmp = tmp + '%';
            SetExitStockGain(tmp)
        }

    }
    //-----------------------------------------------------------------------------
    // if user selects a different expiration and or creditspread from the default
    // they can press the auto select button and get back to the default selection
    //-----------------------------------------------------------------------------
    const handleAutoSelection = (event) => {

        // autoselection is stored in var autoSelection
        selectedExpiration.current = autoSelection[0];

        let tmp = [];
        for (let i = 0; i < checkboxSelectionList.length; i++) {
            if (i === autoSelection[1]) {
                tmp.push(true);
                selectedCreditSpread.current = i;
            }
            else tmp.push(false);
        }
        SetCheckboxSelectionList(tmp);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const toggleLock = () => {
        let tmpB = !creditLock.current;
        creditLock.current = tmpB;

        if (!creditLock.current) {
            SetCredit(creditSpreadPriceList[selectedCreditSpread.current]);
        }
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this is run by clicking X to cancel an order in the UI on the bottom left window
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleCancelOrderConfirm = () => {

        let content;

        const contentArray = [

            <div key="line2">Canceling the order:</div>,
            <div key="line1">&nbsp;</div>,
            <div key="line3">{displayedOrder['row0']}</div>,
            <div key="line4">{displayedOrder['row1']}</div>,

        ];

        props.SetDialogProp({ title: 'Cancel Order', contentText: contentArray, button1Text: 'Close', button2Text: 'Cancel Order', coverDivColor: 'rgb(222,222,222,0)', CancelOrder: CancelOrder })
        props.SetDialogType('info-box');
        props.SetInfoBoxVisible(true)

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // handles turning the display of Exit Order dialog on and off
    //-------------------------------------------------------------------------------------------------------------------------------------
    function toggleExitDialog() {
        if (!dialogRef.current) {
            return; // in case it wasn't there
        }
        dialogRef.current.hasAttribute('open')
            ? dialogRef.current.close()
            : dialogRef.current.showModal();
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this is run by clicking X to cancel an order in the UI on the bottom left window
    //-------------------------------------------------------------------------------------------------------------------------------------
    const CancelOrder = () => {

        // console.log('this is the one to cancel = ', tradeOrders[displayedOrderIndex]);

        let order_id = tradeOrders[displayedOrderIndex]['id'];

        // console.log('----------------------------------------order_id=', order_id)

        let asURL = appserverURL()
        let url = `${asURL}/cancel_placed_order?token=${token}`;

        fetch(url, {
            method: 'POST', // Specify the HTTP method
            headers: {
                'Content-Type': 'application/json',
            },
            // Add the request body if you have data to send
            body: JSON.stringify({ 'order_id': order_id }),
        })

            .then((res) => {
                if (!res.ok) {
                    throw new Error('server responded ' + res.status); // surface HTTP errors instead of parsing an error page as JSON
                }
                return res.json();
            })

            .then((g) => {

                // console.log('returned=', g)


                // wait 2 seconds and then refresh
                const timeout = setTimeout(() => {
                    SetForceRefresh(true);
                }, 2000);
                refreshTimers.current.push(timeout); // track so an unmount can clear it

            })
            .catch(err => {
                console.log('getResourcesObj error=', err.message)
                // the cancel POST failed or returned a non-JSON error page - warn the trader instead of
                // failing silently, since the order may still be live at the broker
                props.SetDialogProp({ title: 'Error Canceling Order', contentText: 'Cancel failed or its status is unknown - please check your broker account.', button1Text: 'Close', button2Text: '', coverDivColor: 'rgb(222,222,222,0)', onButton1: () => { } })
                props.SetDialogType('info-box');
                props.SetInfoBoxVisible(true)
            })


    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // This envokes the exit trade confirmation dialog - the actual functions to exit are placeExitCreditspreadMarket, placeExitCreditspreadConditional
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleCreateExitOrder = (type) => {

        let content = `order type ${type} is not supported`; // in case a weird type is added otherwise, this message is replaced

        // exit variables
        // let num_contracts = selectedExitContractNumber
        // let stock_profit = exitStockGain
        // let stock_loss = exitStockLoss
        // let options_profit = exitOptionGain
        // let options_loss = exitOptionLoss
        // let after_days = daysAfter
        // let after_gain = daysAfterGain
        // let expire_exit_days = daysBefore
        // let order_type = type                // its either 'market' or 'full-exit-order'



        let title = ''; // title of confirmation dialog

        if (type === 'market') {
            content = [
                <div key="line1">Place a Market Order to Sell the Position</div>,
            ];
            props.SetDialogProp({ title: 'Place Market Exit Order', contentText: content, button1Text: 'Close', button2Text: 'Place Exit Order', coverDivColor: 'rgb(222,222,222,0)', ExecuteFuncAfterConfirmation: placeExitCreditspreadMarket })
        }
        else if (type === 'full-exit-order') {
            content = [
                <div key="line1">Place Conditional Exit Orders</div>,
            ];
            props.SetDialogProp({ title: 'Place Conditional Exit Orders', contentText: content, button1Text: 'Close', button2Text: 'Place Exit Order', coverDivColor: 'rgb(222,222,222,0)', ExecuteFuncAfterConfirmation: placeExitCreditspreadConditional })
        }

        props.SetDialogType('info-box');
        props.SetInfoBoxVisible(true)

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div className="dialog-GC" style={AddGC_style}   >


            <div style={{ width: '100%', height: '100%', backgroundColor: 'rgb(225,242,242', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>

                <div className="add-gc-div-top-rows" style={{ backgroundColor: 'dimgray', height: title_height, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    {/* below div color should be either lightgray or gray.  displays dr_id on the top left corner of the  TradeInsrtruments.js  */}
                    <div style={{ width: title_close_width, height: '100%', backgroundColor: 'transparent', color: 'lightgray', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                        {props.googleCalendarDict['dr_id']} &nbsp;&nbsp; {props.googleCalendarDict['order_id_list'].length}
                    </div>
                    <div style={{ width: title_width, display: 'flex', justifyContent: 'center', alignItems: 'center', backgroundColor: 'transparent' }}>
                        <span style={{ color: 'white', fontSize: textFontSize }}>{props.googleCalendarDict['direction'] === 'long' ? 'Long' : 'Short'}&nbsp;&nbsp;</span>


                        <div style={{ width: '1em', height: '1em', backgroundColor: props.googleCalendarDict['direction'] === 'long' ? 'green' : 'red', marginRight: '0.5em' }}> </div>
                        {!rdd.isMobile &&
                            <span style={{ color: 'white', fontSize: textFontSize }}>Trade </span>
                        }
                        <span style={{ color: 'black', fontWeight: 'bold', fontSize: textFontSize }}>&nbsp;&nbsp;{props.googleCalendarDict['ticker']}</span>
                        <span style={{ backgroundColor: 'black', color: 'white', marginLeft: '5px', paddingLeft: '5px', paddingRight: '5px', paddingBottom: '1px', marginRight: '5px' }}>
                            {props.googleCalendarDict['date1']}
                        </span>
                        <span style={{ color: 'white' }}>&nbsp;TO&nbsp;</span>
                        <span style={{ backgroundColor: 'black', color: 'white', marginLeft: '5px', paddingLeft: '5px', paddingRight: '5px', paddingBottom: '1px' }}>
                            {props.googleCalendarDict['date2']}
                        </span>

                    </div>
                    <div style={{ width: title_close_width, height: '100%', backgroundColor: 'lightgray', display: 'flex', justifyContent: 'center', alignItems: 'center', borderBottom: '1px solid gray' }} onClick={() => props.SetAddGCVisible(false)} ><GrClose size={closeIconSize} style={{ fill: 'white' }} /></div>
                </div>

                <div style={{ backgroundColor: 'transparent', width: '100%', height: body_height, display: 'flex', flexDirection: flexDirection }}>

                    {/* left side column */}
                    <div style={{ width: column_width, height: '100%', backgroundColor: 'transparent', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ paddingLeft: '10px', width: '100%', height: '12%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'left' }}>

                            <div style={{ backgroundColor: 'transparent', width: '30%', display: 'flex', alignItems: 'center', justifyContent: 'left', flexDirection: 'row' }}>
                                <div style={{ width: '40%', height: '100%', fontSize: textFontSize, backgroundColor: 'transparent', fontWeight: 'bold', display: 'flex', justifyContent: 'left' }}>{props.googleCalendarDict['ticker']} </div> {/* Price: */}
                                <div style={{ width: '50%', height: '100%', fontSize: textFontSize, backgroundColor: stockPriceBackgroundColor, color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>${stockPrice}</div>
                            </div>
                            {availableExpirationDates.length === 2 &&
                                <div style={{ backgroundColor: 'transparent', width: '70%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <span style={{ fontSize: textFontSize, paddingLeft: '1em', paddingRight: '1em', backgroundColor: selectedExpiration.current === 0 ? 'black' : 'transparent', color: selectedExpiration.current === 0 ? 'white' : 'black', border: '1px solid gray' }} onClick={() => handleExpirationClicked(0)}>{availableExpirationDates[0]} ({daysBetweenDates(getTodayDate(), availableExpirationDates[0])})</span>
                                    &nbsp;&nbsp;
                                    <span style={{ fontSize: textFontSize, paddingLeft: '1em', paddingRight: '1em', backgroundColor: selectedExpiration.current === 1 ? 'black' : 'transparent', color: selectedExpiration.current === 1 ? 'white' : 'black', border: '1px solid gray' }} onClick={() => handleExpirationClicked(1)} >{availableExpirationDates[1]} ({daysBetweenDates(getTodayDate(), availableExpirationDates[1])})</span>
                                </div>
                            },
                        </div>

                        <div style={{ borderBottom: '1px solid black', width: '100%', height: '0.01%' }}></div>


                        <div style={{ width: '100%', height: '54%', backgroundColor: creditSpreadListBackgroundColor }}>

                            {creditSpreadList.length > 0 &&
                                creditSpreadList.map((spread, index) => (
                                    <div key={index} style={{ borderBottom: '1px solid black', width: '100%', height: rowHeight, backgroundColor: 'transparent', display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center' }} onClick={() => checkboxChanged(index)}>
                                        <div style={{ width: CSW[0], height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                                            <CheckBox checked={checkboxSelectionList[index]} cbChanged={() => checkboxChanged(index)} />
                                        </div>
                                        <div style={{ width: CSW[1], height: '100%', backgroundColor: 'transparent' }}>
                                            <div style={{ width: '100%', height: '50%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center' }}>
                                                <span style={{ color: 'black', fontSize: textFontSize }}>Buy {spread['buy']['description']} - OI: {spread['buy']['open_interest']} </span>
                                            </div>
                                            <div style={{ width: '100%', height: '50%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center' }}>
                                                <span style={{ color: 'black', fontSize: textFontSize }}>Sell {spread['sell']['description']} - OI: {spread['sell']['open_interest']} </span>
                                            </div>
                                        </div>
                                        <div style={{ width: CSW[2], height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                                            <span style={{ fontSize: textFontSize, fontWeight: 'bold' }}>${creditSpreadPriceList[index]} <span style={{ fontWeight: 'normal' }}> {word_credit}</span></span>
                                        </div>
                                    </div>
                                ))

                            }



                        </div>


                        <div style={{ width: '100%', height: '35%', backgroundColor: 'transparent', display: 'flex', flexDirection: 'column' }}>

                            <div style={{ width: '100%', height: '50%', backgroundColor: 'transparent', display: 'flex', flexDirection: 'column' }}>

                                <ExitOrderDialog
                                    dialogRef={dialogRef}
                                    // maxNumber={tradePositions[displayedPositionIndex]['leg0']['quantity']}

                                    setSelectedNumber={SetSelectedExitContractNumber}
                                    displayedPosition={displayedPosition}
                                    displayedPositionIndex={displayedPositionIndex}
                                    SetSelectedExitContractNumber={SetSelectedExitContractNumber}
                                    selectedExitContractNumber={selectedExitContractNumber}
                                    toggleExitDialog={toggleExitDialog}
                                    tradePositions={tradePositions}
                                    exitStockGain={exitStockGain}
                                    SetExitStockGain={SetExitStockGain}
                                    exitStockLoss={exitStockLoss}
                                    SetExitStockLoss={SetExitStockLoss}
                                    exitOptionGain={exitOptionGain}
                                    SetExitOptionGain={SetExitOptionGain}
                                    exitOptionLoss={exitOptionLoss}
                                    SetExitOptionLoss={SetExitOptionLoss}
                                    daysAfter={daysAfter}
                                    SetDaysAfter={SetDaysAfter}
                                    daysBefore={daysBefore}
                                    SetDaysBefore={SetDaysBefore}
                                    daysAfterGain={daysAfterGain}
                                    SetDaysAfterGain={SetDaysAfterGain}
                                    handleCreateExitOrder={handleCreateExitOrder}

                                    waveEndActionsList={waveEndActionsList}
                                    waveEndAction={waveEndAction}
                                    SetWaveEndAction={SetWaveEndAction}

                                    earlyExcerciseActionsList={earlyExcerciseActionsList}
                                    earlyExcerciseAction={earlyExcerciseAction}
                                    SetEarlyExcerciseAction={SetEarlyExcerciseAction}
                                />

                                <div style={{ width: '100%', height: '26%', backgroundColor: 'gray', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>

                                    <div style={{ width: '70%', height: '100%', backgroundColor: 'transparent', paddingLeft: '3px', fontSize: '1em', fontWeight: 'bold', display: 'flex', justifyContent: 'left', alignItems: 'center', color: 'white' }}>

                                        <span style={{ paddingLeft: '3px', fontSize: '1em', fontWeight: 'bold', backgroundColor: 'transparent', color: 'white' }}>
                                            POSITIONS&nbsp;&nbsp;&nbsp;
                                            {tradePositions.length > 0
                                                ? `${displayedPositionIndex + 1} / ${tradePositions.length}`
                                                : '0 / 0'
                                            }
                                        </span>
                                    </div>

                                    <div style={{ width: '30%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '6px' }}>
                                        {tradePositions.length > 1 &&
                                            <>
                                                <BsFillCaretLeftFill size={18} style={{ fill: 'white' }} onClick={() => handleAdvancePosition(-1)} />
                                                &nbsp;&nbsp;&nbsp;&nbsp;
                                                <BsFillCaretRightFill size={18} style={{ fill: 'white' }} onClick={() => handleAdvancePosition(1)} />
                                            </>
                                        }
                                    </div>



                                </div>



                                <div style={{ width: '100%', height: '74%', backgroundColor: POSITIONDIVCOLOR, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: textFontSize, fontWeight: 'bold' }}>
                                    {/* This is the POSITIONS display */}

                                    <div style={{ width: '14%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>
                                        {tradePositions.length > 0 &&
                                            <ImExit size={24} style={{ fill: 'gray' }} onClick={toggleExitDialog} />
                                        }

                                    </div>

                                    <div style={{ width: '71%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', flexDirection: 'column' }}>
                                        {/* this is the center div of the ORDERS window   */}
                                        <div style={{ width: '100%', height: '38%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '20px' }}>
                                            {displayedPosition['row0'] ? displayedPosition['row0'].replace('**', displayedPositionNumContracts) : ''}
                                        </div>
                                        <div style={{ width: '100%', height: '38%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '20px' }}>
                                            {displayedPosition['row1'] ? displayedPosition['row1'].replace('**', displayedPositionNumContracts) : ''}
                                        </div>

                                    </div>
                                    {tradePositions.length > 0 &&
                                        <div style={{ width: '15%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>
                                            <div style={{ width: '100%', height: '40%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                                                P&L
                                                {/* {tradeOrders[displayedOrderIndex]['type'].charAt(0).toUpperCase() + tradeOrders[displayedOrderIndex]['type'].slice(1)} */}
                                            </div>
                                            <div style={{ width: '100%', height: '40%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                                                {/* <span style={{ backgroundColor: 'green', paddingRight: '5px', paddingLeft: '5px', color: 'white' }}> 12% </span> */}

                                                <Tippy placement={'top'} delay={500} content={
                                                    // <div style={{ backgroundColor: 'tranparent', color: 'white', paddingLeft: '3px', paddingRight: '3px' }}>
                                                    <> {displayedPositionToolTip}</>
                                                    // </div>
                                                }>

                                                    <span style={{ backgroundColor: displayedPositionGainLoss >= 0 ? 'green' : 'red', paddingRight: '5px', paddingLeft: '5px', color: 'white' }}>
                                                        {displayedPositionGainLoss}%
                                                    </span>

                                                </Tippy>

                                            </div>
                                        </div>
                                    }








                                </div>
                            </div>

                            <div style={{ width: '100%', height: '50%', backgroundColor: 'transparent', display: 'flex', flexDirection: 'column' }}>

                                {/* title bar of orders  */}
                                <div style={{ width: '100%', height: '26%', backgroundColor: 'gray', display: 'flex', justifyContent: 'left', alignItems: 'center' }}>

                                    <div style={{ width: '70%', height: '100%', backgroundColor: 'transparent', paddingLeft: '3px', fontSize: '1em', fontWeight: 'bold', display: 'flex', justifyContent: 'left', alignItems: 'center', color: 'white' }}>
                                        ORDERS &nbsp;&nbsp;&nbsp;
                                        {tradeOrders.length > 0
                                            ? `${displayedOrderIndex + 1} / ${tradeOrders.length}`
                                            : '0 / 0'
                                        }

                                        &nbsp;&nbsp;&nbsp;
                                        {tradeOrders[displayedOrderIndex] !== undefined ? (
                                            <div>
                                                status: {tradeOrders[displayedOrderIndex]['status']}
                                            </div>
                                        ) : null}
                                    </div>

                                    <div style={{ width: '30%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '6px' }}>
                                        {tradeOrders.length > 1 &&
                                            <>
                                                <BsFillCaretLeftFill size={18} style={{ fill: 'white' }} onClick={() => handleAdvanceOrder(-1)} />
                                                &nbsp;&nbsp;&nbsp;&nbsp;
                                                <BsFillCaretRightFill size={18} style={{ fill: 'white' }} onClick={() => handleAdvanceOrder(1)} />
                                            </>
                                        }


                                    </div>

                                </div>


                                <div style={{ width: '100%', height: '74%', backgroundColor: ORDERDIVCOLOR, display: 'flex', justifyContent: 'left', alignItems: 'center', flexDirection: 'row', fontSize: textFontSize, fontWeight: 'bold' }}>
                                    {/* This is the ORDERS display */}


                                    <div style={{ width: '14%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>
                                        {tradeOrders.length > 0 && tradeOrders[displayedOrderIndex]['status'] !== 'canceled' && tradeOrders[displayedOrderIndex]['status'] !== 'filled' && tradeOrders[displayedOrderIndex]['status'] !== 'expired' && tradeOrders[displayedOrderIndex]['status'] !== 'rejected' &&
                                            <MdOutlineCancel size={24} style={{ fill: 'gray' }} onClick={() => handleCancelOrderConfirm()} />
                                        }
                                    </div>


                                    <div style={{ width: '71%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', flexDirection: 'column' }}>
                                        {/* this is the center div of the ORDERS window   */}
                                        <div style={{ width: '100%', height: '38%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center' }}>
                                            {displayedOrder['row0']}
                                        </div>
                                        <div style={{ width: '100%', height: '38%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center' }}>
                                            {displayedOrder['row1']}
                                        </div>

                                    </div>
                                    {tradeOrders.length > 0 &&
                                        <div style={{ width: '15%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center', flexDirection: 'column' }}>
                                            <div style={{ width: '100%', height: '40%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                                                {/* {displayedOrderPrice['sell'] - displayedOrderPrice['buy'] >= 0 ? 'Credit' : 'Debit'} */}
                                                {tradeOrders[displayedOrderIndex]['type'].charAt(0).toUpperCase() + tradeOrders[displayedOrderIndex]['type'].slice(1)}
                                            </div>
                                            <div style={{ width: '100%', height: '40%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                                                {/* ${(Math.abs(displayedOrderPrice['sell'] - displayedOrderPrice['buy'])).toFixed(2)} */}

                                                {tradeOrders[displayedOrderIndex]['price'] !== undefined && tradeOrders[displayedOrderIndex]['price'].toFixed(2)}
                                            </div>
                                        </div>
                                    }

                                </div>
                            </div>
                        </div>
                    </div>



                    {/* right side column */}
                    <div style={{ fontSize: textFontSize, width: column_width, height: '100%', backgroundColor: 'lightgray', display: 'flex', justifyContent: 'right', alignItems: 'center', flexDirection: 'column' }}>
                        {/* first Div is just a spacer so the rest don't start so high on the window */}
                        <div style={{ width: '100%', height: '10px', backgroundColor: 'transparent', display: 'flex' }}></div>


                        <div style={{ width: '100%', height: infoRowHeight, backgroundColor: 'transparent', display: 'flex' }}>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '2px' }}>
                                <span style={{ fontWeight: 'bold' }}> Available Capital:</span>
                            </div>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center', paddingLeft: '2px' }}>
                                <span style={{ backgroundColor: 'black', color: 'white', paddingLeft: '5px', paddingRight: '5px' }}>${(perTradeCapital[0] - tradeRiskCapital).toLocaleString()}</span>
                            </div>
                        </div>

                        <div style={{ width: '100%', height: infoRowHeight, backgroundColor: 'transparent', display: 'flex' }}>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '2px' }}>
                                <span style={{ fontWeight: 'bold' }}> Per Trade Capital:</span>
                            </div>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center', paddingLeft: '2px' }}>

                                <span style={{ backgroundColor: 'black', color: 'white', paddingLeft: '5px', paddingRight: '5px' }}>
                                    {/* ${perTradeCapital[1].toLocaleString()} */}
                                    {perTradeCapital[1] === 0 ? 'Minimum' : `$${perTradeCapital[1]}`}
                                </span>

                            </div>
                        </div>

                        <div style={{ width: '100%', height: infoRowHeight, backgroundColor: 'transparent', display: 'flex' }}>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '2px' }}>
                                <span style={{ fontWeight: 'bold' }}> Credit:</span>
                            </div>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center', paddingLeft: '2px' }}>
                                {/* <TextBox text={creditSpreadPriceList[selectedCreditSpread]} width='2' name="num_option_contracts" /> */}
                                <TextBox text={credit} width='2' name="credit" tbBlur={handleBlur} creditLock={creditLock} />
                                <div style={{ paddingLeft: '4px', backgroundColor: 'transparent' }} onClick={() => toggleLock()} >
                                    {creditLock.current
                                        ? <BsLock size={14} style={{ verticalAlign: "middle", fill: "black" }} />
                                        : <BsUnlock size={14} style={{ verticalAlign: "middle", fill: "black" }} />
                                    }
                                </div>
                                <span>&nbsp; {parseInt(100 * credit / spreadPrice)}%</span>

                            </div>
                        </div>


                        <div style={{ width: '100%', height: infoRowHeight, backgroundColor: 'transparent', display: 'flex' }}>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '2px' }}>
                                <span style={{ fontWeight: 'bold' }}> Num Contracts:</span>
                            </div>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center', paddingLeft: '2px' }}>
                                {/* <TextBox text={perTradeCapital[2].toLocaleString()} width='2' name="num_option_contracts" /> */}
                                <TextBox text={numContracts} width='2' name="num_option_contracts" tbBlur={handleBlur} />
                            </div>
                        </div>


                        <div style={{ width: '100%', height: infoRowHeight, backgroundColor: 'transparent', display: 'flex' }}>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '2px' }}>
                                <span style={{ fontWeight: 'bold' }}> Trade Risk Capital:</span>
                            </div>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center', paddingLeft: '2px' }}>
                                {/* <span style={{ backgroundColor: 'black', color: 'white', paddingLeft: '5px', paddingRight: '5px' }}>${perTradeCapital[3].toLocaleString()}</span> */}

                                {/* backgroundColor: tradeRiskCapital > perTradeCapital[1] || (perTradeCapital[1] === 0 && numContracts > 1) ? 'rgb(75,0,0)' : 'black' */}
                                {perTradeCapital[1] === 0
                                    ? <span style={{ backgroundColor: numContracts > 1 ? 'rgb(75,0,0)' : 'black', color: 'white', paddingLeft: '5px', paddingRight: '5px' }}>
                                        ${tradeRiskCapital.toLocaleString()}
                                    </span>
                                    : <span style={{ backgroundColor: tradeRiskCapital > perTradeCapital[1] ? 'rgb(75,0,0)' : 'black', color: 'white', paddingLeft: '5px', paddingRight: '5px' }}>
                                        ${tradeRiskCapital.toLocaleString()}
                                    </span>
                                }
                            </div>
                        </div>

                        {/* <div style={{ width: '100%', height: infoRowHeight, backgroundColor: 'transparent', display: 'flex' }}>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'right', alignItems: 'center', paddingRight: '2px' }}>
                                <span style={{ fontWeight: 'bold' }}> Auto Exit With Stock Gain:</span>
                            </div>
                            <div style={{ width: '50%', height: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'left', alignItems: 'center', paddingLeft: '2px' }}>
                                <TextBox text={exitStockGain} width='2' name="auto_exit_gain_pct" tbBlur={handleBlur} />
                                <span style={{ fontWeight: 'bold', paddingLeft: '4px' }}> Loss:</span>
                                <TextBox text={exitStockLoss} width='2' name="auto_exit_loss_pct" tbBlur={handleBlur} />
                            </div>
                        </div> */}


                        {/* the coming risk graph  */}
                        <div style={{ width: '100%', height: rightBottomHeight, backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>


                            <div style={{ width: '25%', height: '100%', backgroundColor: 'transparent', border: '0px solid gray', display: 'flex', paddingTop: '0px', justifyContent: 'flex-start', alignItems: 'center', flexDirection: 'column' }}>

                                <button style={{ fontSize: '0.8em', width: '90%', marginTop: '3px' }} disabled={creditSpreadList.length === 0} onClick={() => handlePlaceOrder()}>Place Order</button>
                                <button style={{ fontSize: '0.8em', width: '90%', marginTop: '3px' }} onClick={() => handleAutoSelection()} >Auto Select</button>
                                <button style={{ fontSize: '0.8em', width: '90%', marginTop: '3px' }}  >Risk Profile</button>
                                <button style={{ fontSize: '0.8em', width: '90%', marginTop: '3px' }}  >Price Chart</button>

                                <button style={{ fontSize: '0.8em', width: '90%', marginTop: '3px' }} onClick={toggleExitDialog} >test</button>


                                {/* <button style={{ width: '90%', marginTop: '3px' }} onClick={() => handlePlaceOrder()}>Buy to Close</button> */}
                            </div>

                            <div style={{ width: '75%', height: '100%', backgroundColor: 'transparent', borderTop: '0px solid gray', display: 'flex', justifyContent: 'center', alignItems: 'center', borderLeft: '0px dotted gray' }}>
                                {/* <RiskProfileChart chartTitle="Risk Profile" chartData={riskProfileAtExpiration} chartLabels={riskProfileLabels} chartDataCompare={riskProfileNow} symbol={props.symbol} /> */}
                                <RiskProfileChart stockPrice={stockPrice} creditSpreadList={creditSpreadList} selectedCreditSpread={selectedCreditSpread.current} credit={credit} numContracts={numContracts} />

                            </div>

                        </div>

                    </div>

                </div>

            </div>






        </div>


    )
}
export default TradeInstrument
