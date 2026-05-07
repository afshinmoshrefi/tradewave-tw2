import React, { useMemo, useContext, useEffect, useState } from 'react';

import { Line } from 'react-chartjs-2';
import { UserContext } from './UserContext'

import 'chartjs-plugin-annotation';

import { FaAngleDoubleLeft } from "react-icons/fa";
import { BsQuestionCircle } from "react-icons/bs";
import { UIcolors } from './Common'
import { appserverURL } from './Common'
import { getTodayDate, daysBetweenDates } from './Common';

// <FaAngleLeft size={30} style={{ fill: "white" }} onClick={handleBackClick} />



const RiskProfileChart = ({ stockPrice, creditSpreadList, selectedCreditSpread, credit, numContracts }) => {


    const { browserH, browserW, rdd, infoTextSize, loggedinUser, token } = useContext(UserContext)


    // console.log('props.chartData=',props.chartData)
    // console.log('props.chartDataCompare=',props.chartDataCompare)

    const [cumulativeBoundingClientRect, SetCumulativeBoundingClientRect] = useState([])

    //---------------------------------------------------------------------------
    const [chartLabels, SetChartLabels] = useState([
        'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j'
    ]);
    //---------------------------------------------------------------------------
    const [chartData1, SetChartData1] = useState([
        2, 3, 4, 5, 6, 4, 7, 9, 2, 4
    ]);
    //---------------------------------------------------------------------------
    const [chartData2, SetChartData2] = useState([
        5, 8, 3, 6, 1, 9, 7, 0, 6, 7
    ]);
    //---------------------------------------------------------------------------
    const [xMin, SetXMin] = useState(80)  // these numbers limit the display of risk profile to a range of numbers around the stock price
    const [xMax, SetXMax] = useState(120)

    var questionSize = 16;
    if (rdd.isTablet && browserH > browserW) {
        if (browserH > 1024) questionSize = 30;
        else questionSize = 22;
    }



    let yAxisFont = 9;


    var showTitleDiv = 'none';

    var chartHeight = '100%'; // chartHeight and titleHeight need to add up to 100%
    var titleHeight = '20%';

    var showChartTitle = false; // remove the auto chart title 9/12/2023
    var caretSize = '30'
    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) caretSize = '20' //smartphone portrat
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) caretSize = '30'

    //adjust the xaxis font-size for ipads, tablets
    if (rdd.isMobile) {
        if (rdd.isTablet) {
            if (browserH > browserW) {
                // xAxisFont = browserW / 35
                yAxisFont = browserW / 35
                // titleFont = browserW / 35

                showTitleDiv = 'flex';
                chartHeight = '88%';
                // titleHeight = '12%';
                showChartTitle = false;
            }
            else {
                // xAxisFont = browserW / 75
                yAxisFont = browserW / 75
            }
        }
        else {
            showTitleDiv = 'flex';
            chartHeight = '88%';
            titleHeight = '12%';
            showChartTitle = false;
        }

    }


    // this useEffect prepares the data for the getting riskprofile data from the appserver
    // useEffect(() => {


    // }, []);


    //-------------------------------------------
    // get risk profile data from app server
    //-------------------------------------------
    useEffect(() => {


        let asURL = appserverURL()
        let userid = loggedinUser;

        let url = `${asURL}/risk_profile?token=${token}`

        let scs = creditSpreadList[selectedCreditSpread]; // stands for selected creditspread

        console.log('&&&&&&&&&&&&&&&&',creditSpreadList , selectedCreditSpread);

        if (creditSpreadList.length > 0 && selectedCreditSpread !== null) { // when selectedCreditSpread was 0 riskprofile didn't change !! stupid mistake

            // console.log('xxxxxxxxxxxxxxxxxxxx', creditSpreadList)
            // console.log(scs)


            let daysToExpiration0 = daysBetweenDates(getTodayDate(), scs['buy']['expiration_date']) / 365;
            let daysToExpiration1 = daysBetweenDates(getTodayDate(), scs['sell']['expiration_date']) / 365;

            if (scs['buy']['option_type'] === 'put') {
                SetXMin(parseInt(stockPrice * .75))
                SetXMax(parseInt(stockPrice * 1.30))
            }
            else {
                SetXMin(parseInt(stockPrice * .65))
                SetXMax(parseInt(stockPrice * 1.25))
            }

            let data = {
                'current_stock_price': parseFloat(stockPrice),
                'num_contracts': parseInt(numContracts),
                // 'int_rate'          : int_rate,

                'strike_price0': scs['buy']['strike'],
                'time_to_expire0': daysToExpiration0,
                'sigma0': scs['buy']['greeks']['mid_iv'],
                'type0': scs['buy']['option_type'] === 'put' ? 'P' : 'C',
                'long_or_short0': 'long',  // because we are buying this option its a long

                'strike_price1': scs['sell']['strike'],
                'time_to_expire1': daysToExpiration1,
                'sigma1': scs['sell']['greeks']['mid_iv'],
                'type1': scs['sell']['option_type'] === 'put' ? 'P' : 'C',
                'long_or_short1': 'short',

                'debit_or_credit': parseFloat(credit)
            }

            fetch(url, {
                method: 'POST', // Specify the HTTP method
                headers: {
                    'Content-Type': 'application/json',
                },
                // Add the request body if you have data to send
                body: JSON.stringify(data),
            })

                .then((res) => {
                    return res.json();
                })

                .then((g) => {

                    // console.log('gggggggggggggggggggggggggggggg from risk profile', g);
                    // console.log('g["cs_labels"]=', g['cs_labels'])
                    // console.log('chartLables=', chartLabels)
                    // console.log('chartdata1=', chartData1)
                    // console.log('chartdata2=',chartData2)

                    SetChartLabels(g['cs_labels']);
                    SetChartData1(g['cs_current']);
                    SetChartData2(g['cs_exp']);


                })
                .catch(err => {
                    console.log('getResourcesObj error=', err.message)
                })
        }

    }, [selectedCreditSpread, credit, numContracts])






    // console.log('props.chartData,=', props.chartData,)
    // console.log('props.chartLabels=', props.chartLabels)


    const data = {
        labels: chartLabels,
        datasets: [
            { fill: true },
            {
                // for some reason the first line refreshes all the time. but if I make it a blank line and then add the lines as line-current and line-expiraiton it works without blinking and refreshing constantly 
                borderWidth: 1,
                pointBorderWidth: 0,
                data: [],
                pointRadius: 0,
                // backgroundColor: 'rgb(255, 99, 132)',
                borderColor: 'magenta', // linechart color
                // pointStyle: pointStyle
                hidden: false
            },
            {
                label: "line-current",
                borderWidth: 2,
                pointBorderWidth: 0,
                data: chartData1,
                pointRadius: 0,
                // backgroundColor: 'rgb(255, 99, 132)',
                borderColor: 'magenta', // linechart color
                // pointStyle: pointStyle
                hidden: false
            },
            {
                label: "line-expiration",
                borderWidth: 1,
                pointBorderWidth: 0,
                data: chartData2,
                pointRadius: 0,
                borderColor: 'blue', // linechart color
                borderDash: [1, 1],
                hidden: false
            },


        ],



    };

    const options = {
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                ticks: {
                    font: {
                        size: yAxisFont,
                        weight: 'bold'
                    },
                    beginAtZero: true,
                    callback: function (val) { return '$' + val; },
                }
            },

            x: {
                min: xMin,  // minimum value
                max: xMax,
                ticks:
                {
                    font: {
                        size: yAxisFont,
                        weight: 'bold'
                    },
                }
            },


        },
        plugins: {
            legend: { display: false },
            annotation:
            {
                display: false,
                annotations: {
                    zeroLine: {
                        type: 'line',
                        yMin: 0,
                        yMax: 0,
                        borderColor: 'gray',
                        borderWidth: 1,
                    },

                    stockPriceLine: {
                        type: 'line',
                        xMin: parseInt(stockPrice),
                        xMax: parseInt(stockPrice),
                        borderColor: 'darkorange',
                        borderWidth: 2,
                        borderDash: [2, 2],  // this will make the line dashed
                    },

                }
            },
            tooltip: {
                callbacks: {
                    title: function (context) {
                        return 'security price: $' + context[0]['label'];
                    },


                    beforeBody: function (context) {
                        let r = '';
                        if (context[0].dataset.label === 'line-current') {
                            r = 'position gain: '
                        }
                        else if (context[0].dataset.label === 'line-expiration') {
                            r = 'position gain: '
                        }
                        return r;
                    },
                    label: function (context) {
                        let position_value = parseFloat(context.raw).toFixed(2);
                        return 'postion value: $' + position_value;

                    },
                }
            }
        }
    };


    const lineChartDivStyle = {
        backgroundColor: UIcolors(loggedinUser)['background_risk_profile'],
        height: chartHeight,
        //  border: '1px solid lightgray' ,
        borderLeft: '1px solid lightgray',
        borderRight: '1px solid lightgray',
        borderBottom: '1px solid lightgray',
    }





    //------------------------------------------------------------------------------------------
    return (
        <div className="generic-line-chart" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column',paddingRight:'6px' }}>
            <div className="cumulative-linechart" style={lineChartDivStyle}>
                <Line data={data} options={options} />
            </div>
        </div>
    )

};
export default RiskProfileChart
