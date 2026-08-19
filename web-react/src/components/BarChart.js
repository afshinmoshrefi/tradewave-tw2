import React, { useContext, useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import { UserContext } from './UserContext';
import { UIcolors, themeColors } from './Common';
import { buildBarChartSeries } from './barChartSeries';
import {
    BAR_CHART_EXCURSION_STYLES,
    getCappedNeedleCapHalfWidth,
    getExcursionVisibility,
    getNeedleRange,
    normalizeBarChartExcursionStyle,
} from './barChartExcursion';

const formatPercent = (value) => {
    const rounded = Number.parseFloat(Number(value).toFixed(2));
    return `${rounded > 0 ? '+' : ''}${rounded}%`;
};

const excursionOverlayPlugin = {
    id: 'tradeWaveExcursionOverlay',
    afterDatasetsDraw(chart, args, pluginOptions) {
        const {
            style,
            highs = [],
            lows = [],
            showHigh,
            showLow,
            highColor,
            lowColor,
            needleColor,
        } = pluginOptions || {};

        if (!style || style === BAR_CHART_EXCURSION_STYLES.FILLED) return;

        const bars = chart.getDatasetMeta(0)?.data || [];
        const yScale = chart.scales?.y;
        if (!yScale || bars.length === 0) return;

        const ctx = chart.ctx;
        ctx.save();
        ctx.lineCap = style === BAR_CHART_EXCURSION_STYLES.TICKS ? 'butt' : 'round';

        bars.forEach((bar, index) => {
            const high = highs[index];
            const low = lows[index];
            const x = bar.x;
            const barWidth = Number.isFinite(bar.width) ? bar.width : 12;
            const hasHigh = Number.isFinite(high) && high > 0;
            const hasLow = Number.isFinite(low) && low < 0;

            if (style === BAR_CHART_EXCURSION_STYLES.TICKS) {
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

                const capHalfWidth = getCappedNeedleCapHalfWidth(barWidth);
                ctx.lineWidth = Math.max(2, Math.min(3, barWidth * 0.08));

                if (drawHigh) {
                    const highY = yScale.getPixelForValue(high);
                    ctx.beginPath();
                    ctx.strokeStyle = highColor;
                    ctx.moveTo(x - capHalfWidth, highY);
                    ctx.lineTo(x + capHalfWidth, highY);
                    ctx.stroke();
                }

                if (drawLow) {
                    const lowY = yScale.getPixelForValue(low);
                    ctx.beginPath();
                    ctx.strokeStyle = lowColor;
                    ctx.moveTo(x - capHalfWidth, lowY);
                    ctx.lineTo(x + capHalfWidth, lowY);
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

        ctx.restore();
    },
};

const BarChart = ({
    seasonalBarChartData,
    showMFE,
    showMAE,
    barClicked,
    barChartLongOrShort,
    UITheme,
    barChartExcursionStyle,
}) => {
    const { rdd, loggedinUser } = useContext(UserContext);
    const tc = themeColors(UITheme);
    const excursionStyle = normalizeBarChartExcursionStyle(barChartExcursionStyle);
    const excursionVisibility = getExcursionVisibility(
        barChartLongOrShort,
        showMFE,
        showMAE
    );

    // Derive the complete Chart.js payload during render. Effect-backed state
    // briefly painted the previous ticker after a fast row change.
    const {
        dataMain,
        dataMainColors,
        dataHigh,
        dataLow,
        dataMax,
        dataMin,
        labels,
    } = useMemo(() => {
        const series = buildBarChartSeries(seasonalBarChartData, {
            green: tc.barGreen,
            red: tc.barRed,
        });

        return {
            dataMain: series.main,
            dataMainColors: series.mainColors,
            dataHigh: series.highs,
            dataLow: series.lows,
            dataMax: excursionVisibility.showHigh ? series.upperRemainders : [],
            dataMin: excursionVisibility.showLow ? series.lowerRemainders : [],
            labels: series.labels,
        };
    }, [
        seasonalBarChartData,
        excursionVisibility.showHigh,
        excursionVisibility.showLow,
        tc.barGreen,
        tc.barRed,
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

    const datasets = [{
        label: 'dataMain',
        data: dataMain,
        backgroundColor: dataMainColors,
    }];
    if (excursionStyle === BAR_CHART_EXCURSION_STYLES.FILLED) {
        datasets.push(
            {
                label: 'dataMax',
                data: dataMax,
                backgroundColor: tc.barMFE,
            },
            {
                label: 'dataMin',
                data: dataMin,
                backgroundColor: tc.barMAE,
            }
        );
    }

    const data = { labels, datasets };
    const scaleValues = [0, ...dataMain].filter(Number.isFinite);
    if (excursionStyle !== BAR_CHART_EXCURSION_STYLES.FILLED) {
        if (excursionVisibility.showHigh) {
            scaleValues.push(...dataHigh.filter(value => Number.isFinite(value) && value > 0));
        }
        if (excursionVisibility.showLow) {
            scaleValues.push(...dataLow.filter(value => Number.isFinite(value) && value < 0));
        }
    }
    const scaleBounds = excursionStyle === BAR_CHART_EXCURSION_STYLES.FILLED
        ? {}
        : {
            suggestedMin: Math.min(...scaleValues),
            suggestedMax: Math.max(...scaleValues),
        };
    const highColor = excursionVisibility.highKind === 'MFE' ? tc.barMFE : tc.barMAE;
    const lowColor = excursionVisibility.lowKind === 'MFE' ? tc.barMFE : tc.barMAE;
    const needleColor = UITheme === 'dark'
        ? 'rgba(220, 225, 232, 0.92)'
        : 'rgba(25, 30, 35, 0.82)';

    const options = {
        animation: false,
        onClick: function (event, item) {
            if (item.length > 0) {
                barClicked(labels[item[0].index]);
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
    };

    return (
        <div style={{ backgroundColor: UIcolors(loggedinUser, UITheme)['background_barchart'], height: '100%' }}>
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
