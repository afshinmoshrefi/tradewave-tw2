import React, { useMemo, useContext, useEffect, useState } from 'react';

import { Line } from 'react-chartjs-2';
import { UserContext } from './UserContext'

import 'chartjs-plugin-annotation';

import { FaAngleDoubleLeft } from "react-icons/fa";
import { BsQuestionCircle } from "react-icons/bs";
import { UIcolors, themeColors } from './Common'

// <FaAngleLeft size={30} style={{ fill: "white" }} onClick={handleBackClick} />



const GenericLineChart = (props) => {

    const { browserH, browserW, rdd, infoTextSize } = useContext(UserContext)
    const tc = themeColors(props.UITheme)


    // console.log('props.chartData=',props.chartData)
    // console.log('props.chartDataCompare=',props.chartDataCompare)

    const [cumulativeBoundingClientRect, SetCumulativeBoundingClientRect] = useState([])


    var questionSize = 16;
    if (rdd.isTablet && browserH > browserW) {
        if (browserH > 1024) questionSize = 30;
        else questionSize = 22;
    }


    //------------------------------------------------------------------------------------------
    useMemo(() => {

        // console.log('props.charLabels=', props.chartLabels)

    }, [props.chartData])




    // let xAxisFont = 12;
    let yAxisFont = 12;
    // let titleFont = 12;


    var showTitleDiv = 'none';

    var chartHeight = '80%'; // chartHeight and titleHeight need to add up to 100%
    var titleHeight = '20%';

    // var showChartTitle = true;
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
        // console.log('x,y',xAxisFont,yAxisFont)
    }


    // console.log('props.chartData,=',props.chartData,)


    const data = {
        labels: props.chartLabels,
        datasets: [
            { fill: true },
            {

                borderWidth: 2,
                pointBorderWidth: 0.1,
                data: props.chartData,

                backgroundColor: tc.lineFill,
                borderColor: tc.lineColor, // linechart color
                // pointStyle: pointStyle
            },
            {
                label: "S&P500",
                borderWidth: 1,
                pointBorderWidth: 0.1,
                data: props.chartDataCompare,

                borderColor: tc.compareLineColor, // linechart color
            },
        ],



    };

    const options = {
        maintainAspectRatio: false,
        scales: {
            y: {
                beginAtZero: true,
                ticks: {
                    color: tc.tickColor,
                    font: { size: yAxisFont },
                    beginAtZero: true,
                    callback: function (val, index) { return val + '%'; },
                }
            },

            x: { ticks: { color: tc.tickColor, font: { size: yAxisFont }, } }


        },
        plugins: {
            legend: { display: false },
            title: { display: showChartTitle, text: props.chartTitle }
        }
    };











    const doubleLeftArrow = (event) => {
        props.chartTo(0)
    }


    const handleHelpClicked = () => {
        // props.SetHelpBoxVisible(!props.helpBoxVisible);
        props.SetVideosBoxVisible(true)
    }



    // useEffect(() => {

    //     setTimeout(() => {

    //         let elem = document.querySelector('.generic-line-chart');
    //         let rect = elem.getBoundingClientRect();

    //         SetCumulativeBoundingClientRect(rect);

    //         // console.log('eeeeeeeeeeeeeeeeeelement=',elem);
    //         // console.log('rrrrrrrrrrrrrrect=',rect)

    //     }, 10000); 




    // }, [props.symbol])




    // const overlayLegend = {
    //     position: 'absolute',
    //     backgroundColor: 'red',
    //     top: cumulativeBoundingClientRect['top'],
    //     left: cumulativeBoundingClientRect['left'],
    //     width: cumulativeBoundingClientRect['width'],
    //     height: cumulativeBoundingClientRect['height'],
    //     ZIndex:968,

    // }

    const lineChartDivStyle = {
        backgroundColor: UIcolors(props.loggedinUser, props.UITheme)['background_cumulative'],
        height: chartHeight,
        //  border: '1px solid lightgray' ,
        borderLeft: '1px solid ' + tc.border,
        borderRight: '1px solid ' + tc.border,
        borderBottom: '1px solid ' + tc.border,
    }

    const titleDivStyle = {
        // display: 'flex',
        paddingTop: '4px',
        backgroundColor: props.UITheme === 'dark' ? tc.titleBar : 'white',
        color: tc.text,
        height: titleHeight,
        borderLeft: '1px solid ' + tc.border,
        borderRight: '1px solid ' + tc.border,
        borderTop: '1px solid ' + tc.border,

        // justifyContent: 'center',
        // alignItems: 'center' /* Vertically center the content */
    }

    var legendFontSize = '0.75em';
    var squareFontSize = '1.3em';
    if (rdd.isMacOs) {
        legendFontSize = '0.65em';
    }

    //------------------------------------------------------------------------------------------
    return (
        <div className="generic-line-chart" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }}>



            <div style={{ height: '12%', width: '100%', backgroundColor: tc.controlBar, display: showTitleDiv, alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ height: '100%', width: '10%', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={doubleLeftArrow} >
                    <FaAngleDoubleLeft size={caretSize} style={{ fill: tc.iconFill }} />
                </div>
                <div style={{ height: '100%', width: '80%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ color: tc.textOnControl, fontSize: infoTextSize }}>Cumulative Return</span>
                </div>

                <div style={{ paddingRight: '2%', display: 'flex', width: '10%', alignItems: 'center', justifyContent: 'flex-end' }}>
                    <BsQuestionCircle size={questionSize} style={{ fill: tc.iconFill }} onClick={handleHelpClicked} />
                </div>
            </div>





                <div className="cumulative-linechart-title" style={titleDivStyle}>

                    {!rdd.isMobile && rdd.isMacOs
                        && <span style={{ fontSize: legendFontSize, fontWeight: 'bold' }}>Cumulative Return &nbsp;</span>
                    }

                    {!rdd.isMobile && !rdd.isMacOs
                        && <span style={{ fontSize: legendFontSize, fontWeight: 'bold' }}>{props.chartTitle} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span>
                    }


                    <span style={{ fontWeight: 'bold', fontSize: legendFontSize }}>{props.symbol}</span>
                    <span style={{ fontSize: squareFontSize }}>&#9632;</span>

                    &nbsp; &nbsp;

                    <span style={{ color: 'rgb(170,0,0', fontWeight: 'bold', fontSize: legendFontSize }}>S&P 500</span>
                    <span style={{ color: 'rgb(170,0,0)', fontSize: squareFontSize }}>&#9632;</span>

                </div>



            <div className="cumulative-linechart" style={lineChartDivStyle}>
                <Line data={data} options={options} />
            </div>
        </div>
    )

}
export default GenericLineChart
