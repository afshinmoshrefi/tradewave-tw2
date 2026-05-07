import React, { useContext, useEffect, useState, useRef } from 'react';
import { unstable_batchedUpdates } from 'react-dom';
import { Line } from 'react-chartjs-2';
import { UserContext } from './UserContext';
import Tippy from '@tippyjs/react';
import 'chartjs-plugin-annotation';

import { FaAngleDoubleLeft } from "react-icons/fa";
import { BsQuestionCircle } from "react-icons/bs";
import { BiExport } from 'react-icons/bi';
import { incrementDate, setCookie, getCookie } from './Common';
import SeasonalChartStats from './SeasonalChartStats';
import './styles/SeasonalChart.css';
import { minDaysOut, maxDaysOut, customYearsDesc } from './Common';
import CheckBox from './CheckBox';
import { userAccessToSelectedSecurity } from './Common';
import { BsDownload, BsPencilSquare } from 'react-icons/bs';
import { UIcolors, themeColors } from './Common';
import { opp_dashboard_dialog_content } from './Common';
import { BsFillCircleFill } from "react-icons/bs";
import { brand, trend_chart_left_gap_days } from './Common'

const SeasonalChart = (props) => {

    const currentYear = new Date().getFullYear().toString();

    const debug_events = false;

    const { browserH, browserW, rdd, infoTextSize, loggedinUser, wpUserLevels, globalTextSize, token } = useContext(UserContext);
    const tc = themeColors(props.UITheme);
    const [x0, SetX0] = useState(0);
    const [x1, SetX1] = useState(0);

    const [oppDivLTWH, SetOppDivLTWH] = useState([0, 0, 0, 0, 0]); // dimensions of the div overlay on opp-window

    // pixelsPerDay system - complete rewrite for stability
    const pixelsPerDayRef = useRef(3.5);         // Current pixelsPerDay value
    const lastBrowserWidth = useRef(browserW);   // Last browser width for scaling
    const maxOpportunityWidth = useRef(0);       // Maximum opportunity window width seen (most accurate)
    const loadedInitialValue = useRef(false);    // Whether we've loaded from cookie
    const opportunityLoading = useRef(false);    // Track new opportunity loading state
    const minReliableWidth = useRef(100);        // Minimum width for reliable measurements


    const activePPDRef = useRef(3.5);

    var questionSize = 16;
    if (rdd.isTablet && browserH > browserW) {
        if (browserH > 1024) questionSize = 30;
        else questionSize = 22;
    }

    var statsDivLoc = 'below';  // above or below

    const ref = useRef(null);
    const refLeft = useRef(null);
    const refRight = useRef(null);
    const chartRef = useRef(null);

    // Reference to the last valid window position
    const needsRepositioning = useRef(false);
    const lastValidPosition = useRef({ x: 0, y: 0, width: 0, height: 0 });



    const getExactPPDFromChart = () => {
        const chart = chartRef.current;
        const x = chart?.scales?.x;
        if (!x) return null;

        // Category scale: indices 0,1 are adjacent labels
        const p0 = x.getPixelForValue(0);
        const p1 = x.getPixelForValue(1);
        const step = Math.abs(p1 - p0);

        if (!Number.isFinite(step) || step <= 0) return null;
        return step; // CSS pixels
    };



    // Load pixelsPerDay from cookie on component mount - only once
    useEffect(() => {
        if (!loadedInitialValue.current) {
            const savedRatioStr = getCookie('sc_ratio_txt');
            const cookieVersion = getCookie('sc_ratio_version');

            // Default values
            let usablePixelsPerDay = 3.5;
            let usableMaxWidth = 0;

            if (savedRatioStr) {
                try {
                    // Parse the cookie values
                    const parts = savedRatioStr.split(',');

                    // If this is a v2 cookie (from our new version) or there are exactly 3 values
                    if (cookieVersion === '2' || parts.length === 3) {
                        const [savedBrowserWidth, savedMaxOppWidth, savedPixelsPerDay] = parts.map(Number);

                        if (debug_events) {
                            console.log('Loading from cookie:', {
                                cookieVersion: cookieVersion || 'legacy',
                                savedBrowserWidth,
                                savedMaxOppWidth,
                                savedPixelsPerDay,
                                currentBrowserWidth: browserW
                            });
                        }

                        // Values appear valid
                        if (savedBrowserWidth > 0 && savedPixelsPerDay > 0) {
                            // If browser size changed, scale the values
                            if (Math.abs(browserW - savedBrowserWidth) > 50) {
                                const scaleFactor = browserW / savedBrowserWidth;
                                usablePixelsPerDay = savedPixelsPerDay * scaleFactor;
                                usableMaxWidth = savedMaxOppWidth * scaleFactor;
                            } else {
                                // No scaling needed
                                usablePixelsPerDay = savedPixelsPerDay;
                                usableMaxWidth = savedMaxOppWidth;
                            }
                        }
                    } else {
                        // Legacy cookie with a different format
                        if (debug_events) {
                            console.log('Found legacy cookie format, using default values');
                        }
                    }
                } catch (e) {
                    console.error('Error parsing ratio cookie:', e);
                }
            }

            // Set the values
            pixelsPerDayRef.current = usablePixelsPerDay;
            maxOpportunityWidth.current = usableMaxWidth;
            lastBrowserWidth.current = browserW;
            loadedInitialValue.current = true;

            // Save the cookie with version to establish new format
            setCookie('sc_ratio_version', '2', 300);
            setCookie('sc_ratio_txt',
                browserW + ',' +
                maxOpportunityWidth.current + ',' +
                pixelsPerDayRef.current,
                300);

            if (debug_events) {
                console.log('Initialized pixelsPerDay:', pixelsPerDayRef.current);
            }
        }
    }, [browserW]);

    // Update pixelsPerDay when a larger opportunity window is seen
    const updatePixelsPerDay = (oppWidth, daysOut) => {
        // Skip updates during opportunity loading unless window is larger than before
        if (opportunityLoading.current && oppWidth <= maxOpportunityWidth.current) {
            return false;
        }

        // Only update if this window is larger than what we've seen before
        // This is the key part - only update from larger windows
        if (oppWidth > maxOpportunityWidth.current && oppWidth >= minReliableWidth.current) {
            // Calculate new pixelsPerDay
            const newPixelsPerDay = oppWidth / daysOut;

            if (debug_events) {
                console.log('Updating pixelsPerDay:', {
                    oldMaxWidth: maxOpportunityWidth.current,
                    newMaxWidth: oppWidth,
                    oldPixelsPerDay: pixelsPerDayRef.current,
                    newPixelsPerDay,
                    daysOut
                });
            }

            // Update stored values
            maxOpportunityWidth.current = oppWidth;
            pixelsPerDayRef.current = newPixelsPerDay;

            // Save to cookie for persistence
            setCookie('sc_ratio_txt',
                browserW + ',' +
                maxOpportunityWidth.current + ',' +
                pixelsPerDayRef.current,
                300);

            return true;
        }

        return false;
    };

    useEffect(() => {
        let xx0 = 0;
        let xx1 = 0;
        let c = 0;

        let date0 = props.startDate;
        let date1 = incrementDate(props.startDate, props.daysOut - 1);

        let first_date_seasonal_chart = '';
        let last_date_seasonal_chart = '';
        if (props.consolidatedSeasonalData.length > 0) {
            first_date_seasonal_chart = props.consolidatedSeasonalData[0][0];
            last_date_seasonal_chart = props.consolidatedSeasonalData[props.consolidatedSeasonalData.length - 1][0];
        }

        if (first_date_seasonal_chart !== '' && props.startDate < first_date_seasonal_chart) {
            let sd = props.startDate.substring(0, 10);
            let y = parseInt(sd.substring(0, 4)) + 1;
            date0 = y.toString() + sd.substring(4, 10);
            date1 = incrementDate(date0, props.daysOut - 1);
        }
        else if (first_date_seasonal_chart !== '' && props.startDate >= last_date_seasonal_chart) {
            let sd = props.startDate.substring(0, 10);
            let y = parseInt(sd.substring(0, 4)) - 1;
            date0 = y.toString() + sd.substring(4, 10);
            date1 = incrementDate(date0, props.daysOut - 1);
        }

        props.consolidatedSeasonalData.forEach((r) => {
            if (r[0] === date0) xx0 = c;
            if (r[0] === date1) xx1 = c;
            c++;
        });

        if (xx1 === 0) xx1 = c;
        SetX0(xx0);
        SetX1(xx1);

        // Flag that we're loading a new opportunity
        opportunityLoading.current = true;

        // Reset the flag after a short delay to allow for initial rendering
        setTimeout(() => {
            opportunityLoading.current = false;
        }, 500);

        SetOppDivLTWH([0, 0, 0, 0, 0]); // resetting the div for interactive sizing of opp window
        lastValidPosition.current = { x: 0, y: 0, width: 0, height: 0 };

    }, [props.startDate, props.symbol, props.daysOut, props.seasonalYears, props.consolidatedSeasonalData, props.janDecDateRange]);

    var xAxisFont = 12;
    var yAxisFont = 12;
    var questionDisplay = 'none';
    var doubleArrowDisplay = 'none';
    var showTitleDiv = 'none';

    var scstatHeight = '92%';
    var linechartControlsHeight = '8%';

    var chartHeight = '95%';
    var statsHeight = '5%';
    var statsWidth = '100%';

    var svFont = '7vw';
    var showChartTitle = true;
    var caretSize = '30';
    var resizerWidth = '5px';
    var oppDivBackgroundColor = tc.oppWindowBg;
    var div1W = '20%';
    var div2W = '60%';
    var div3W = '20%';

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { div1W = '30%'; div2W = '63%'; div3W = '7%'; }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { }

    if (rdd.isMobile) {
        caretSize = '20';
        doubleArrowDisplay = 'flex';
        questionDisplay = 'flex';
        resizerWidth = '50%';
        oppDivBackgroundColor = tc.oppWindowBgActive;
        svFont = '10vw';
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
        doubleArrowDisplay = 'flex';
        questionDisplay = 'flex';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) caretSize = '40';
    if (rdd.isMobile) {
        if (rdd.isTablet) {
            if (browserH > browserW) {
                caretSize = '30';
                questionDisplay = 'flex';
                doubleArrowDisplay = 'flex';
                xAxisFont = browserW / 55;
                yAxisFont = browserW / 50;
                showTitleDiv = 'flex';
                chartHeight = '90%';
                statsHeight = '10%';
                linechartControlsHeight = '12%';
                scstatHeight = '88%';
                showChartTitle = false;
            }
            else {
                questionDisplay = 'none';
                xAxisFont = browserW / 75;
                yAxisFont = browserW / 75;
                svFont = '7vw';
            }
        }
        else {
            showTitleDiv = 'flex';
            chartHeight = '90%';
            statsHeight = '10%';
            linechartControlsHeight = '12%';
            scstatHeight = '88%';
            showChartTitle = false;
        }
    }

    // console.log('ppppppppppppppppppppppppppppppppppppppppppppppprops.chartData=',props.chartData);

    const data = {
        labels: props.chartLabels,
        datasets: [
            { fill: true },
            {
                borderWidth: 2,
                pointBorderWidth: 0.1,
                data: props.chartData,
                backgroundColor: tc.lineFill,
                borderColor: tc.lineColor,
            },
        ],
    };

    const highlightBox = {
        drawTime: "afterDatasetsDraw",
        display: true,
        type: "box",
        xMin: x0,
        xMax: x1,
        backgroundColor: tc.oppWindowBg,

        enter(event) {
            if (debug_events) console.log('event:annotation:enter');
            let divX = event.element['x'];
            let divY = event.element['y'];
            let oppHeight = event.element['height'];
            let oppWidth = event.element['width'];
            let controlDivHeight = document.getElementsByClassName('seasonal-chart-controls')[0]?.['offsetHeight'] || 0;
            let statsDivHeight = document.getElementsByClassName('seasonal-chart-stats')[0]?.['offsetHeight'] || 0;

            // Store these values for future reference
            lastValidPosition.current = {
                x: divX,
                y: statsDivLoc === 'above' ? divY + controlDivHeight + statsDivHeight : divY + controlDivHeight,
                width: oppWidth,
                height: oppHeight
            };

            // Apply the new position
            if (statsDivLoc === 'above') {
                SetOppDivLTWH([divX, divY + controlDivHeight + statsDivHeight, oppWidth, oppHeight]);
            } else {
                SetOppDivLTWH([divX, divY + controlDivHeight, oppWidth, oppHeight]);
            }

            let oppWidthValid = true;
            if (x0 < 0 || x1 >= 365) oppWidthValid = false;

            if (debug_events) {
                console.log('Annotation enter:', {
                    oppWidth,
                    daysOut: props.daysOut,
                    pixelsPerDay: pixelsPerDayRef.current,
                    maxOpportunityWidth: maxOpportunityWidth.current,
                    calculatedPPD: oppWidth / props.daysOut,
                    oppWidthValid
                });
            }

            // Only update pixelsPerDay if this is a valid opportunity window and not during loading
            if (oppWidthValid && !opportunityLoading.current) {
                updatePixelsPerDay(oppWidth, props.daysOut);
            }

            needsRepositioning.current = false;
            if (rdd.isAndroid) props.swiper.enabled = false;
        },
        leave(event) {
            if (rdd.isAndroid) {
                props.swiper.enabled = true;
                SetOppDivLTWH([0, 0, 0, 0, 0]);
            }
            if (debug_events) console.log('event:annotation:leave');
        }
    };

    const options = {
        animation: {
            duration: 0
        },
        maintainAspectRatio: false,
        responsive: true,
        scales: {
            y: {
                display: false,
                ticks: {
                    font: { size: yAxisFont },
                    callback: function (val, index) { return val + '%'; },
                }
            },

            x: {
                ticks: {
                    color: tc.tickColor,
                    font: { size: xAxisFont },
                    callback: function (val) {
                        return this.getLabelForValue(val).substring(5);
                    },
                },
                // min:data['datasets'][1]['data'][0][0].substring(5)
                // min: data?.['datasets']?.[1]?.['data']?.[0]?.[0]?.substring(5) ?? currentYear+'-01-01'
            }
        },
        plugins: {
            legend: { display: false },
            title: { display: false, text: props.chartTitle },
            annotation: {
                display: false,
                annotations: {
                    box1: highlightBox,
                }
            }
        },
        // Handle resizing properly
        onResize: function (chart, size) {
            needsRepositioning.current = true;

            // Schedule a redraw of the opportunity window
            setTimeout(() => {
                if (oppDivLTWH[2] > 0 && lastValidPosition.current.width > 0) {
                    // Calculate new position based on pixelsPerDay and daysOut
                    const newWidth = props.daysOut * pixelsPerDayRef.current;
                    const scaleFactor = size.width / (size.previousWidth || size.width);

                    const newPosition = [
                        lastValidPosition.current.x * scaleFactor,
                        lastValidPosition.current.y,
                        newWidth,
                        lastValidPosition.current.height,
                        0
                    ];

                    SetOppDivLTWH(newPosition);
                }
            }, 150);
        }
    };

    const doubleLeftArrow = (event) => {
        props.chartTo(0);
    };

    // Permanent watermark plugin - draws on every chart render
    const watermarkPlugin = {
        id: 'watermarkPlugin',
        afterDraw: (chart) => {
            const ctx = chart.ctx;
            const chartArea = chart.chartArea;
            ctx.save();
            ctx.font = 'bold 14px Arial';
            ctx.fillStyle = props.UITheme === 'dark' ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.18)';
            ctx.textAlign = 'right';
            ctx.textBaseline = 'bottom';
            ctx.fillText('TradeWave.AI', chartArea.right - 10, chartArea.bottom - 8);
            ctx.restore();
        },
    };

    const handleHelpClicked = () => {
        props.SetVideosBoxVisible(true);
    };

    const linechartControlsStyle = {
        height: linechartControlsHeight,
        display: "flex",
        width: '100%',
        backgroundColor: tc.controlBar,
        alignItems: 'center',
        justifyContent: props.seasonalBarChartData.length > 0 ? 'center' : 'left',
    };

    const oppDivStyle = {
        left: oppDivLTWH[0],
        top: oppDivLTWH[1],
        width: oppDivLTWH[2],
        height: oppDivLTWH[3],
        right: oppDivLTWH[4],
        backgroundColor: oppDivBackgroundColor,
    };

    const handleExport = () => {
        props.SetShowWatermark(true);
        props.SetExportImage(true);
    };

    useEffect(() => {
        const resizeableEle = ref.current;
        if (!resizeableEle) return;

        const styles = window.getComputedStyle(resizeableEle);
        let width = oppDivLTWH[2];
        let x = 0;

        // Validate resize operations to ensure they stay within bounds
        const isValidResizeOperation = (newWidth) => {
            return newWidth >= minDaysOut * activePPDRef.current &&
                newWidth <= maxDaysOut * activePPDRef.current;
        };

        const onMouseEnter = () => {
            if (debug_events) console.log('event:onMouseEnter:');
            props.swiper.enabled = false;
        };

        const onMouseLeave = () => {
            if (debug_events) console.log('event:onMouseLeave:');
            if (rdd.isIOS) {
                SetOppDivLTWH([0, 0, 0, 0, 0]);
            }
            props.swiper.enabled = true;
        };

        const onMouseMoveRightResize = (event) => {
            if (debug_events) console.log('event:onMouseMoveRightResize:', event.type);
            let cx = 0;
            if (event.type === "touchstart" || event.type === "touchmove") cx = event.touches[0].clientX;
            else cx = event.clientX;

            const dx = cx - x;
            x = cx;

            // Calculate new width and apply constraints
            const newWidth = width + dx;

            // Only apply if it's within bounds
            if (isValidResizeOperation(newWidth)) {
                width = newWidth;
                resizeableEle.style.width = `${width}px`;
            }
        };

        const onMouseUpRightResizeOperations = async (days) => {
            // Apply min/max constraints
            days = Math.max(minDaysOut, Math.min(maxDaysOut, days));

            // Check if days has changed significantly enough to update
            let daysChanged = (Math.abs(days - props.daysOut) <= 1) ? false : true;

            if (daysChanged) {
                // Calculate precise width without rounding
                const exactWidth = days * activePPDRef.current;

                // Set the width of the element - this is the visual representation
                resizeableEle.style.width = `${exactWidth}px`;

                // Update app state with the new daysOut
                props.SetDaysOut(days);
                props.SetRowIndexClicked(-1);
                props.SetMonthsAndQtrs('Months & Qtrs');
            }
            else if (rdd.isIOS) {
                SetOppDivLTWH([0, 0, 0, 0, 0]);
            }

            if (rdd.isMobile) {
                props.swiper.enabled = true;
                if (browserH > browserW && daysChanged) {
                    props.chartTo(0);
                }
            }
        };

        const onMouseUpRightResize = (event) => {
            if (debug_events) console.log('event:onMouseUpRightResize:', event.type);
            document.removeEventListener("mousemove", onMouseMoveRightResize);
            document.removeEventListener("mouseup", onMouseUpRightResize);
            document.removeEventListener("touchmove", onMouseMoveRightResize);
            document.removeEventListener("touchend", onMouseUpRightResize);

            // Get actual width without rounding
            const w = parseFloat(resizeableEle.style.width || width);

            // Calculate days based on current pixelsPerDay
            let days = Math.round(w / activePPDRef.current);

            if (debug_events) {
                console.log('Mouse up resize:', {
                    width: w,
                    days,
                    daysOut: props.daysOut,
                    pixelsPerDay: pixelsPerDayRef.current,
                    maxWidth: maxOpportunityWidth.current
                });
            }

            // Check if this width is larger than our previously recorded maximum
            // If so, update pixelsPerDay for better accuracy
            updatePixelsPerDay(w, days);

            onMouseUpRightResizeOperations(days);
        };

        const onMouseDownRightResize = (event) => {
            if (debug_events) console.log('event:onMouseDownRightResize:', event.type);
            let cx = 0;
            if (event.type === "touchstart" || event.type === "touchmove") cx = event.touches[0].clientX;
            else cx = event.clientX;

            x = cx;

            activePPDRef.current = getExactPPDFromChart() ?? pixelsPerDayRef.current;

            resizeableEle.style.left = styles.left;
            resizeableEle.style.right = null;
            document.addEventListener("mousemove", onMouseMoveRightResize, { passive: true });
            document.addEventListener("mouseup", onMouseUpRightResize, { passive: true });
            document.addEventListener("touchmove", onMouseMoveRightResize, { passive: true });
            document.addEventListener("touchend", onMouseUpRightResize, { passive: true });
        };

        const onMouseMoveLeftResize = (event) => {
            if (debug_events) console.log('event:onMouseMoveLeftResize:', event.type);
            let cx = 0;
            if (event.type === "touchstart" || event.type === "touchmove") cx = event.touches[0].clientX;
            else cx = event.clientX;

            const dx = cx - x;
            x = cx;

            // Calculate new width and apply constraints
            const newWidth = width - dx;

            // Only apply if it's within bounds
            if (isValidResizeOperation(newWidth)) {
                width = newWidth;
                resizeableEle.style.width = `${width}px`;
            }
        };


        const md = (d) => d.substring(5, 10);

        const bumpYear = (yyyy_mm_dd, deltaYears) => {
            const y = parseInt(yyyy_mm_dd.substring(0, 4), 10) + deltaYears;
            return y.toString() + yyyy_mm_dd.substring(4, 10);
        };

        const daysBetweenInclusive = (d0, d1) => {
            return Math.floor((Date.parse(d1) - Date.parse(d0)) / 86400000) + 1;
        };

        const isPE = (sy) => typeof sy === 'string' && sy.startsWith('pe');





        const onMouseUpLeftResize = (event) => {
            if (debug_events) console.log('event:onMouseUpLeftResize:', event.type);

            document.removeEventListener("mousemove", onMouseMoveLeftResize);
            document.removeEventListener("mouseup", onMouseUpLeftResize);
            document.removeEventListener("touchmove", onMouseMoveLeftResize);
            document.removeEventListener("touchend", onMouseUpLeftResize);

            // Get exact values
            const w = parseFloat(resizeableEle.style.width || width);

            // Calculate day change using pixelsPerDay
            let daysChg = Math.round((oppDivLTWH[0] - parseFloat(styles.left || 0)) / activePPDRef.current);

            // let new_opp_date = incrementDate(props.startDate, -daysChg);
            // let days = Math.round(w / pixelsPerDayRef.current);

            // // Update pixelsPerDay if this is a larger window
            // updatePixelsPerDay(w, days);

            // let daysChanged = (props.startDate === new_opp_date) ? false : true;
            // if (daysChanged) {
            //     let current_end_date = incrementDate(props.startDate, props.daysOut - 1);
            //     days = Math.floor((Date.parse(current_end_date) - Date.parse(new_opp_date)) / 86400000) + 1;
            // }

            const oldStart = props.startDate;
            const oldYear = parseInt(oldStart.substring(0, 4), 10);

            // Fixed right edge (must be anchored to the old state)
            const fixedEnd = incrementDate(oldStart, props.daysOut - 1);

            // Candidate new start from drag math
            let new_opp_date = incrementDate(oldStart, -daysChg);

            // Detect direction
            const movedForward = daysChg < 0;
            const movedBackward = daysChg > 0;

            // Determine if year must change when month-day wraps on Jan-Dec axis
            let yearDelta = parseInt(new_opp_date.substring(0, 4), 10) - oldYear;

            // If incrementDate did not change the year but the MM-DD wrapped, correct it
            if (yearDelta === 0) {
                const oldMD = md(oldStart);
                const newMD = md(new_opp_date);

                if (movedForward && newMD < oldMD) yearDelta = +1;
                else if (movedBackward && newMD > oldMD) yearDelta = -1;

                if (yearDelta !== 0) {
                    new_opp_date = bumpYear(new_opp_date, yearDelta);
                }
            }








            // Update pixelsPerDay if this is a larger window (keep your existing intent)
            let daysFromWidth = Math.round(w / activePPDRef.current);
            updatePixelsPerDay(w, daysFromWidth);

            // Recompute daysOut from fixed end (right edge anchored)
            let days = daysBetweenInclusive(new_opp_date, fixedEnd);

            // Clamp to allowed range
            days = Math.max(minDaysOut, Math.min(maxDaysOut, days));

            // Enforce minDaysOut by clamping start date only (since end is fixed)
            let maxStart = incrementDate(fixedEnd, -(minDaysOut - 1));
            if (new_opp_date > maxStart) {
                new_opp_date = maxStart;
                days = minDaysOut;

                const exactWidth = minDaysOut * activePPDRef.current;
                resizeableEle.style.width = `${Math.round(exactWidth)}px`;
            } else {
                // Keep the overlay width consistent with the computed day count
                const exactWidth = days * activePPDRef.current;
                resizeableEle.style.width = `${Math.round(exactWidth)}px`;
            }

            const daysChanged = (props.startDate !== new_opp_date);

            // Compute PE key, but do NOT apply it yet.
            // We'll apply it after SetStartDate so fetches don't use stale opp_start_date.
            let pendingPEKey = null;

            if (yearDelta !== 0 && props.PEselected && props.PEselected !== 'cons') {
                const cur = parseInt(props.PEselected.substring(2), 10);   // "pe2" -> 2
                const next = Math.max(0, Math.min(3, cur + yearDelta));
                const nextKey = `pe${next}`;
                if (nextKey !== props.PEselected) {
                    pendingPEKey = nextKey;
                }
            }



            if ((daysChanged && loggedinUser === '0') || (wpUserLevels.length === 1 && wpUserLevels[0] === '1')) {
                props.SetDialogType('free-register');
                props.SetInfoBoxVisible(true);
                SetOppDivLTWH([0, 0, 0, 0, 0]);
            }
            else {
                let retArray = userAccessToSelectedSecurity(props.securityTypeList2, props.selectedSecurity);
                if (retArray[0] === 'F') {
                    props.SetDialogType('free-register');
                    props.SetInfoBoxVisible(true);
                    SetOppDivLTWH([0, 0, 0, 0, 0]);  // snap chart window back to original (mirrors free-Ripple branch)
                    return;
                }

                props.SetRowIndexClicked(-1);

                // let endDate = incrementDate(props.startDate, props.daysOut);
                // let maxDate = incrementDate(endDate, -minDaysOut);

                if (daysChanged && new_opp_date > maxStart) {
                    new_opp_date = maxStart;
                    days = minDaysOut;

                    // Calculate precise width without rounding
                    const exactWidth = minDaysOut * activePPDRef.current;
                    resizeableEle.style.width = `${Math.round(exactWidth)}px`;
                }


                if (daysChanged) {
                    props.SetStartDate(new_opp_date);
                    props.SetDaysOut(days);
                    props.SetMonthsAndQtrs('Months & Qtrs');

                    // Only refresh the trend chart if the new start date falls outside
                    // the existing chart data range, otherwise just let the window move
                    const chartData = props.consolidatedSeasonalData;
                    const needsRefresh = !chartData || chartData.length === 0
                        || new_opp_date < chartData[0][0];
                    if (needsRefresh) {
                        const trend_start = incrementDate(new_opp_date, -trend_chart_left_gap_days);
                        props.SetTrendChartStartDate(trend_start);
                        props.SetConsolidatedSeasonalData([]);
                    }

                    // Apply PE year change if the year crossed into a different PE cycle
                    if (pendingPEKey) {
                        props.SetPEselected(pendingPEKey);
                    }

                }
                else {
                    if (rdd.isIOS) SetOppDivLTWH([0, 0, 0, 0, 0]);
                }

                if (rdd.isMobile) {
                    props.swiper.enabled = true;
                    if (browserH > browserW && daysChanged) {
                        props.chartTo(0);
                    }
                }
            }
        };

        const onMouseDownLeftResize = (event) => {
            if (debug_events) console.log('event:onMouseDownLeftResize:', event.type);
            let cx = 0;
            if (event.type === "touchstart" || event.type === "touchmove") cx = event.touches[0].clientX;
            else cx = event.clientX;

            x = cx;

            activePPDRef.current = getExactPPDFromChart() ?? pixelsPerDayRef.current;

            resizeableEle.style.right = styles.right;
            resizeableEle.style.left = null;
            document.addEventListener("mousemove", onMouseMoveLeftResize, { passive: true });
            document.addEventListener("mouseup", onMouseUpLeftResize, { passive: true });
            document.addEventListener("touchmove", onMouseMoveLeftResize, { passive: true });
            document.addEventListener("touchend", onMouseUpLeftResize, { passive: true });
        };

        if (resizeableEle) {
            resizeableEle.addEventListener("mouseenter", onMouseEnter, { passive: true });
            resizeableEle.addEventListener("mouseleave", onMouseLeave, { passive: true });
        }

        const resizerRight = refRight.current;
        if (resizerRight) {
            resizerRight.addEventListener("mousedown", onMouseDownRightResize, { passive: true });
            resizerRight.addEventListener("touchstart", onMouseDownRightResize, { passive: true });
        }

        const resizerLeft = refLeft.current;
        if (resizerLeft) {
            resizerLeft.addEventListener("mousedown", onMouseDownLeftResize, { passive: true });
            resizerLeft.addEventListener("touchstart", onMouseDownLeftResize, { passive: true });
        }

        return () => {
            if (resizeableEle) {
                resizeableEle.removeEventListener("mouseenter", onMouseEnter);
                resizeableEle.removeEventListener("mouseleave", onMouseLeave);
            }

            if (resizerRight) {
                if (!rdd.isAndroid) resizerRight.removeEventListener("mousedown", onMouseDownRightResize);
                resizerRight.removeEventListener("touchstart", onMouseDownRightResize);
            }

            if (resizerLeft) {
                if (!rdd.isAndroid) resizerLeft.removeEventListener("mousedown", onMouseDownLeftResize);
                resizerLeft.removeEventListener("touchstart", onMouseDownLeftResize);
            }
        };

    }, [props.swiper, oppDivLTWH[2], props.symbol, props.janDecDateRange, browserW, props.daysOut]);

    const jandecChanged = () => {
        let val = Number(props.seasonalYears) ? true : false;
        val = true;
        if (val === true) {
            // the following 2 lines were added to make non jan-dec trend chart display to always
            // start from 2 weeks before the opportunity start date props.startDate 3/2/2025


            let trend_chart_start_date = incrementDate(props.startDate, -trend_chart_left_gap_days); // set to 2 weeks before  - set in common 
            props.SetTrendChartStartDate(trend_chart_start_date)
            //------------------------------------------------------------------------------------
            props.SetJanDecDateRange(!props.janDecDateRange);
            props.SetConsolidatedSeasonalData([]);

        }
    };

    const yearsDisplay = () => {
        // Build PE label if a PE cycle is selected
        let peLabel = '';
        if (props.PEselected && props.PEselected !== 'cons') {
            const peNum = props.PEselected[2]; // "0", "1", "2", or "3"
            peLabel = peNum === '0' ? ' PE' : ` PE+${peNum}`;
        }

        if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
            // return props.seasonalYears + peLabel + ' Y Trend Chart ';
            return props.seasonalYears + peLabel + ' Year Trend Chart ';
        } else {
            return props.seasonalYears + peLabel + ' Year Trend Chart for ';
        }
    };

    const handleDRreport = () => {
        if (loggedinUser === '0') {
            props.SetDialogType('free-register');
            props.SetDialogProp({ title: 'Portfolio Manager', contentText: opp_dashboard_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
            props.SetInfoBoxVisible(true);
        }
        else {
            props.SetReportsDashVisible(true);
        }
    };



    // Handle browser width changes
    useEffect(() => {
        // If browser width has changed significantly, scale pixelsPerDay
        if (Math.abs(browserW - lastBrowserWidth.current) > 50) {
            const scaleFactor = browserW / lastBrowserWidth.current;

            if (debug_events) {
                console.log('Browser width changed:', {
                    oldWidth: lastBrowserWidth.current,
                    newWidth: browserW,
                    scaleFactor,
                    oldPixelsPerDay: pixelsPerDayRef.current,
                    oldMaxOpportunityWidth: maxOpportunityWidth.current
                });
            }

            // Scale both pixelsPerDay and maxOpportunityWidth
            pixelsPerDayRef.current = pixelsPerDayRef.current * scaleFactor;
            maxOpportunityWidth.current = maxOpportunityWidth.current * scaleFactor;

            // Save to cookie
            setCookie('sc_ratio_txt',
                browserW + ',' +
                maxOpportunityWidth.current + ',' +
                pixelsPerDayRef.current,
                300);

            if (debug_events) {
                console.log('Updated after browser resize:', {
                    newPixelsPerDay: pixelsPerDayRef.current,
                    newMaxOpportunityWidth: maxOpportunityWidth.current
                });
            }

            // Reset opportunity window
            if (oppDivLTWH[2] > 0) {
                SetOppDivLTWH([0, 0, 0, 0, 0]);
            }

            // Update last browser width
            lastBrowserWidth.current = browserW;
        }
    }, [browserW, oppDivLTWH]);



    // console.log('Line Chart Data:', data);
    // console.log('Line Chart Options:', options);
    // console.log('Chart X range:', { x0, x1 });
    // console.log('^^^^^^^^^^^^^^^^^^^^^^^data[0][0]=',data['datasets'][1]['data'][0][0])
    // console.log('^^^^^^^^^^^^^^^^^^^^^^^data[0][0]=',data['datasets'][1]['data'][0])

    // console.log('**************************************=',props.startDate,props.trendChartStartDate);


    return (
        <div className="seasonal-chart-parent" style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column' }} >

            {/* these divs are for interactive resizing of the opp windows */}
            <div ref={ref} className="seasonal-opp" style={oppDivStyle} >
                <div ref={refLeft} className="seasonal-opp-left-resizer" style={{ width: resizerWidth }}></div>
                <div ref={refRight} className="seasonal-opp-right-resizer" style={{ width: resizerWidth }}></div>
            </div>

            <div className="seasonal-chart-controls noselect" style={linechartControlsStyle}>

                <div style={{ backgroundColor: 'transparent', width: div1W, display: 'flex', alignItems: 'center' }}>

                    {!rdd.isMobile || (rdd.isMobile && rdd.isTablet && browserH < browserW) ?

                        <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                            <div theme="tw" >
                                {props.tooltipSW ? 'Portfolio Manager' : ''}
                            </div>
                        }>
                            <div style={{ backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }}>
                                <BsPencilSquare size={21} style={{ fill: "white", marginLeft: '10px', backgroundColor: 'transparent' }} onClick={handleDRreport} />
                            </div>
                        </Tippy>
                        : null
                    }

                    {(rdd.isMobile && !rdd.isTablet) || (rdd.isTablet && browserH > browserW)

                        ? <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', paddingLeft: '1vw' }} onClick={doubleLeftArrow} >
                            <FaAngleDoubleLeft size={caretSize} style={{ fill: "white", display: doubleArrowDisplay }} onClick={doubleLeftArrow} />
                        </div>
                        : props.seasonalBarChartData.length > 0 ?
                            <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                <div theme="tw" >
                                    {props.tooltipSW ? 'Export Strategy Barchart and the Trend Chart as Jpeg' : ''}
                                </div>
                            }>
                                <div style={{ height: '100%', width: '10%', display: 'flex', alignItems: 'center', justifyContent: 'left', marginLeft: '10px' }} onClick={doubleLeftArrow} >
                                    <BsDownload size={20} style={{ fill: "white" }} onClick={handleExport} />
                                </div>
                            </Tippy>
                            :
                            <div style={{ height: '100%', width: '10%', display: 'flex', alignItems: 'center', justifyContent: 'left', marginLeft: '10px' }} onClick={doubleLeftArrow} >
                            </div>
                    }

                    {props.seasonalBarChartData.length > 0 ?
                        <div style={{ fontSize: globalTextSize, marginLeft: '3vw', paddingRight: '3vw' }}>
                            <CheckBox tooltipContent={props.tooltipSW ? 'b,By default, the Trend Chart date range starts 2 months ago from today rounded to the first of the month.  When checkbox is selected, seasonal chart dates range is from Jan 1 to dec 31.' : ''} label="Jan-Dec" cbChanged={jandecChanged} checked={props.janDecDateRange} />
                        </div>
                        :
                        <div style={{ fontSize: globalTextSize }}>
                        </div>
                    }

                </div>

                <div style={{ backgroundColor: 'transparent', width: div2W, padding: "10px" }}>

                    {props.seasonalBarChartData.length > 0 ?
                        <div style={{ height: '100%', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent' }}>
                            <Tippy disabled={!props.tooltipSW} placement={'bottom'} content={
                                <div theme="tw" >
                                    {props.tooltipSW ? 'TradeWave Trend Charts show the overall average trend of the financial instrument by normalizing and averaging the financial instrument yearly price charts.  The overall trend of the chart shows the average trend of the instrument during that time of the year. Make sure to look at sharpe-ratio of any date range selected to understand the overall stability of the profits for the date range.' : ''}
                                </div>
                            }>
                                <span style={{ color: tc.textOnControl, fontSize: infoTextSize, whiteSpace: 'nowrap' }}>

                                    {/* {yearsDisplay()}&nbsp;  <span style={{ color: UIcolors(loggedinUser)['security_name'], fontSize: infoTextSize, fontWeight: 'bold' }}> {companyName}</span> */}
                                    {/* {yearsDisplay()}&nbsp;  <span style={{ color: UIcolors(loggedinUser)['security_name'], fontSize: infoTextSize, fontWeight: 'bold' }}>{props.symbol}</span> */}
                                    {/* {yearsDisplay()}&nbsp;  {(!rdd.isMobile || (rdd.isMobile && rdd.isTablet && browserH < browserW)) && <span style={{ color: UIcolors(loggedinUser)['security_name'], fontSize: infoTextSize, fontWeight: 'bold' }}>{props.company}</span>} */}
                                    {yearsDisplay()}&nbsp;  <span style={{ color: UIcolors(loggedinUser)['security_name'], fontSize: infoTextSize, fontWeight: 'bold' }}>{(rdd.isMobile && !rdd.isTablet) || (rdd.isTablet && browserH > browserW) ? props.symbol : props.company}</span>
                                    {/* 4/5/2025  */}
                                    {!rdd.isMobile && <span style={{ color: 'red', fontSize: "1vw", paddingLeft: '10px' }}>{props.tradeActive ? "ACTIVE" : ""}</span>}
                                </span>

                            </Tippy>
                        </div>
                        :
                        <div style={{ height: '100%', width: '70%', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent' }}></div>
                    }

                </div>

                {!rdd.isMobile || (rdd.isMobile && rdd.isTablet && browserH < browserW) ?
                    <div style={{ width: div3W, display: 'flex', alignItems: 'center', backgroundColor: 'transparent', justifyContent: 'center' }}>

                        <Tippy placement={'top'} content={
                            <div theme="tw" >
                                {'Trend Chart'}
                            </div>
                        }>

                            <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }}>
                                <BsFillCircleFill size={12} style={{ fill: "red" }} />
                            </div>
                        </Tippy>

                        <Tippy placement={'top'} content={
                            <div theme="tw" >
                                {'Wave Stats'}
                            </div>
                        }>

                            <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }} onClick={() => props.chartTo(1)}>
                                <BsFillCircleFill size={12} style={{ fill: "white" }} />
                            </div>
                        </Tippy>

                        <Tippy placement={'top'} content={
                            <div theme="tw" >
                                {'Price Chart'}
                            </div>
                        }>

                            <div style={{ marginLeft: '1vw', display: 'flex', alignItems: 'center', width: '20%' }} onClick={() => props.chartTo(2)}>
                                <BsFillCircleFill size={12} style={{ fill: "white" }} />
                            </div>
                        </Tippy>

                    </div>
                    :
                    <div style={{ width: div3W, display: 'flex', alignItems: 'center', backgroundColor: 'transparent', justifyContent: 'right', paddingRight: '2vw' }}>
                        <BsQuestionCircle size={questionSize} style={{ fill: "white", display: questionDisplay }} onClick={handleHelpClicked} />
                    </div>
                }

            </div>

            {props.chartData.length > 0 ?
                <div className="seasonal-scstats" style={{ height: scstatHeight, backgroundColor: 'purple' }}>
                    <div className="seasonal-linechart" style={{ height: chartHeight, backgroundColor: UIcolors(loggedinUser, props.UITheme)['background_seasonal_chart'], borderLeft: '1px solid ' + tc.border }}>
                        <Line ref={chartRef} data={data} options={options} plugins={[watermarkPlugin]} />
                    </div>
                    <SeasonalChartStats height={statsHeight} width={statsWidth} {...props} />
                </div>
                :
                <div className="seasonal-linechart" style={{ height: chartHeight, backgroundColor: UIcolors(loggedinUser, props.UITheme)['background_seasonal_chart'], borderLeft: '1px solid ' + tc.border, userSelect: 'none' }}>
                    <div className='barchart-background'><span style={{ fontSize: svFont, color: tc.watermark }} >{brand['seasonal chart']}</span></div>
                </div>
            }

        </div>
    );

}
export default SeasonalChart;    