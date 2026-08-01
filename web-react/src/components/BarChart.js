import React, { useContext, useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import { UserContext } from './UserContext';
import { UIcolors, themeColors } from './Common';
import { buildBarChartSeries } from './barChartSeries';

const BarChart = ({ seasonalBarChartData, showMFE, showMAE, barClicked, barChartLongOrShort, UITheme }) => {
    const { rdd, loggedinUser } = useContext(UserContext);
    const tc = themeColors(UITheme);

    // Derive the complete Chart.js payload during render. The previous effect-
    // backed state rendered one frame with the prior ticker before installing
    // the new labels and bars, creating a measurable stale-canvas flash.
    const {
        dataMain,
        dataMainColors,
        dataMax,
        dataMin,
        labels,
    } = useMemo(() => {
        const series = buildBarChartSeries(seasonalBarChartData, {
            green: tc.barGreen,
            red: tc.barRed,
        });

        const includeMax =
            (barChartLongOrShort === 'long' && showMFE) ||
            (barChartLongOrShort === 'short' && showMAE);
        const includeMin =
            (barChartLongOrShort === 'long' && showMAE) ||
            (barChartLongOrShort === 'short' && showMFE);

        return {
            dataMain: series.main,
            dataMainColors: series.mainColors,
            dataMax: includeMax ? series.upperRemainders : [],
            dataMin: includeMin ? series.lowerRemainders : [],
            labels: series.labels,
        };
    }, [
        seasonalBarChartData,
        showMFE,
        showMAE,
        barChartLongOrShort,
        tc.barGreen,
        tc.barRed,
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
                backgroundColor: tc.barMFE,
            },
            {
                label: 'dataMin',
                data: dataMin,
                backgroundColor: tc.barMAE,
            },
        ]
    };

    const options = {
        // The chart is an interaction result, not a decorative entrance. Chart.js
        // animations kept repainting the canvas after ChartData4 had completed,
        // which made rapid row selections look stale and missed the viewer's
        // response-to-usable budget.
        animation: false,
        onClick: function (event, item) {
            if (item.length > 0) {
                barClicked(labels[item[0]['index']]);
            }
        },
        devicePixelRatio: 0.5,
        normalized: true,
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

export default React.memo(BarChart);
