import React, { useMemo, useContext, useRef } from 'react';
import { Bar } from 'react-chartjs-2';
import { UserContext } from './UserContext';
import { UIcolors, themeColors } from './Common';
import { buildBarChartSeries } from './barChartSeries';
import {
    BAR_CHART_EXCURSION_STYLES,
    getExcursionVisibility,
    getNeedleRange,
    normalizeBarChartExcursionStyle,
} from './barChartExcursion';

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

                if (showHigh && hasHigh) {
                    const highY = yScale.getPixelForValue(high);
                    ctx.beginPath();
                    ctx.strokeStyle = highColor;
                    ctx.moveTo(x - halfWidth, highY);
                    ctx.lineTo(x + halfWidth, highY);
                    ctx.stroke();
                }

                if (showLow && hasLow) {
                    const lowY = yScale.getPixelForValue(low);
                    ctx.beginPath();
                    ctx.strokeStyle = lowColor;
                    ctx.moveTo(x - halfWidth, lowY);
                    ctx.lineTo(x + halfWidth, lowY);
                    ctx.stroke();
                }
                return;
            }

            const drawHigh = showHigh && hasHigh;
            const drawLow = showLow && hasLow;
            if (!drawHigh && !drawLow) return;
            const range = getNeedleRange(
                hasHigh ? high : 0,
                hasLow ? low : 0,
                drawHigh,
                drawLow
            );
            if (!range) return;

            ctx.beginPath();
            ctx.strokeStyle = needleColor;
            ctx.lineWidth = 1.5;
            ctx.moveTo(x, yScale.getPixelForValue(range.from));
            ctx.lineTo(x, yScale.getPixelForValue(range.to));
            ctx.stroke();
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

    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) {
        axisFontSize = '15vw';
        tooltipEnabled = false;
    } else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) {
        axisFontSize = '18vw';
        tooltipEnabled = false;
    } else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) {
        if (window.innerHeight > 1024) axisFontSize = '26vw';
        else axisFontSize = '20vw';
    } else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) {
        axisFontSize = '16vw';
    } else if (!rdd.isMobile) {
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
                backgroundColor: tc.barMFE,
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
        normalized: true,
        maintainAspectRatio: false,
        scales: {
            y: {
                stacked: excursionStyle === BAR_CHART_EXCURSION_STYLES.FILLED,
                beginAtZero: true,
                ...scaleBounds,
                ticks: {
                    color: tc.tickColor,
                    font: { size: axisFontSize },
                    callback: function (val) {
                        const valueString = val.toString();
                        let renderedValue = val;
                        if (valueString.length > 10) renderedValue = renderedValue.toFixed(2);
                        return renderedValue + '%';
                    },
                },
                grid: {
                    display: false,
                },
            },
            x: {
                stacked: excursionStyle === BAR_CHART_EXCURSION_STYLES.FILLED,
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
            tradeWaveExcursionOverlay: {
                style: excursionStyle,
                highs: dataHigh,
                lows: dataLow,
                showHigh: excursionVisibility.showHigh,
                showLow: excursionVisibility.showLow,
                highColor,
                lowColor,
                needleColor,
            },
            tooltip: {
                enabled: tooltipEnabled,
                callbacks: {
                    title: function (context) {
                        return 'year: ' + context[0].label;
                    },
                    afterTitle: function () {
                        return barChartLongOrShort === 'long'
                            ? 'strategy: Long'
                            : 'strategy: Short';
                    },
                    beforeBody: function (context) {
                        let result = '';
                        switch (context[0].dataset.label) {
                            case 'dataMin':
                                result = excursionVisibility.lowKind + ': min price';
                                break;
                            case 'dataMax':
                                result = excursionVisibility.highKind + ': max price';
                                break;
                            case 'dataMain':
                                result = 'strategy data';
                                break;
                            default:
                                break;
                        }
                        return result;
                    },
                    label: function (context) {
                        let pct = Number.parseFloat(context.raw);
                        if (barChartLongOrShort === 'short') pct *= -1;
                        return 'gain:' + formatPercent(pct);
                    },
                    afterBody: function (context) {
                        if (
                            excursionStyle === BAR_CHART_EXCURSION_STYLES.FILLED
                            || context[0].dataset.label !== 'dataMain'
                        ) return [];

                        const dataIndex = context[0].dataIndex;
                        const directionMultiplier = barChartLongOrShort === 'short' ? -1 : 1;
                        const lines = [];
                        if (excursionVisibility.showHigh && dataHigh[dataIndex] > 0) {
                            lines.push(
                                `${excursionVisibility.highKind}: ${formatPercent(dataHigh[dataIndex] * directionMultiplier)}`
                            );
                        }
                        if (excursionVisibility.showLow && dataLow[dataIndex] < 0) {
                            lines.push(
                                `${excursionVisibility.lowKind}: ${formatPercent(dataLow[dataIndex] * directionMultiplier)}`
                            );
                        }
                        return lines;
                    },
                },
            },
        },
    }), [labels, axisFontSize, tc.tickColor, tooltipEnabled, barChartLongOrShort]);

    return (
        <div style={{ backgroundColor: chartBackgroundColor, height: "100%" }}>
            <Bar
                key={`${UITheme}`}
                data={data}
                options={options}
                plugins={[excursionOverlayPlugin]}
            />
        </div>
    );
};

export default React.memo(BarChart);
