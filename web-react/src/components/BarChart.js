import React, { useState, useEffect, useContext } from 'react';
import { Bar } from 'react-chartjs-2';
import { UserContext } from './UserContext';
import { UIcolors, themeColors } from './Common';

const BarChart = ({ seasonalBarChartData, showMFE, showMAE, barClicked, barChartLongOrShort, UITheme }) => {
    const { rdd, loggedinUser } = useContext(UserContext);
    const tc = themeColors(UITheme);

    const [dataMain, setDataMain] = useState([21.02, 7.92, 1.73, 3.65, -4.13, 1.36, 3.56, 5.02, 1.85, 1.17, 6.29, 24.07]);
    const [dataMainColors, setDataMainColors] = useState(() => Array(12).fill(tc.barGreen));
    const [dataMax, setDataMax] = useState([9.53, 4.6, 0.41, 0.36, 0.91, 2.47, 1.3, 0.53, 4.48, 7.83, 3.13, 0.48]);
    const [maxColor, setMaxColor] = useState(tc.barMFE);
    const [dataMin, setDataMin] = useState([-3.28, -1.78, -4, -6.28, -2.3, -4.16, -1.761, -1.54, -4.37, -1.7, -5.2, -6.73]);
    const [minColor, setMinColor] = useState(tc.barMAE);
    const [labels, setLabels] = useState(['2009', '2010', '2011', '2012', '2013', '2014', '2015', '2016', '2017', '2018', '2019', '2020']);

    useEffect(() => {
        var pos = 0, neg = 0, tmpLevels = [], tmpColors = [], tmpMin = [], tmpMax = [], tmpLabels = [];
        seasonalBarChartData.forEach((r) => {
            var plist = r['pct'].split(',');
            tmpLabels.push(r['year']);
            tmpLevels.push(plist[0]);

            if (plist[0] >= 0) {
                pos++;
                tmpColors.push(tc.barGreen);
            }
            if (plist[0] < 0) {
                neg++;
                tmpColors.push(tc.barRed);
            }
        });

        setDataMain(tmpLevels);
        setDataMainColors(tmpColors);
        setLabels(tmpLabels);
        var longOrShort = barChartLongOrShort;

        seasonalBarChartData.forEach((r) => {
            var plist = r['pct'].split(',');
            var close = plist[0];
            var high = plist[1];
            var low = plist[2];

            if (close >= 0 && high > 0) tmpMax.push(parseFloat(high - close).toFixed(2));
            else if (close < 0 && high >= 0) tmpMax.push(parseFloat(high).toFixed(2));
            else if (close < 0 && high < 0) tmpMax.push(0);

            if (close <= 0 && low < 0) tmpMin.push(parseFloat(low - close).toFixed(2));
            else if (close > 0 && low <= 0) tmpMin.push(parseFloat(low).toFixed(2));
            else if (close > 0 && low > 0) tmpMin.push(0);
        });

        if ((longOrShort === 'long' && showMFE) || (longOrShort === 'short' && showMAE)) {
            setDataMax(tmpMax);
        } else setDataMax([]);
        setMaxColor(tc.barMFE);

        if ((longOrShort === 'long' && showMAE) || (longOrShort === 'short' && showMFE)) {
            setDataMin(tmpMin);
        } else setDataMin([]);
        setMinColor(tc.barMAE);
    }, [seasonalBarChartData, showMFE, showMAE, barChartLongOrShort, UITheme]);

    let axisFontSize = '20vw';
    let tooltipEnabled = true;

    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
        axisFontSize = '15vw';
        tooltipEnabled = false;
    } else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { //smartphone landscape
        axisFontSize = '18vw';
        tooltipEnabled = false;
    } else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
        if (window.innerHeight > 1024) axisFontSize = '26vw';
        else axisFontSize = '20vw';
    } else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { //tablet landscape
        axisFontSize = '16vw';
    } else if (!rdd.isMobile) { // desktop
        axisFontSize = '17vw';
    }

    const data = {
        labels: labels,
        datasets: [
            {
                label: 'dataMain',
                data: dataMain,
                backgroundColor: dataMainColors,
            },
            {
                label: 'dataMax',
                data: dataMax,
                backgroundColor: maxColor,
            },
            {
                label: 'dataMin',
                data: dataMin,
                backgroundColor: minColor,
            },
        ]
    };

    const options = {
        onClick: function (event, item) {
            if (item.length > 0) {
                barClicked(labels[item[0]['index']]);
            }
        },
        maintainAspectRatio: false,
        scales: {
            y: {
                stacked: true,
                ticks: {
                    color: tc.tickColor,
                    font: { size: axisFontSize },
                    beginAtZero: true,
                    callback: function (val, index) {
                        let val_str = val.toString();
                        let val2 = val;
                        if (val_str.length > 10) val2 = val2.toFixed(2);
                        return val2 + '%';
                    },
                },
                grid: {
                    display: false,
                },
            },
            x: {
                stacked: true,
                ticks: {
                    color: tc.tickColor,
                    font: { size: axisFontSize },
                },
                grid: {
                    display: false,
                },
            },
        },
        plugins: {
            legend: {
                display: false,
            },
            tooltip: {
                enabled: tooltipEnabled,
                callbacks: {
                    title: function (context) {
                        return 'year: ' + context[0]['label'];
                    },
                    afterTitle: function (context) {
                        let f = '';
                        if (barChartLongOrShort === 'long') f = 'strategy: Long';
                        else f = 'strategy: Short';
                        return f;
                    },
                    beforeBody: function (context) {
                        let r = '';
                        switch (context[0].dataset.label) {
                            case 'dataMin':
                                if (barChartLongOrShort === 'long') r = 'MAE: min price';
                                else r = 'MFE: min price';
                                break;
                            case 'dataMax':
                                if (barChartLongOrShort === 'long') r = 'MFE: max price';
                                else r = 'MAE: min price';
                                break;
                            case 'dataMain':
                                r = 'strategy data';
                                break;
                            default:
                                break;
                        }
                        return r;
                    },
                    label: function (context) {
                        let pct = parseFloat(context.raw);
                        if (barChartLongOrShort === 'short') pct *= -1;
                        let r = 'gain:';
                        if (pct > 0) r += '+';
                        r += pct + '%';
                        return r;
                    },
                }
            },
        },
    };

    return (
        <div style={{ backgroundColor: UIcolors(loggedinUser, UITheme)['background_barchart'], height: "100%" }}>
            <Bar
                key={`${UITheme}`}
                data={data}
                options={options}
            />
        </div>
    );
};

export default BarChart;
