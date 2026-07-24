import React, { useMemo, useContext, useRef } from 'react';
import { Bar } from 'react-chartjs-2';
import { UserContext } from './UserContext';
import { UIcolors, themeColors } from './Common';

const BarChart = ({ seasonalBarChartData, showMFE, showMAE, barClicked, barChartLongOrShort, UITheme }) => {
    const { rdd, loggedinUser } = useContext(UserContext);
    const tc = useMemo(() => themeColors(UITheme), [UITheme]);
    const chartBackgroundColor = useMemo(
        () => UIcolors(loggedinUser, UITheme)['background_barchart'],
        [loggedinUser, UITheme]
    );
    const barClickedRef = useRef(barClicked);
    barClickedRef.current = barClicked;

    const {
        dataMain,
        dataMainColors,
        dataMax,
        maxColor,
        dataMin,
        minColor,
        labels,
    } = useMemo(() => {
        const tmpLevels = [];
        const tmpColors = [];
        const tmpMin = [];
        const tmpMax = [];
        const tmpLabels = [];

        seasonalBarChartData.forEach((r) => {
            const plist = r['pct'].split(',');
            tmpLabels.push(r['year']);
            tmpLevels.push(plist[0]);

            if (plist[0] >= 0) {
                tmpColors.push(tc.barGreen);
            }
            if (plist[0] < 0) {
                tmpColors.push(tc.barRed);
            }

            const close = plist[0];
            const high = plist[1];
            const low = plist[2];

            if (close >= 0 && high > 0) tmpMax.push(parseFloat(high - close).toFixed(2));
            else if (close < 0 && high >= 0) tmpMax.push(parseFloat(high).toFixed(2));
            else if (close < 0 && high < 0) tmpMax.push(0);

            if (close <= 0 && low < 0) tmpMin.push(parseFloat(low - close).toFixed(2));
            else if (close > 0 && low <= 0) tmpMin.push(parseFloat(low).toFixed(2));
            else if (close > 0 && low > 0) tmpMin.push(0);
        });

        const showMax = (barChartLongOrShort === 'long' && showMFE)
            || (barChartLongOrShort === 'short' && showMAE);
        const showMin = (barChartLongOrShort === 'long' && showMAE)
            || (barChartLongOrShort === 'short' && showMFE);

        return {
            dataMain: tmpLevels,
            dataMainColors: tmpColors,
            dataMax: showMax ? tmpMax : [],
            maxColor: tc.barMFE,
            dataMin: showMin ? tmpMin : [],
            minColor: tc.barMAE,
            labels: tmpLabels,
        };
    }, [
        seasonalBarChartData,
        showMFE,
        showMAE,
        barChartLongOrShort,
        tc.barGreen,
        tc.barRed,
        tc.barMFE,
        tc.barMAE,
    ]);

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

    const data = useMemo(() => ({
        labels,
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
    }), [labels, dataMain, dataMainColors, dataMax, maxColor, dataMin, minColor]);

    const options = useMemo(() => ({
        onClick: function (event, item) {
            if (item.length > 0) {
                barClickedRef.current(labels[item[0]['index']]);
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
    }), [labels, axisFontSize, tc.tickColor, tooltipEnabled, barChartLongOrShort]);

    return (
        <div style={{ backgroundColor: chartBackgroundColor, height: "100%" }}>
            <Bar
                key={`${UITheme}`}
                data={data}
                options={options}
            />
        </div>
    );
};

export default BarChart;
