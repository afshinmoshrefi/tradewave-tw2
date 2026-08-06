import React, { useContext, useEffect, useState, useRef, useCallback } from "react";
import PopulatePortfolio from './PopulatePortfolio';
import PortfolioSettings from './PortfolioSettings';
import WatchlistSettings from './WatchlistSettings';
import SeasonalBarChart from './SeasonalBarChart';
import TradeInstrument from './TradeInstrument';
import StockLineChart from './StockLineChart';
import SeasonalChart from './SeasonalChart';
import TradeDetail from './TradeDetail';
import AIScorePanel from './AIScorePanel';
import BottomPanelTabs, { getBottomPanelId, getBottomPanelTabId } from './BottomPanelTabs';
import AIScoresPopup from './AIScoresPopup';
import InfoPopup from './InfoPopup';
import OppTable from './OppTable';
import AddGC from './AddGC';

import ReportsDashboard from './ReportsDashboard';
import PublishArticle from "./PublishArticle";
import InfoPopupHelp from './InfoPopupHelp';
import HelpPanelPopup from './HelpPanelPopup';
import SelectBox from './SelectBox';
import CheckBox from './CheckBox';
import Settings from './Settings';
import SecuritiesGroupSettings from './SecuritiesGroupSettings';
import Chatbot from './Chatbot';
import OppNote from "./OppNote";
import AutoTrade from "./AutoTrade";
import TradeReport from "./PortfolioTradeReport";
import TradeInstrumentReport from "./TradeInstrumentReport";
import TestGIS from './TestGIS';
import './styles/DesktopLayout.css';
import { UserContext } from './UserContext';
import { AiOutlineDollarCircle } from "react-icons/ai";
import { BsFillCircleFill, BsSun, BsMoon, BsListUl } from "react-icons/bs";
import { SlSettings } from "react-icons/sl";
import { toggle_off_64, toggle_on_64 } from './Common';
import { settings_dialog_content } from './Common';
import { incrementDate } from './Common';
import { Swiper, SwiperSlide } from "swiper/react";
import html2canvas from "html2canvas";
import "swiper/swiper.min.css";
import "swiper/components/pagination/pagination.min.css";
import "swiper/components/navigation/navigation.min.css";
import SwiperCore, { Pagination, Navigation, Virtual } from 'swiper/core';
import { getCookie, setCookie, appserverURL } from './Common';
import { LiaToggleOffSolid, LiaToggleOnSolid } from "react-icons/lia";
import { DarkBGColor, LightBGColor, themeColors } from './Common'
import { tierHasAI } from './Common'
import { lsSet } from './Common'
import { BAR_CHART_EXCURSION_STYLES } from './barChartExcursion'
import { BsPlus, BsTrash3 } from "react-icons/bs";
import { GrEdit } from "react-icons/gr";
import Tippy from '@tippyjs/react'
import {
    getBottomSlideIndex,
    getBottomSlideName,
    getBottomSlides,
    resolveBottomSlidePresentation,
} from './bottomSlides';





const SWIPE_WITH_MOUSE = false;

const legacyBottomSlideName = value => {
    const index = Number.parseInt(value, 10);
    if (index === 1) return 'wave_stats';
    if (index === 2) return 'price_chart';
    return 'trend_chart';
};

SwiperCore.use([Pagination, Navigation, Virtual]);

const DesktopLayout = (props) => {
    const [initialSlide, SetInitialSlide] = useState(() => {
        // let bottomWindowNumber = getCookie('WindowNumber');
        // if (bottomWindowNumber === null) return "1";
        // return bottomWindowNumber;
    });
    const [activeBottomSlide, SetActiveBottomSlide] = useState(() => {
        if (window.location.search && window.location.search !== '?set=on') {
            return legacyBottomSlideName(props.initialWindowNum);
        }
        const semantic = getCookie('BottomWindowName');
        if (['trend_chart', 'wave_stats', 'ai_scores', 'price_chart'].includes(semantic)) return semantic;
        return legacyBottomSlideName(props.initialWindowNum);
    });
    const [showAIScoresGuide, SetShowAIScoresGuide] = useState(false);

    const [coverOpp, SetCoverOpp] = useState(false);
    const [coverBottomCharts, SetCoverBottomCharts] = useState(false);
    const [coverTopCharts, SetCoverTopCharts] = useState(false);

    const [chatbotHeightPct, SetChatbotHeightPct] = useState(30);
    const isDragging = useRef(false);
    const oppChatContainerRef = useRef(null);

    const DEFAULT_LEFT_NAV_PCT = 30;
    const [leftNavWidthPct, SetLeftNavWidthPct] = useState(() => {
        try {
            const saved = localStorage.getItem('leftNavWidthPct');
            if (saved) return Math.min(40, Math.max(20, parseFloat(saved)));
        } catch (e) {}
        return DEFAULT_LEFT_NAV_PCT;
    });
    const isResizingNav = useRef(false);
    const navWidthRef = useRef(leftNavWidthPct); // tracks latest value across closure
    const appContainerRef = useRef(null);
    const swiperRef = useRef(null); // ref so onMouseUp closure can call swiper.update()
    const lastInitialWindowNumRef = useRef(props.initialWindowNum);

    const DEFAULT_TOP_CHART_PCT = 50;
    const [topChartHeightPct, SetTopChartHeightPct] = useState(DEFAULT_TOP_CHART_PCT);
    const isResizingTopChart = useRef(false);
    const topChartHeightRef = useRef(DEFAULT_TOP_CHART_PCT);
    const rightContentRef = useRef(null);

    const [showLeftNavSettings, SetShowLeftNavSettings] = useState(false);
    const [settingsCategory, SetSettingsCategory] = useState('general');
    const gearIconRef = useRef(null);
    const settingsPanelRef = useRef(null);
    const [settingsDragPos, setSettingsDragPos] = useState(null);
    const settingsDragRef = useRef({ active: false, offsetX: 0, offsetY: 0 });

    const [priceChartType, SetPriceChartType] = useState(() => {
        // Button keys are 'line' / 'candle' / 'ohlc'. Older builds wrote 'candlestick'
        // for the default which matches none of the buttons (settings shows no
        // selection, chart falls through to OHLC). Migrate stale values + default
        // to 'candle' so the price chart always has a known type.
        const stored = localStorage.getItem('priceChartType');
        if (stored === 'line' || stored === 'candle' || stored === 'ohlc') return stored;
        localStorage.setItem('priceChartType', 'candle');
        return 'candle';
    });

    // Securities Groups inline state
    const [secGroupsTab, SetSecGroupsTab] = useState('groups'); // 'groups', 'published', 'admin'
    const [sgMessage, SetSgMessage] = useState('');
    const [sgMsgColor, SetSgMsgColor] = useState('red');
    const [newListName, SetNewListName] = useState('');
    const [newListResourceId, SetNewListResourceId] = useState('');
    const [newListSymbols, SetNewListSymbols] = useState('');
    const [editingList, SetEditingList] = useState(null);
    const [editSymbols, SetEditSymbols] = useState('');
    const [lbPulse, setLbPulse] = useState(false);    // toolbar lightbulb attention pulse (fires on LessonBox close/invite/mute)
    // lbCalloutKind: null | 'reopen' | 'invite' | 'muted' - which anchored callout (if any) is
    // showing below the bulb. One kind at a time, all reusing the same pos/pulse mechanics -
    // 'reopen' (existing "Your lessons live here"), 'invite' (Gating v2 one-time existing-user
    // opt-in, from LessonBox's tw-lessonbox-invite), 'muted' (Gating v2 mute confirmation, from
    // tw-lessonbox-muted). LessonBox.js owns all the underlying persisted state (tw_lesson_*,
    // tw_onboard_dismissed); this toolbar only reacts to its window events.
    const [lbCalloutKind, setLbCalloutKind] = useState(null);
    const [lbPos, setLbPos] = useState(null);         // {left, top} of the anchored callout (sits just below the bulb)
    const bulbRef = useRef(null);
    const lbTimers = useRef([]);

    const { seasonalAppDivH, seasonalAppDivH2, rdd, loggedinUser, wpUserLevels, token } = useContext(UserContext);
    const tc = themeColors(props.UITheme);
    const userHasAITier = tierHasAI(wpUserLevels);
    const opportunityAIStateMatchesMarket = Boolean(
        props.opportunityAIState &&
        props.opportunityAIState.market === props.selectedSecurity
    );
    const aiEligibilityResolved = Boolean(
        opportunityAIStateMatchesMarket &&
        props.opportunityAIState.resolved === true
    );
    const hasAIScores = Boolean(
        userHasAITier &&
        aiEligibilityResolved &&
        opportunityAIStateMatchesMarket &&
        props.opportunityAIState.eligible === true &&
        props.opportunityAIState.enabled === true
    );
    const bottomSlides = getBottomSlides({ hasAIScores });
    const bottomSlidePresentation = resolveBottomSlidePresentation(activeBottomSlide, {
        hasAIScores,
        aiEligibilityResolved,
        fallback: 'wave_stats',
    });
    const visibleBottomSlide = bottomSlidePresentation.visibleSlide;
    const preserveRequestedBottomSlide = bottomSlidePresentation.preserveRequestedSlide;
    const publishedAISelection = props.opportunityAIState && props.opportunityAIState.selected;
    const publishedAISelectionMatchesViewer = Boolean(
        publishedAISelection &&
        String(publishedAISelection.symbol || '') === String(props.symbol || '') &&
        String(publishedAISelection.date || '') === String(props.startDate || '') &&
        Number.parseInt(publishedAISelection.daysOut, 10) === Number.parseInt(props.daysOut, 10)
    );
    const aiPanelViewModel = publishedAISelection && !publishedAISelectionMatchesViewer
        ? {
            ...props.opportunityAIState,
            selected: {
                symbol: props.symbol,
                date: props.startDate,
                daysOut: props.daysOut,
                direction: props.barChartLongOrShort,
            },
            loading: true,
            bundle: null,
            unavailableReason: '',
        }
        : props.opportunityAIState;

    const toggle_width = '2.2vw';
    const settingsSize = 18;

    // Show an anchored callout of the given kind just below the toolbar lightbulb, with the
    // usual attention pulse. autoHideMs === 0 leaves it up until the user dismisses it.
    const showLbCallout = useCallback((kind, autoHideMs) => {
        setLbPulse(true);
        lbTimers.current.push(setTimeout(() => setLbPulse(false), 6500));
        try {
            const r = bulbRef.current && bulbRef.current.getBoundingClientRect();
            if (r && r.width) {
                setLbPos({ left: Math.max(8, Math.round(r.left - 4)), top: Math.round(r.bottom + 8) });
                setLbCalloutKind(kind);
                if (autoHideMs) lbTimers.current.push(setTimeout(() => setLbCalloutKind(null), autoHideMs));
            }
        } catch (e) { /* noop */ }
    }, []);

    // Toolbar reactions to the LessonBox's own state changes (it owns all the persisted
    // onboarding/lesson state; this is pure window-event choreography).
    //   tw-lessonbox-closed  - draw the eye to the reopen lightbulb.
    //   tw-lessonbox-invite  - Gating v2: unenrolled, undismissed user gets a one-time opt-in.
    //   tw-lessonbox-muted   - Gating v2: confirms "Stop daily pop-ups" just fired.
    useEffect(() => {
        const onClosed = () => showLbCallout('reopen', 7000);
        const onInvite = () => showLbCallout('invite', 9000);
        const onMuted = () => showLbCallout('muted', 7000);
        window.addEventListener('tw-lessonbox-closed', onClosed);
        window.addEventListener('tw-lessonbox-invite', onInvite);
        window.addEventListener('tw-lessonbox-muted', onMuted);
        return () => {
            window.removeEventListener('tw-lessonbox-closed', onClosed);
            window.removeEventListener('tw-lessonbox-invite', onInvite);
            window.removeEventListener('tw-lessonbox-muted', onMuted);
            lbTimers.current.forEach(clearTimeout);
        };
    }, [showLbCallout]);

    // const showChatbot = true;




    let DivH = (rdd.isMobile) ? seasonalAppDivH2 : seasonalAppDivH;
    const appContainerStyle = {
        display: "flex",
        padding: "0px",
        margin: "0px",
        backgroundColor: tc.panelBg,
        height: DivH,
        width: "100vw",
        overflow: "hidden"
    };

    let resizeWindow = () => {
        window.scrollTo(0, 1);
    };

    useEffect(() => {
        const timer = setTimeout(function () {
            resizeWindow();
        }, 100);
        return () => clearTimeout(timer);
    }, []);

    const goToBottomSlide = useCallback((requestedSlide) => {
        const presentation = resolveBottomSlidePresentation(requestedSlide, {
            hasAIScores,
            aiEligibilityResolved,
            fallback: requestedSlide === 'ai_scores' ? 'wave_stats' : 'trend_chart',
        });
        const target = presentation.visibleSlide;
        const savedTarget = presentation.preserveRequestedSlide ? requestedSlide : target;
        const index = getBottomSlideIndex(target, { hasAIScores });
        const targetSwiper = swiperRef.current || props.swiper;
        if (index >= 0 && targetSwiper && typeof targetSwiper.slideTo === 'function') {
            targetSwiper.slideTo(index);
        }
        SetActiveBottomSlide(savedTarget);
        setCookie('BottomWindowName', savedTarget, 300);
        // Preserve rollback compatibility. Legacy builds know only 0/1/2.
        const legacyIndex = savedTarget === 'wave_stats' || savedTarget === 'ai_scores'
            ? 1
            : savedTarget === 'price_chart' ? 2 : 0;
        setCookie('WindowNumber', String(legacyIndex), 300);
    }, [hasAIScores, aiEligibilityResolved, props.swiper]);

    // Existing chart headers still call chartTo(0/1/2). Treat those numbers as
    // their old semantic destinations so "2" remains Price Chart after AI is inserted.
    const chartTo = useCallback((destination) => {
        const semantic = typeof destination === 'number'
            ? ['trend_chart', 'wave_stats', 'price_chart'][destination]
            : destination;
        goToBottomSlide(semantic);
    }, [goToBottomSlide]);

    useEffect(() => {
        const target = visibleBottomSlide;
        const index = getBottomSlideIndex(target, { hasAIScores });
        if (!preserveRequestedBottomSlide && target !== activeBottomSlide) {
            SetActiveBottomSlide(target);
            setCookie('BottomWindowName', target, 300);
        }
        const targetSwiper = swiperRef.current || props.swiper;
        if (index >= 0 && targetSwiper && targetSwiper.activeIndex !== index) {
            targetSwiper.slideTo(index);
        }
    }, [hasAIScores, activeBottomSlide, visibleBottomSlide, preserveRequestedBottomSlide, props.swiper]);

    useEffect(() => {
        if (
            props.initialWindowNum === undefined ||
            props.initialWindowNum === null ||
            lastInitialWindowNumRef.current === props.initialWindowNum
        ) return;
        lastInitialWindowNumRef.current = props.initialWindowNum;
        const requested = legacyBottomSlideName(props.initialWindowNum);
        if (window.location.search) goToBottomSlide(requested);
    }, [props.initialWindowNum, goToBottomSlide]);

    const handleDollarClicked = () => {
        window.open('/#pricing', '_blank');
    };

    const handleAMbutton = (n) => {
        if (n === 1) SetCoverOpp(!coverOpp);
        if (n === 2) SetCoverBottomCharts(!coverBottomCharts);
        if (n === 3) SetCoverTopCharts(!coverTopCharts);
    };

    const handleSecurityDivClicked = () => {
        // let elem = document.querySelector('.left-nav');
        // let rect = elem.getBoundingClientRect();
        // console.log(rect)
    };

    const handleTooltipSW = () => {
        const next = !props.tooltipSW;
        props.SetTooltipSW(next);
        lsSet('tw_tooltips', next);
    };

    const handleTheme = () => {

        if (props.UITheme === 'dark') {
            props.SetUITheme('light');
            props.SetBackgroundColor(LightBGColor)
            localStorage.setItem('UITheme', 'light');
        }
        else {
            props.SetUITheme('dark');
            props.SetBackgroundColor(DarkBGColor)
            localStorage.setItem('UITheme', 'dark');
        }
    }

    useEffect(() => {
        if (props.exportImage) {
            const timeoutid = setTimeout(() => {
                html2canvas(document.getElementById("right-content"), {
                    allowTaint: true,
                    useCORS: true
                }).then(canvas => {
                    const imgData = canvas.toDataURL('image/jpeg');
                    var link = document.createElement('a');
                    link.download = props.downloadImageName;
                    link.href = imgData;
                    link.click();
                    props.SetShowWatermark(false);
                }).catch(err => {
                    console.log('Export image error:', err);
                    props.SetShowWatermark(false);
                });
            }, 2000);
        }
        props.SetExportImage(false);
    }, [props.exportImage]);

    useEffect(() => {
        const onMouseMove = (e) => {
            // chatbot vertical resize
            if (isDragging.current && oppChatContainerRef.current) {
                const rect = oppChatContainerRef.current.getBoundingClientRect();
                const mouseY = e.clientY - rect.top;
                const pct = ((rect.height - mouseY) / rect.height) * 100;
                SetChatbotHeightPct(Math.min(75, Math.max(15, pct)));
            }
            // left-nav horizontal resize
            if (isResizingNav.current && appContainerRef.current) {
                const rect = appContainerRef.current.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const pct = Math.min(40, Math.max(20, (mouseX / rect.width) * 100));
                navWidthRef.current = pct;
                SetLeftNavWidthPct(pct);
            }
            // right-side top/bottom chart vertical resize
            if (isResizingTopChart.current && rightContentRef.current) {
                const rect = rightContentRef.current.getBoundingClientRect();
                const mouseY = e.clientY - rect.top;
                const pct = Math.min(80, Math.max(20, (mouseY / rect.height) * 100));
                topChartHeightRef.current = pct;
                SetTopChartHeightPct(pct);
            }
        };
        const onMouseUp = () => {
            isDragging.current = false;
            if (isResizingNav.current) {
                isResizingNav.current = false;
                localStorage.setItem('leftNavWidthPct', String(navWidthRef.current));
            }
            if (isResizingTopChart.current) {
                isResizingTopChart.current = false;
                swiperRef.current?.update();
            }
        };
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        return () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        };
    }, []);

    // When #right-content changes width, tell Swiper to re-measure so its slides
    // get new pixel widths - Chart.js ResizeObservers then pick up the change naturally.
    useEffect(() => {
        const rightContent = document.getElementById('right-content');
        if (!rightContent) return;
        const observer = new ResizeObserver(() => {
            swiperRef.current?.update();
        });
        observer.observe(rightContent);
        return () => observer.disconnect();
    }, []);

    const handleResizerMouseDown = (e) => {
        isDragging.current = true;
        e.preventDefault();
    };

    const handleNavResizerMouseDown = (e) => {
        isResizingNav.current = true;
        e.preventDefault();
    };

    const handleTopChartResizerMouseDown = (e) => {
        isResizingTopChart.current = true;
        e.preventDefault();
    };

    const handleLeftNavGear = (e) => {
        e.stopPropagation();
        SetShowLeftNavSettings(prev => !prev);
    };

    useEffect(() => {
        if (!showLeftNavSettings) return;
        const onMouseDown = (e) => {
            const inGear = gearIconRef.current?.contains(e.target);
            const inPanel = settingsPanelRef.current?.contains(e.target);
            if (!inGear && !inPanel) SetShowLeftNavSettings(false);
        };
        document.addEventListener('mousedown', onMouseDown);
        return () => document.removeEventListener('mousedown', onMouseDown);
    }, [showLeftNavSettings]);

    // drag support for settings panel
    useEffect(() => {
        const onMouseMove = (e) => {
            if (!settingsDragRef.current.active) return;
            const x = Math.max(0, Math.min(window.innerWidth - 200, e.clientX - settingsDragRef.current.offsetX));
            const y = Math.max(0, Math.min(window.innerHeight - 60, e.clientY - settingsDragRef.current.offsetY));
            setSettingsDragPos({ x, y });
        };
        const onMouseUp = () => { settingsDragRef.current.active = false; };
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
        return () => {
            window.removeEventListener('mousemove', onMouseMove);
            window.removeEventListener('mouseup', onMouseUp);
        };
    }, []);

    const handleSettingsTitleMouseDown = (e) => {
        if (e.detail === 2) { setSettingsDragPos(null); return; } // double-click resets
        if (!settingsPanelRef.current) return;
        const rect = settingsPanelRef.current.getBoundingClientRect();
        settingsDragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top };
        e.preventDefault();
    };

    // ── Securities Groups helpers ──
    const allGroups = (props.securityTypeList2 || []).filter(x => x.value !== '' && x.label !== 'More...');
    const isGroupHidden = (groupValue) => (props.securitiesPrefs?.hidden_groups || []).includes(groupValue);
    const isPublishedEnabled = (plName) => (props.securitiesPrefs?.enabled_published || []).includes(plName);

    const saveSGPrefs = (newPrefs) => {
        let asURL = appserverURL();
        fetch(`${asURL}/set_securities_prefs?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newPrefs)
        })
            .then(res => res.json())
            .then(data => { if (data['securities_prefs']) props.SetSecuritiesPrefs(data['securities_prefs']); })
            .catch(err => console.log('save securities prefs error:', err.message));
    };

    const toggleGroup = (groupValue) => {
        let hidden = [...(props.securitiesPrefs?.hidden_groups || [])];
        if (hidden.includes(groupValue)) hidden = hidden.filter(v => v !== groupValue);
        else hidden.push(groupValue);
        const newPrefs = { ...props.securitiesPrefs, hidden_groups: hidden };
        props.SetSecuritiesPrefs(newPrefs);
        saveSGPrefs(newPrefs);
    };

    const togglePublished = (plName) => {
        let enabled = [...(props.securitiesPrefs?.enabled_published || [])];
        if (enabled.includes(plName)) enabled = enabled.filter(v => v !== plName);
        else enabled.push(plName);
        const newPrefs = { ...props.securitiesPrefs, enabled_published: enabled };
        props.SetSecuritiesPrefs(newPrefs);
        saveSGPrefs(newPrefs);
    };

    const resetSGToDefault = () => {
        const newPrefs = { hidden_groups: [], enabled_published: [] };
        props.SetSecuritiesPrefs(newPrefs);
        saveSGPrefs(newPrefs);
        SetSgMessage('Reset to default'); SetSgMsgColor('green');
    };

    const resourceOptions = Object.entries(props.resourceObj || {}).map(([id, name]) => ({ id: parseInt(id), value: id, label: name }));

    const handleCreatePublishedList = () => {
        if (!newListName.trim()) { SetSgMessage('Enter a list name'); SetSgMsgColor('red'); return; }
        if (!newListResourceId) { SetSgMessage('Select a securities group'); SetSgMsgColor('red'); return; }
        if (!newListSymbols.trim()) { SetSgMessage('Enter symbols separated by commas'); SetSgMsgColor('red'); return; }
        let symbols = newListSymbols.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
        let asURL = appserverURL();
        fetch(`${asURL}/create_published_list?token=${token}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: newListName.trim(), resource_id: newListResourceId, symbols })
        })
            .then(res => res.json())
            .then(data => {
                if (data['error'] === 'duplicate_name') { SetSgMessage('A list with this name already exists'); SetSgMsgColor('red'); }
                else if (data['published_lists']) {
                    props.SetPublishedLists(data['published_lists']);
                    SetNewListName(''); SetNewListSymbols(''); SetNewListResourceId('');
                    SetSgMessage('Published list created'); SetSgMsgColor('green');
                }
            })
            .catch(() => { SetSgMessage('Error creating list'); SetSgMsgColor('red'); });
    };

    const handleDeletePublishedList = (name) => {
        let asURL = appserverURL();
        fetch(`${asURL}/delete_published_list/${encodeURIComponent(name)}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => { if (data['published_lists']) { props.SetPublishedLists(data['published_lists']); SetSgMessage(`Deleted: ${name}`); SetSgMsgColor('green'); } })
            .catch(() => { SetSgMessage('Error deleting list'); SetSgMsgColor('red'); });
    };

    const handleCsvUpload = (e, target) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            const text = ev.target.result;
            const lines = text.split(/[\n\r]+/).filter(l => l.trim());
            if (lines.length === 0) return;
            const strip = s => s.trim().replace(/^["']|["']$/g, '');
            // detect header row and find the symbol/ticker column
            const headerCells = lines[0].split(/[,\t]/).map(strip);
            const symbolCol = headerCells.findIndex(h => /^(symbol|ticker)$/i.test(h));
            const hasHeader = symbolCol >= 0;
            const colIdx = hasHeader ? symbolCol : 0;
            const dataLines = hasHeader ? lines.slice(1) : lines;
            const symbols = dataLines
                .map(line => strip(line.split(/[,\t]/)[colIdx] || ''))
                .filter(s => s)
                .map(s => s.toUpperCase());
            const unique = [...new Set(symbols)];
            if (target === 'new') SetNewListSymbols(unique.join(', '));
            else SetEditSymbols(unique.join(', '));
            SetSgMessage(`Loaded ${unique.length} symbols from CSV`); SetSgMsgColor('green');
        };
        reader.readAsText(file);
        e.target.value = '';
    };

    const handleStartEdit = (pl) => { SetEditingList(pl.name); SetEditSymbols(pl.symbols.join(', ')); };

    const handleSaveEdit = (name) => {
        let symbols = editSymbols.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
        let asURL = appserverURL();
        fetch(`${asURL}/update_published_list?token=${token}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, updates: { symbols } })
        })
            .then(res => res.json())
            .then(data => { if (data['published_lists']) { props.SetPublishedLists(data['published_lists']); SetEditingList(null); SetSgMessage('List updated'); SetSgMsgColor('green'); } })
            .catch(() => { SetSgMessage('Error updating list'); SetSgMsgColor('red'); });
    };

    const handleToggleEnabled = (pl) => {
        let asURL = appserverURL();
        fetch(`${asURL}/update_published_list?token=${token}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: pl.name, updates: { enabled: !pl.enabled } })
        })
            .then(res => res.json())
            .then(data => { if (data['published_lists']) props.SetPublishedLists(data['published_lists']); })
            .catch(err => console.log('toggle enabled error:', err.message));
    };

    const handle_Settings_clicks = () => {
        if (loggedinUser === '0') {
            props.SetDialogType('info-box');
            props.SetDialogProp({ title: 'Settings', contentText: settings_dialog_content, button1Text: '', button2Text: 'Close', coverDivColor: 'rgb(222,222,222,0)' });
            props.SetInfoBoxVisible(true);
        } else {
            props.SetShowSettings(true);
        }
    };

    const handle_slide_change = (swiperCore) => {
        // Handle slide change if needed
    };

    return (
        <div ref={appContainerRef} style={appContainerStyle}>
            {/* Anchored lightbulb callout - sits just BELOW the toolbar lightbulb (never covers it).
                Kind-switched: 'reopen' (existing), 'invite' (Gating v2 one-time opt-in, two actions),
                'muted' (Gating v2 mute confirmation). Same position/styling for all three. */}
            {lbCalloutKind && lbPos &&
                <div
                    style={{ position: 'fixed', top: lbPos.top + 'px', left: lbPos.left + 'px', zIndex: 100000, maxWidth: '250px', background: 'linear-gradient(180deg,#1F1A2C,#1A1626)', color: '#F2EFF8', border: '1px solid rgba(167,139,250,0.4)', borderRadius: '10px', padding: '10px 13px', fontSize: '12.5px', lineHeight: 1.45, boxShadow: '0 12px 34px rgba(0,0,0,0.6)' }}
                >
                    {lbCalloutKind === 'reopen' &&
                        <div
                            onClick={() => { setLbCalloutKind(null); setLbPulse(false); window.dispatchEvent(new CustomEvent('tw-lessonbox-open')); }}
                            title="Reopen your lessons"
                            style={{ cursor: 'pointer' }}
                        >
                            <div style={{ color: '#C4B2FF', fontWeight: 700, marginBottom: '2px' }}>&#8593; Your lessons live here</div>
                            Click the lightbulb above - or click this - to reopen them.
                        </div>
                    }
                    {lbCalloutKind === 'invite' &&
                        <div>
                            <div style={{ color: '#C4B2FF', fontWeight: 700, marginBottom: '4px' }}>&#8593; New: 7 Quick Daily Lessons</div>
                            <div style={{ marginBottom: '9px' }}>Learn to read seasonal patterns in a few minutes a day. Want the tour?</div>
                            <div style={{ display: 'flex', gap: '14px' }}>
                                <span
                                    onClick={() => { setLbCalloutKind(null); setLbPulse(false); window.dispatchEvent(new CustomEvent('tw-lessonbox-open')); }}
                                    style={{ cursor: 'pointer', color: '#C4B2FF', fontWeight: 700 }}
                                >Start the tour</span>
                                <span
                                    onClick={() => setLbCalloutKind(null)}
                                    style={{ cursor: 'pointer', opacity: 0.75 }}
                                >No thanks</span>
                            </div>
                        </div>
                    }
                    {lbCalloutKind === 'muted' &&
                        <div onClick={() => setLbCalloutKind(null)} style={{ cursor: 'pointer' }}>
                            <div style={{ color: '#C4B2FF', fontWeight: 700, marginBottom: '2px' }}>Muted</div>
                            Your lessons stay right here whenever you want them.
                        </div>
                    }
                </div>
            }
            {coverOpp && <div className='opp-cover'></div>}
            {coverBottomCharts && <div className='bottom-chart-cover'></div>}
            {coverTopCharts && <div className='top-chart-cover'></div>}

            {props.videosBoxVisible && <HelpPanelPopup onClose={() => props.SetVideosBoxVisible(false)} />}
            {props.reportsDashVisible && <ReportsDashboard {...props} />}

            {/* forceGC: the Remind me bell's Edit link always means the calendar dialog,
                even when an '&' autotrade portfolio happens to be the current selection */}
            {props.addGCVisible && props.selectedPortfolio[0] === '&' && !props.googleCalendarDict['forceGC'] && <TradeInstrument {...props} />}
            {props.addGCVisible && (props.selectedPortfolio[0] !== '&' || props.googleCalendarDict['forceGC']) && <AddGC {...props} />}


            {props.showPortfolioSettings && <PortfolioSettings {...props} />}
            {props.showWatchlistSettings && <WatchlistSettings {...props} />}

            {props.showOppNote && <OppNote {...props} />}
            {props.showArticlePublish && <PublishArticle {...props} />}

            {props.showSettings && <Settings {...props} />}
            {/* SecuritiesGroupSettings is now inline in the settings panel */}

            {props.showPopulatePortfolio && <PopulatePortfolio {...props} />}

            {props.showAutoTrade && <AutoTrade {...props} />}

            {props.showTradeReport && <TradeReport {...props} />}

            {props.showTradeInstrumentReport && <TradeInstrumentReport {...props} />}
            {props.infoBoxVisible && <InfoPopup {...props} />}



            <div className='left-nav' style={{ width: `${leftNavWidthPct}%`, position: 'relative' }}>
                <div className='security-selection' style={{ backgroundColor: tc.securitySelectionBg, overflow: 'hidden' }} onClick={handleSecurityDivClicked}>
                    {/* left side: shrinks and clips as left-nav narrows; font scales with container width */}
                    <div style={{ flex: 1, minWidth: 0, height: "100%", backgroundColor: 'transparent', display: "flex", alignItems: 'center', overflow: 'hidden', userSelect: 'none', fontSize: `${Math.min(0.85, Math.max(0.55, leftNavWidthPct * 0.028))}vw` }}>
                        {/* settings gear icon */}
                        <div ref={gearIconRef} style={{ flexShrink: 0, display: 'flex', alignItems: 'center', paddingLeft: '6px', paddingRight: '4px', cursor: 'pointer' }} onClick={handleLeftNavGear}>
                            <SlSettings size={settingsSize} style={{ fill: showLeftNavSettings ? 'cyan' : 'white' }} />
                        </div>
                        {/* watchlist icon */}
                        {loggedinUser !== '0' &&
                            <Tippy content="Watchlist Settings" placement="bottom">
                                <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', paddingRight: '4px', cursor: 'pointer' }} onClick={() => props.SetShowWatchlistSettings(true)}>
                                    <BsListUl size={settingsSize} style={{ fill: props.showWatchlistSettings ? 'cyan' : 'white' }} />
                                </div>
                            </Tippy>
                        }
                        <div style={{ paddingTop: '2px', display: 'flex', alignItems: 'center', backgroundColor: 'transparent', flexShrink: 1, minWidth: 0, overflow: 'hidden' }} >
                            <span style={{ color: "white", margin: "4px 6px", whiteSpace: 'nowrap', flexShrink: 1 }} >tooltips</span>
                            {
                                props.tooltipSW
                                    ? <img src={"data:image/png;base64, " + toggle_on_64} alt="" style={{ width: toggle_width, flexShrink: 0 }} onClick={handleTooltipSW} />
                                    : <img src={"data:image/png;base64, " + toggle_off_64} alt="" style={{ width: toggle_width, flexShrink: 0 }} onClick={handleTooltipSW} />
                            }
                            {/* Lessons lightbulb - reopens the onboarding LessonBox (it docks here on desktop
                                instead of a bottom bulb so it never covers the charts). */}
                            {loggedinUser !== '0' &&
                                <Tippy content="Open your lessons" placement="bottom">
                                    <div
                                        style={{ position: 'relative', flexShrink: 0, display: 'flex', alignItems: 'center', paddingLeft: '8px', cursor: 'pointer' }}
                                        onClick={(e) => { e.stopPropagation(); setLbCalloutKind(null); setLbPulse(false); window.dispatchEvent(new CustomEvent('tw-lessonbox-open')); }}
                                    >
                                        <style>{'@keyframes twTbBulb{0%{transform:scale(1);filter:drop-shadow(0 0 4px rgba(167,139,250,0.6))}50%{transform:scale(1.3);filter:drop-shadow(0 0 14px rgba(167,139,250,1))}100%{transform:scale(1);filter:drop-shadow(0 0 4px rgba(167,139,250,0.6))}}'}</style>
                                        <span ref={bulbRef} role="img" aria-label="Open your lessons" style={{ fontSize: '1.1vw', lineHeight: 1, display: 'inline-block', filter: 'drop-shadow(0 0 5px rgba(167,139,250,0.85))', animation: lbPulse ? 'twTbBulb 1.3s ease-in-out 5' : 'none' }}>&#128161;</span>
                                    </div>
                                </Tippy>
                            }
                            <div style={{ paddingLeft: '4px', display: "flex", alignItems: "center", flexShrink: 0, backgroundColor: 'transparent' }} onClick={handle_Settings_clicks}>
                                {(false && (props.loggedinUser === '1' || props.loggedinUser === '22' || props.loggedinUser === '16' || props.loggedinUser === '190')) &&
                                    <SlSettings size={settingsSize} style={{ fill: "white", backgroundColor: "transparent", verticalAlign: 'bottom' }} />
                                }
                            </div>
                            {props.upgradeMessage != '' && !props.showUpgradeBanner &&
                                <div
                                    style={{ paddingLeft: '4px', display: "flex", alignItems: "center", flexShrink: 0, backgroundColor: 'transparent' }}
                                    onClick={() => props.SetShowUpgradeBanner(true)}
                                >
                                    <span style={{ color: "white", fontSize: '1vw' }}>✨</span>
                                </div>
                            }
                        </div>
                    </div>

                    {/* right side: SelectBox, never shrinks away */}
                    <div style={{ flexShrink: 0, marginRight: "12px", display: "flex", alignItems: "center", justifyContent: 'flex-end', userSelect: 'none' }}>
                        <SelectBox tooltipContent={props.tooltipSW ? 'r,Set Securities Group' : ''} optionList={props.securityTypeList} name="securityTypeList" value={props.selectedSecurityDisplay || props.selectedSecurity} sbChanged={props.selectboxChanged} />
                    </div>
                </div>

                {showLeftNavSettings && (
                    <div ref={settingsPanelRef} style={{
                        position: settingsDragPos ? 'fixed' : 'absolute',
                        ...(settingsDragPos
                            ? { top: settingsDragPos.y, left: settingsDragPos.x }
                            : { top: '4%', left: 0 }),
                        zIndex: 2000,
                        backgroundColor: tc.panelBg,
                        border: '1px solid ' + tc.border,
                        borderRadius: '10px',
                        width: '540px',
                        boxShadow: '0 8px 28px rgba(0,0,0,0.5)',
                        color: tc.text,
                        display: 'flex',
                        flexDirection: 'column',
                        overflow: 'hidden',
                    }}>
                        {/* panel title */}
                        <div style={{ fontSize: '13px', fontWeight: '700', color: tc.text, padding: '14px 18px 12px', borderBottom: '1px solid ' + tc.border, letterSpacing: '0.3px', cursor: 'move' }}
                            onMouseDown={handleSettingsTitleMouseDown}>
                            Settings
                        </div>

                        <div style={{ display: 'flex', minHeight: '220px' }}>
                            {/* ── Left menu ── */}
                            <div style={{ width: '140px', flexShrink: 0, borderRight: '1px solid ' + tc.border, paddingTop: '6px' }}>
                                {[
                                    { key: 'general', label: 'General' },
                                    { key: 'barchart', label: 'Bar Chart' },
                                    { key: 'pricechart', label: 'Price Chart' },
                                    { key: 'opptable', label: 'Opp Table' },
                                    { key: 'secgroups', label: 'Securities Groups' },
                                ].map(cat => (
                                    <div
                                        key={cat.key}
                                        onClick={() => {
                                            SetSettingsCategory(cat.key);
                                        }}
                                        style={{
                                            padding: '8px 12px',
                                            fontSize: '11px',
                                            cursor: 'pointer',
                                            color: tc.text,
                                            fontWeight: settingsCategory === cat.key ? '700' : '400',
                                            backgroundColor: settingsCategory === cat.key
                                                ? (props.UITheme === 'dark' ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)')
                                                : 'transparent',
                                            borderLeft: settingsCategory === cat.key ? '3px solid ' + (props.UITheme === 'dark' ? '#7aa2f7' : '#336') : '3px solid transparent',
                                        }}
                                    >
                                        {cat.label}
                                    </div>
                                ))}
                            </div>

                            {/* ── Right content ── */}
                            <div style={{ flex: 1, padding: '14px 16px', overflow: 'auto' }}>

                                {/* ── General ── */}
                                {settingsCategory === 'general' && (
                                    <div>
                                        <Tippy placement="right" content={<div>Switch between light and dark color theme</div>}>
                                            <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px' }}>
                                                Appearance
                                            </div>
                                        </Tippy>
                                        <div style={{
                                            display: 'flex',
                                            backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)',
                                            borderRadius: '8px',
                                            padding: '3px',
                                            gap: '3px',
                                        }}>
                                            <button
                                                onClick={() => { props.SetUITheme('light'); props.SetBackgroundColor(LightBGColor); localStorage.setItem('UITheme', 'light'); }}
                                                style={{
                                                    flex: 1, padding: '9px 4px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                                                    backgroundColor: props.UITheme === 'light' ? '#ffffff' : 'transparent',
                                                    color: props.UITheme === 'light' ? '#1a1a1a' : tc.text,
                                                    fontWeight: props.UITheme === 'light' ? '600' : '400',
                                                    fontSize: '12px',
                                                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '5px',
                                                    boxShadow: props.UITheme === 'light' ? '0 1px 5px rgba(0,0,0,0.18)' : 'none',
                                                    transition: 'background 0.15s, box-shadow 0.15s',
                                                }}
                                            >
                                                <BsSun size={15} />
                                                Light
                                            </button>
                                            <button
                                                onClick={() => { props.SetUITheme('dark'); props.SetBackgroundColor(DarkBGColor); localStorage.setItem('UITheme', 'dark'); }}
                                                style={{
                                                    flex: 1, padding: '9px 4px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                                                    backgroundColor: props.UITheme === 'dark' ? '#3a3a5c' : 'transparent',
                                                    color: tc.text,
                                                    fontWeight: props.UITheme === 'dark' ? '600' : '400',
                                                    fontSize: '12px',
                                                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '5px',
                                                    boxShadow: props.UITheme === 'dark' ? '0 1px 5px rgba(0,0,0,0.35)' : 'none',
                                                    transition: 'background 0.15s, box-shadow 0.15s',
                                                }}
                                            >
                                                <BsMoon size={15} />
                                                Dark
                                            </button>
                                        </div>

                                        {/* ── Price Lines ── */}
                                        <Tippy placement="right" content={<div>Remove all saved price level lines from every chart</div>}>
                                            <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px', marginTop: '20px' }}>
                                                Price Lines
                                            </div>
                                        </Tippy>
                                        <button
                                            onClick={() => {
                                                const cookies = document.cookie.split(';')
                                                cookies.forEach(c => {
                                                    const name = c.split('=')[0].trim()
                                                    if (name.startsWith('pl_')) setCookie(name, '', -1)
                                                })
                                                try {
                                                    Object.keys(localStorage).forEach(k => {
                                                        if (k.startsWith('pl_')) localStorage.removeItem(k)
                                                    })
                                                } catch {}
                                                // Notify any mounted StockLineChart to drop its in-memory levels;
                                                // without this, the persistence effect re-writes them on next render.
                                                try { window.dispatchEvent(new CustomEvent('pl_clear_all')) } catch {}
                                            }}
                                            style={{
                                                padding: '8px 16px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                                                backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)',
                                                color: tc.text, fontSize: '12px', fontWeight: '500',
                                                transition: 'background 0.15s',
                                            }}
                                        >
                                            Clear All Price Lines
                                        </button>

                                        <Tippy placement="right" content={<div>Show default watchlist symbols when clicking the symbol input</div>}>
                                            <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px', marginTop: '20px' }}>
                                                Watchlist
                                            </div>
                                        </Tippy>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                            <CheckBox name="watchlistOnFocus" cbChanged={() => {
                                                let newVal = !props.showWatchlistOnFocus
                                                props.SetShowWatchlistOnFocus(newVal)
                                                setCookie('show_watchlist_on_focus', newVal.toString(), 365)
                                            }} checked={props.showWatchlistOnFocus} />
                                            <span style={{ fontSize: '12px', color: tc.text }}>Show Watchlist on Focus</span>
                                        </div>
                                    </div>
                                )}

                                {/* ── Bar Chart ── */}
                                {settingsCategory === 'barchart' && (
                                    <div>
                                        <Tippy placement="right" content={<div>Choose how MFE and MAE are drawn around each annual return bar</div>}>
                                            <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px' }}>
                                                MFE / MAE Display
                                            </div>
                                        </Tippy>
                                        <div
                                            role="radiogroup"
                                            aria-label="MFE and MAE bar chart display"
                                            style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}
                                        >
                                            {[
                                                {
                                                    key: BAR_CHART_EXCURSION_STYLES.FILLED,
                                                    label: 'Filled Extensions',
                                                    description: 'Current view - shaded distance from the close to each extreme.',
                                                },
                                                {
                                                    key: BAR_CHART_EXCURSION_STYLES.TICKS,
                                                    label: 'High / Low Ticks',
                                                    description: 'Thin green and pink marks at the exact extreme levels.',
                                                },
                                                {
                                                    key: BAR_CHART_EXCURSION_STYLES.NEEDLE,
                                                    label: 'Range Needles',
                                                    description: 'A theme-aware vertical line spanning the selected range.',
                                                },
                                            ].map(({ key, label, description }) => {
                                                const selected = props.barChartExcursionStyle === key;
                                                return (
                                                    <button
                                                        key={key}
                                                        type="button"
                                                        role="radio"
                                                        aria-checked={selected}
                                                        onClick={() => props.SetBarChartExcursionStyle(key)}
                                                        style={{
                                                            width: '100%',
                                                            padding: '9px 11px',
                                                            border: '1px solid ' + (selected
                                                                ? (props.UITheme === 'dark' ? '#7aa2f7' : '#336')
                                                                : tc.border),
                                                            borderRadius: '7px',
                                                            cursor: 'pointer',
                                                            textAlign: 'left',
                                                            backgroundColor: selected
                                                                ? (props.UITheme === 'dark' ? '#3a3a5c' : '#ffffff')
                                                                : (props.UITheme === 'dark' ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'),
                                                            color: tc.text,
                                                            boxShadow: selected ? '0 1px 5px rgba(0,0,0,0.18)' : 'none',
                                                        }}
                                                    >
                                                        <div style={{ fontSize: '12px', fontWeight: selected ? '700' : '500' }}>
                                                            {label}{key === BAR_CHART_EXCURSION_STYLES.FILLED ? ' (Default)' : ''}
                                                        </div>
                                                        <div style={{ marginTop: '3px', fontSize: '10px', lineHeight: 1.35, opacity: 0.65 }}>
                                                            {description}
                                                        </div>
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}

                                {/* ── Price Chart ── */}
                                {settingsCategory === 'pricechart' && (
                                    <div>
                                        <Tippy placement="right" content={<div>Choose how price data is displayed on the chart</div>}>
                                            <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px' }}>
                                                Chart Type
                                            </div>
                                        </Tippy>
                                        <div style={{
                                            display: 'flex',
                                            backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)',
                                            borderRadius: '8px',
                                            padding: '3px',
                                            gap: '3px',
                                        }}>
                                            {[
                                                { key: 'line', label: 'Line' },
                                                { key: 'candle', label: 'Candle' },
                                                { key: 'ohlc', label: 'OHLC' },
                                            ].map(({ key, label }) => (
                                                <button
                                                    key={key}
                                                    onClick={() => { SetPriceChartType(key); localStorage.setItem('priceChartType', key); }}
                                                    style={{
                                                        flex: 1, padding: '9px 4px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                                                        backgroundColor: priceChartType === key ? (props.UITheme === 'dark' ? '#3a3a5c' : '#ffffff') : 'transparent',
                                                        color: priceChartType === key ? (props.UITheme === 'dark' ? '#ffffff' : '#1a1a1a') : tc.text,
                                                        fontWeight: priceChartType === key ? '600' : '400',
                                                        fontSize: '12px',
                                                        boxShadow: priceChartType === key ? '0 1px 5px rgba(0,0,0,0.18)' : 'none',
                                                        transition: 'background 0.15s, box-shadow 0.15s',
                                                    }}
                                                >
                                                    {label}
                                                </button>
                                            ))}
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>Switch between daily and weekly price bars on the current price chart</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px' }}>
                                                    Timeframe
                                                </div>
                                            </Tippy>
                                            <div style={{
                                                display: 'flex',
                                                backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)',
                                                borderRadius: '8px',
                                                padding: '3px',
                                                gap: '3px',
                                            }}>
                                                {[
                                                    { key: 'daily', label: 'Daily' },
                                                    { key: 'weekly', label: 'Weekly' },
                                                ].map(({ key, label }) => (
                                                    <button
                                                        key={key}
                                                        onClick={() => props.SetPriceChartTimeframe(key)}
                                                        style={{
                                                            flex: 1, padding: '9px 4px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                                                            backgroundColor: props.priceChartTimeframe === key ? (props.UITheme === 'dark' ? '#3a3a5c' : '#ffffff') : 'transparent',
                                                            color: props.priceChartTimeframe === key ? (props.UITheme === 'dark' ? '#ffffff' : '#1a1a1a') : tc.text,
                                                            fontWeight: props.priceChartTimeframe === key ? '600' : '400',
                                                            fontSize: '12px',
                                                            boxShadow: props.priceChartTimeframe === key ? '0 1px 5px rgba(0,0,0,0.18)' : 'none',
                                                            transition: 'background 0.15s, box-shadow 0.15s',
                                                        }}
                                                    >
                                                        {label}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>How much history to show on the current price chart</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px' }}>
                                                    Chart Range
                                                </div>
                                            </Tippy>
                                            <div style={{
                                                display: 'flex',
                                                backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)',
                                                borderRadius: '8px',
                                                padding: '3px',
                                                gap: '3px',
                                            }}>
                                                {[
                                                    { key: '3m', label: '3M' },
                                                    { key: '6m', label: '6M' },
                                                    { key: '1y', label: '1Y' },
                                                    { key: '2y', label: '2Y' },
                                                ].map(({ key, label }) => (
                                                    <button
                                                        key={key}
                                                        onClick={() => props.SetChartRange(key)}
                                                        style={{
                                                            flex: 1, padding: '9px 4px', border: 'none', borderRadius: '6px', cursor: 'pointer',
                                                            backgroundColor: props.chartRange === key ? (props.UITheme === 'dark' ? '#3a3a5c' : '#ffffff') : 'transparent',
                                                            color: props.chartRange === key ? (props.UITheme === 'dark' ? '#ffffff' : '#1a1a1a') : tc.text,
                                                            fontWeight: props.chartRange === key ? '600' : '400',
                                                            fontSize: '12px',
                                                            boxShadow: props.chartRange === key ? '0 1px 5px rgba(0,0,0,0.18)' : 'none',
                                                            transition: 'background 0.15s, box-shadow 0.15s',
                                                        }}
                                                    >
                                                        {label}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>Show or hide trading volume bars below the price chart</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Volume
                                                </div>
                                            </Tippy>
                                            <CheckBox
                                                label="Show Volume"
                                                cbChanged={() => props.SetShowVolume(!props.showVolume)}
                                                checked={props.showVolume}
                                                textSide="right"
                                                textColor={tc.text}
                                            />
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>Show historical and projected earnings announcement dates as markers on the price chart (US stocks only)</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Earnings Dates
                                                </div>
                                            </Tippy>
                                            <CheckBox
                                                label="Show Earnings"
                                                cbChanged={() => props.SetShowEarnings(!props.showEarnings)}
                                                checked={props.showEarnings}
                                                textSide="right"
                                                textColor={tc.text}
                                            />
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>Configure moving average overlays - toggle visibility, set period, type (SMA/EMA), line style, and color</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Moving Averages
                                                </div>
                                            </Tippy>
                                            {(props.maConfig || [])
                                                .map((ma, idx) => ({ ma, idx }))
                                                .sort((a, b) => a.ma.period - b.ma.period)
                                                .map(({ ma, idx }) => {
                                                const MA_COLORS = ['#c850c8', '#e8a838', '#38b8e8', '#48c848', '#e84848', '#888888'];
                                                const updateMA = (field, value) => {
                                                    const next = props.maConfig.map((m, i) => i === idx ? { ...m, [field]: value } : m);
                                                    props.SetMaConfig(next);
                                                };
                                                return (
                                                    <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '6px' }}>
                                                        <CheckBox
                                                            label=""
                                                            cbChanged={() => updateMA('enabled', !ma.enabled)}
                                                            checked={ma.enabled}
                                                            textSide="right"
                                                            textColor={tc.text}
                                                        />
                                                        <input
                                                            type="number"
                                                            value={ma.period}
                                                            onChange={(e) => {
                                                                const v = parseInt(e.target.value, 10);
                                                                if (v > 0) updateMA('period', v);
                                                            }}
                                                            style={{
                                                                width: '48px', padding: '2px 4px', fontSize: '11px',
                                                                backgroundColor: props.UITheme === 'dark' ? '#2a2a44' : '#f0f0f0',
                                                                color: tc.text, border: '1px solid ' + tc.border, borderRadius: '4px',
                                                                textAlign: 'center',
                                                            }}
                                                        />
                                                        <div style={{
                                                            display: 'flex',
                                                            backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)',
                                                            borderRadius: '4px', padding: '1px', gap: '1px',
                                                        }}>
                                                            {['sma', 'ema'].map(t => (
                                                                <button key={t}
                                                                    onClick={() => updateMA('type', t)}
                                                                    style={{
                                                                        padding: '2px 6px', border: 'none', borderRadius: '3px', cursor: 'pointer',
                                                                        fontSize: '10px', fontWeight: ma.type === t ? '700' : '400',
                                                                        backgroundColor: ma.type === t ? (props.UITheme === 'dark' ? '#3a3a5c' : '#ffffff') : 'transparent',
                                                                        color: ma.type === t ? (props.UITheme === 'dark' ? '#fff' : '#1a1a1a') : tc.text,
                                                                        boxShadow: ma.type === t ? '0 1px 3px rgba(0,0,0,0.18)' : 'none',
                                                                    }}
                                                                >{t.toUpperCase()}</button>
                                                            ))}
                                                        </div>
                                                        <div style={{
                                                            display: 'flex',
                                                            backgroundColor: props.UITheme === 'dark' ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.08)',
                                                            borderRadius: '4px', padding: '1px', gap: '1px',
                                                        }}>
                                                            {['solid', 'dashed'].map(d => (
                                                                <div key={d}
                                                                    onClick={() => updateMA('dash', d)}
                                                                    style={{
                                                                        padding: '2px 5px', cursor: 'pointer', borderRadius: '3px',
                                                                        backgroundColor: (ma.dash || 'solid') === d ? (props.UITheme === 'dark' ? '#3a3a5c' : '#ffffff') : 'transparent',
                                                                        boxShadow: (ma.dash || 'solid') === d ? '0 1px 3px rgba(0,0,0,0.18)' : 'none',
                                                                        display: 'flex', alignItems: 'center',
                                                                    }}
                                                                >
                                                                    <svg width="18" height="8" viewBox="0 0 18 8">
                                                                        <line x1="0" y1="4" x2="18" y2="4"
                                                                            stroke={(ma.dash || 'solid') === d ? tc.text : (props.UITheme === 'dark' ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.35)')}
                                                                            strokeWidth="2"
                                                                            strokeDasharray={d === 'dashed' ? '4,3' : 'none'}
                                                                        />
                                                                    </svg>
                                                                </div>
                                                            ))}
                                                        </div>
                                                        <div style={{ display: 'flex', gap: '3px' }}>
                                                            {MA_COLORS.map(c => (
                                                                <div key={c}
                                                                    onClick={() => updateMA('color', c)}
                                                                    style={{
                                                                        width: '12px', height: '12px', backgroundColor: c, cursor: 'pointer',
                                                                        borderRadius: '2px',
                                                                        border: ma.color === c ? '2px solid ' + tc.text : '1px solid transparent',
                                                                    }}
                                                                />
                                                            ))}
                                                        </div>
                                                    </div>
                                                );
                                            })}
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>Configure Bollinger Bands overlay - set period, standard deviation multiplier, fill, and color</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Bollinger Bands
                                                </div>
                                            </Tippy>
                                            {(() => {
                                                const bb = props.bbConfig || { enabled: false, period: 20, multiplier: 2, color: '#e8a838', fill: true };
                                                const BB_COLORS = ['#c850c8', '#e8a838', '#38b8e8', '#48c848', '#e84848', '#888888'];
                                                const updateBB = (field, value) => {
                                                    props.SetBbConfig({ ...bb, [field]: value });
                                                };
                                                return (
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                        <CheckBox
                                                            label=""
                                                            cbChanged={() => updateBB('enabled', !bb.enabled)}
                                                            checked={bb.enabled}
                                                            textSide="right"
                                                            textColor={tc.text}
                                                        />
                                                        <span style={{ fontSize: '10px', color: tc.text, opacity: 0.6 }}>Period</span>
                                                        <input
                                                            type="number"
                                                            value={bb.period}
                                                            onChange={(e) => {
                                                                const v = parseInt(e.target.value, 10);
                                                                if (v > 0) updateBB('period', v);
                                                            }}
                                                            style={{
                                                                width: '48px', padding: '2px 4px', fontSize: '11px',
                                                                backgroundColor: props.UITheme === 'dark' ? '#2a2a44' : '#f0f0f0',
                                                                color: tc.text, border: '1px solid ' + tc.border, borderRadius: '4px',
                                                                textAlign: 'center',
                                                            }}
                                                        />
                                                        <span style={{ fontSize: '10px', color: tc.text, opacity: 0.6 }}>StdDev</span>
                                                        <input
                                                            type="number"
                                                            step="0.1"
                                                            value={bb.multiplier}
                                                            onChange={(e) => {
                                                                const v = parseFloat(e.target.value);
                                                                if (v > 0) updateBB('multiplier', v);
                                                            }}
                                                            style={{
                                                                width: '40px', padding: '2px 4px', fontSize: '11px',
                                                                backgroundColor: props.UITheme === 'dark' ? '#2a2a44' : '#f0f0f0',
                                                                color: tc.text, border: '1px solid ' + tc.border, borderRadius: '4px',
                                                                textAlign: 'center',
                                                            }}
                                                        />
                                                        <CheckBox
                                                            label="Fill"
                                                            cbChanged={() => updateBB('fill', !bb.fill)}
                                                            checked={bb.fill}
                                                            textSide="right"
                                                            textColor={tc.text}
                                                        />
                                                        <div style={{ display: 'flex', gap: '3px' }}>
                                                            {BB_COLORS.map(c => (
                                                                <div key={c}
                                                                    onClick={() => updateBB('color', c)}
                                                                    style={{
                                                                        width: '12px', height: '12px', backgroundColor: c, cursor: 'pointer',
                                                                        borderRadius: '2px',
                                                                        border: bb.color === c ? '2px solid ' + tc.text : '1px solid transparent',
                                                                    }}
                                                                />
                                                            ))}
                                                        </div>
                                                    </div>
                                                );
                                            })()}
                                        </div>

                                        <div style={{ marginTop: '16px' }}>
                                            <Tippy placement="right" content={<div>Project the seasonal trend forward from the last close price as a dashed line on the price chart</div>}>
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Seasonal Projection
                                                </div>
                                            </Tippy>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                                <CheckBox
                                                    label="Show Projection"
                                                    cbChanged={() => props.SetShowProjection(!props.showProjection)}
                                                    checked={props.showProjection}
                                                    textSide="right"
                                                    textColor={tc.text}
                                                />
                                                <select
                                                    value={props.projectionPeriod}
                                                    onChange={(e) => props.SetProjectionPeriod(e.target.value)}
                                                    style={{
                                                        padding: '2px 4px', fontSize: '11px',
                                                        backgroundColor: props.UITheme === 'dark' ? '#2a2a44' : '#f0f0f0',
                                                        color: tc.text, border: '1px solid ' + tc.border, borderRadius: '4px',
                                                    }}
                                                >
                                                    <option value="14">2 Weeks</option>
                                                    <option value="30">1 Month</option>
                                                    <option value="60">2 Months</option>
                                                    <option value="90">3 Months</option>
                                                </select>
                                            </div>
                                            {props.maxAvailableYears > 0 && parseInt(props.seasonalYears, 10) !== props.maxAvailableYears && (
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '6px' }}>
                                                    <CheckBox
                                                        label={`Show Projection (${props.maxAvailableYears}-Y)`}
                                                        cbChanged={() => props.SetShowMaxProjection(!props.showMaxProjection)}
                                                        checked={props.showMaxProjection}
                                                        textSide="right"
                                                        textColor={tc.text}
                                                    />
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                {/* ── Opp Table ── */}
                                {settingsCategory === 'opptable' && (() => {
                                    const COL_META = {
                                        symbol:       { label: 'Ticker', desc: 'Symbol',              required: true },
                                        daysOut:      { label: 'Days',   desc: 'Pattern Length',      required: true },
                                        sharpe_ratio: { label: 'SR',     desc: 'Sharpe Ratio',        required: true },
                                        date:         { label: 'Date',   desc: 'Pattern Start Date',  required: false },
                                        lOrS:         { label: 'DIR',    desc: 'Long or Short',       required: false },
                                        avg_profit:   { label: 'AvgP',   desc: 'Average Profit',      required: false },
                                        avg_profit2:  { label: 'TWA',    desc: 'TradeWave Average',   required: false },
                                        sharpe_ratio2:{ label: 'TWR',    desc: 'TradeWave Ratio',     required: false },
                                        TL:           { label: 'TL',     desc: 'Trend Long Score',    required: false },
                                        price:        { label: 'Price',  desc: 'Real-time Price',     required: false },
                                        ml_score:     { label: 'AIS',    desc: 'AI return rank (0-100)', required: false },
                                        win_prob:     { label: 'Win%',   desc: 'AI chance of profit',   required: false },
                                        pred_return:  { label: 'PredR',  desc: 'Estimated ending return', required: false },
                                        pred_mfe:     { label: 'PMFE',   desc: 'Estimated best move',    required: false },
                                    };
                                    const order = props.columnOrder || Object.keys(COL_META);
                                    const AI_COLS = ['ml_score', 'win_prob', 'pred_return', 'pred_mfe'];
                                    const _settingsHasAI = tierHasAI(wpUserLevels);  // false -> mark AI cols locked
                                    const canSwap = (a, b) => {
                                        if (a < 0 || b < 0 || a >= order.length || b >= order.length) return false;
                                        return AI_COLS.includes(order[a]) === AI_COLS.includes(order[b]);
                                    };
                                    const moveCol = (idx, dir) => {
                                        const swapIdx = idx + dir;
                                        if (!canSwap(idx, swapIdx)) return;
                                        const newOrder = [...order];
                                        [newOrder[idx], newOrder[swapIdx]] = [newOrder[swapIdx], newOrder[idx]];
                                        props.SetColumnOrder(newOrder);
                                    };
                                    const DEFAULT_COL_ORDER = ['date', 'symbol', 'daysOut', 'lOrS', 'sharpe_ratio', 'avg_profit', 'avg_profit2', 'sharpe_ratio2', 'TL', 'price', 'ml_score', 'win_prob', 'pred_return', 'pred_mfe'];
                                    const isDefaultOrder = JSON.stringify(order) === JSON.stringify(DEFAULT_COL_ORDER);
                                    return (
                                    <div>
                                        <Tippy placement="right" content={<div>Choose which columns are visible and reorder them with the arrows</div>}>
                                            <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '10px' }}>
                                                Columns
                                            </div>
                                        </Tippy>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                            {order.map((key, idx) => {
                                                const col = COL_META[key];
                                                if (!col) return null;
                                                const arrowStyle = (disabled) => ({
                                                    cursor: disabled ? 'default' : 'pointer',
                                                    opacity: disabled ? 0.2 : 0.6,
                                                    fontSize: '12px',
                                                    lineHeight: '1',
                                                    userSelect: 'none',
                                                    color: tc.text,
                                                    padding: '1px 2px',
                                                });
                                                return (
                                                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0px', width: '16px', flexShrink: 0 }}>
                                                        <span
                                                            style={arrowStyle(!canSwap(idx, idx - 1))}
                                                            onClick={() => moveCol(idx, -1)}
                                                        >▲</span>
                                                        <span
                                                            style={arrowStyle(!canSwap(idx, idx + 1))}
                                                            onClick={() => moveCol(idx, 1)}
                                                        >▼</span>
                                                    </div>
                                                    <CheckBox
                                                        label={col.label}
                                                        cbChanged={col.required ? () => {} : () => {
                                                            const newVis = { ...props.columnVisibility, [key]: !props.columnVisibility[key] };
                                                            props.SetColumnVisibility(newVis);
                                                        }}
                                                        checked={col.required || (AI_COLS.includes(key)
                                                            ? props.columnVisibility[key] === true
                                                            : props.columnVisibility[key] !== false)}
                                                        textSide="right"
                                                        textColor={tc.text}
                                                        disabled={col.required}
                                                    />
                                                    <span style={{ fontSize: '10px', color: tc.text, opacity: 0.5 }}>{col.desc}{(!_settingsHasAI && AI_COLS.includes(key)) ? ' 🔒' : ''}</span>
                                                </div>
                                                );
                                            })}
                                        </div>
                                        {!isDefaultOrder && (
                                            <div
                                                style={{ fontSize: '10px', color: tc.text, opacity: 0.5, cursor: 'pointer', marginTop: '8px', textDecoration: 'underline' }}
                                                onClick={() => props.SetColumnOrder([...DEFAULT_COL_ORDER])}
                                            >
                                                Reset order
                                            </div>
                                        )}

                                        {/* Short Dates toggle */}
                                        <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginTop: '14px', marginBottom: '6px' }}>
                                            Display
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                            <CheckBox
                                                label="Short Dates"
                                                cbChanged={() => {
                                                    const next = !props.shortDates;
                                                    props.SetShortDates(next);
                                                    lsSet('tw_short_dates', next);
                                                }}
                                                checked={props.shortDates || false}
                                                textSide="right"
                                                textColor={tc.text}
                                            />
                                            <span style={{ fontSize: '10px', color: tc.text, opacity: 0.5 }}>Drop year from dates</span>
                                        </div>
                                    </div>
                                    );
                                })()}

                                {/* ── Securities Groups ── */}
                                {settingsCategory === 'secgroups' && (
                                    <div>
                                        {/* Sub-tabs */}
                                        <div style={{ display: 'flex', gap: '0px', marginBottom: '10px', borderBottom: '1px solid ' + tc.border }}>
                                            {[
                                                { key: 'groups', label: 'My Groups' },
                                                { key: 'published', label: 'Published Lists' },
                                                ...(props.isAdmin ? [{ key: 'admin', label: 'Admin' }] : []),
                                            ].map(t => (
                                                <div key={t.key}
                                                    onClick={() => { SetSecGroupsTab(t.key); SetSgMessage(''); }}
                                                    style={{
                                                        padding: '6px 12px', fontSize: '11px', cursor: 'pointer',
                                                        color: secGroupsTab === t.key ? tc.text : (tc.text + '88'),
                                                        fontWeight: secGroupsTab === t.key ? '700' : '400',
                                                        borderBottom: secGroupsTab === t.key ? '2px solid ' + (props.UITheme === 'dark' ? '#7aa2f7' : '#336') : '2px solid transparent',
                                                    }}
                                                >{t.label}</div>
                                            ))}
                                        </div>

                                        {sgMessage && <div style={{ fontSize: '10px', color: sgMsgColor, textAlign: 'center', marginBottom: '6px' }}>{sgMessage}</div>}

                                        {/* My Groups */}
                                        {secGroupsTab === 'groups' && (
                                            <div>
                                                <div style={{ fontSize: '10px', color: tc.text, opacity: 0.55, marginBottom: '8px', textAlign: 'center' }}>
                                                    Uncheck groups to hide them from the securities dropdown
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                                    {allGroups.map((g, i) => (
                                                        <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '2px 0' }}>
                                                            <CheckBox
                                                                name={`grp_${g.value}`}
                                                                checked={!isGroupHidden(g.label)}
                                                                cbChanged={() => toggleGroup(g.label)}
                                                                textSide="right"
                                                                textColor={tc.text}
                                                            />
                                                            <span style={{ marginLeft: '6px', fontSize: '11px', color: tc.text }}>{g.label}</span>
                                                            {g.type === 'P' && <span style={{ marginLeft: '4px', fontSize: '9px', color: 'gold' }}>★</span>}
                                                        </div>
                                                    ))}
                                                </div>
                                                <div style={{ textAlign: 'center', marginTop: '10px' }}>
                                                    <span style={{ fontSize: '10px', color: tc.text, opacity: 0.5, cursor: 'pointer', textDecoration: 'underline' }}
                                                        onClick={resetSGToDefault}>Reset to Default</span>
                                                </div>
                                            </div>
                                        )}

                                        {/* Published Lists */}
                                        {secGroupsTab === 'published' && (
                                            <div>
                                                <div style={{ fontSize: '10px', color: tc.text, opacity: 0.55, marginBottom: '8px', textAlign: 'center' }}>
                                                    Check published lists to add them to your securities dropdown
                                                </div>
                                                {(props.publishedLists || []).length === 0 &&
                                                    <div style={{ fontSize: '11px', color: tc.text, opacity: 0.5, textAlign: 'center', padding: '16px 0' }}>No published lists available</div>
                                                }
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                                    {(props.publishedLists || []).map((pl, i) => (
                                                        <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '2px 0' }}>
                                                            <CheckBox
                                                                name={`pl_${pl.name}`}
                                                                checked={isPublishedEnabled(pl.name)}
                                                                cbChanged={() => togglePublished(pl.name)}
                                                                textSide="right"
                                                                textColor={tc.text}
                                                            />
                                                            <span style={{ marginLeft: '6px', fontSize: '11px', color: tc.text }}>{pl.name}</span>
                                                            <span style={{ marginLeft: '6px', fontSize: '9px', color: tc.text, opacity: 0.5 }}>
                                                                ({pl.resource_name} · {pl.symbols ? pl.symbols.length : 0} symbols)
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* Admin */}
                                        {secGroupsTab === 'admin' && props.isAdmin && (
                                            <div>
                                                {/* Create new */}
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Create New List
                                                </div>
                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginBottom: '12px' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                        <span style={{ fontSize: '11px', color: tc.text, width: '50px' }}>Name:</span>
                                                        <input type="text" value={newListName} onChange={(e) => SetNewListName(e.target.value)}
                                                            placeholder="e.g. Optionable Stocks"
                                                            style={{ flex: 1, padding: '3px 6px', fontSize: '11px', borderRadius: '4px', border: '1px solid ' + tc.border }} />
                                                    </div>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                        <span style={{ fontSize: '11px', color: tc.text, width: '50px' }}>Group:</span>
                                                        <select value={newListResourceId} onChange={(e) => SetNewListResourceId(e.target.value)}
                                                            style={{ flex: 1, padding: '3px 6px', fontSize: '11px', borderRadius: '4px', border: '1px solid ' + tc.border }}>
                                                            <option value="">Select resource group</option>
                                                            {resourceOptions.map(r => <option key={r.id} value={r.value}>{r.label}</option>)}
                                                        </select>
                                                    </div>
                                                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px' }}>
                                                        <span style={{ fontSize: '11px', color: tc.text, width: '50px', paddingTop: '4px' }}>Symbols:</span>
                                                        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                            <textarea value={newListSymbols} onChange={(e) => SetNewListSymbols(e.target.value)}
                                                                placeholder="AAPL, MSFT, NVDA, ... or upload CSV"
                                                                rows={3}
                                                                style={{ width: '100%', padding: '3px 6px', fontSize: '11px', borderRadius: '4px', border: '1px solid ' + tc.border, resize: 'vertical' }} />
                                                            <label style={{ fontSize: '10px', color: tc.text, opacity: 0.7, cursor: 'pointer', textDecoration: 'underline' }}>
                                                                Upload from CSV
                                                                <input type="file" accept=".csv,.txt" style={{ display: 'none' }}
                                                                    onChange={(e) => handleCsvUpload(e, 'new')} />
                                                            </label>
                                                        </div>
                                                    </div>
                                                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                                        <button onClick={handleCreatePublishedList}
                                                            style={{ padding: '3px 14px', fontSize: '11px', cursor: 'pointer', borderRadius: '4px', border: '1px solid ' + tc.border }}>
                                                            Create
                                                        </button>
                                                    </div>
                                                </div>

                                                {/* Existing lists */}
                                                <div style={{ fontSize: '10px', fontWeight: '600', color: tc.text, opacity: 0.55, textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: '8px' }}>
                                                    Existing Published Lists
                                                </div>
                                                {(props.publishedLists || []).length === 0 &&
                                                    <div style={{ fontSize: '11px', color: tc.text, opacity: 0.5, textAlign: 'center' }}>No published lists</div>
                                                }
                                                {(props.publishedLists || []).map((pl, i) => (
                                                    <div key={i} style={{ borderBottom: '1px solid ' + tc.border, padding: '6px 0' }}>
                                                        <div style={{ display: 'flex', alignItems: 'center' }}>
                                                            <CheckBox name={`en_${pl.name}`} checked={pl.enabled} cbChanged={() => handleToggleEnabled(pl)} textColor={tc.text} />
                                                            <span style={{ marginLeft: '6px', fontSize: '11px', color: tc.text, flex: 1 }}>
                                                                {pl.name} <span style={{ fontSize: '9px', opacity: 0.5 }}>({pl.resource_name} · {pl.symbols.length})</span>
                                                            </span>
                                                            <GrEdit size={11} style={{ cursor: 'pointer', marginRight: '8px' }}
                                                                onClick={() => editingList === pl.name ? SetEditingList(null) : handleStartEdit(pl)} />
                                                            <BsTrash3 size={11} style={{ cursor: 'pointer', fill: 'red' }}
                                                                onClick={() => handleDeletePublishedList(pl.name)} />
                                                        </div>
                                                        {editingList === pl.name && (
                                                            <div style={{ marginTop: '4px' }}>
                                                                <textarea value={editSymbols} onChange={(e) => SetEditSymbols(e.target.value)}
                                                                    rows={3}
                                                                    style={{ width: '100%', padding: '3px 6px', fontSize: '11px', borderRadius: '4px', border: '1px solid ' + tc.border, resize: 'vertical' }} />
                                                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                                                                    <label style={{ fontSize: '10px', color: tc.text, opacity: 0.7, cursor: 'pointer', textDecoration: 'underline' }}>
                                                                        Upload from CSV
                                                                        <input type="file" accept=".csv,.txt" style={{ display: 'none' }}
                                                                            onChange={(e) => handleCsvUpload(e, 'edit')} />
                                                                    </label>
                                                                    <div style={{ display: 'flex', gap: '6px' }}>
                                                                        <button onClick={() => SetEditingList(null)} style={{ fontSize: '10px', cursor: 'pointer', padding: '2px 10px' }}>Cancel</button>
                                                                        <button onClick={() => handleSaveEdit(pl.name)} style={{ fontSize: '10px', cursor: 'pointer', padding: '2px 10px' }}>Save</button>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}

                            </div>
                        </div>

                    </div>
                )}

                <div ref={oppChatContainerRef} className='opp_table_div' style={{ backgroundColor: tc.panelBg }}>
                    <div style={{ flex: 100 - chatbotHeightPct, minHeight: 0, width: '100%', overflow: 'hidden' }} >
                        <OppTable {...props} onChatbotResizeMouseDown={handleResizerMouseDown} />
                    </div>

                    {props.showChatbot && <>
                        <div
                            role="separator"
                            aria-orientation="horizontal"
                            aria-label="Resize Tara chat from bottom edge"
                            onMouseDown={handleResizerMouseDown}
                            style={{
                                height: '5px',
                                width: '100%',
                                cursor: 'ns-resize',
                                backgroundColor: tc.titleBar,
                                flexShrink: 0,
                            }}
                        />
                        <div style={{ flex: chatbotHeightPct, minHeight: 0, width: '100%', overflow: 'hidden' }}>
                            <Chatbot {...props} hasAIScores={hasAIScores} />
                        </div>
                    </>}
                </div>

            </div>


            <div
                onMouseDown={handleNavResizerMouseDown}
                style={{
                    width: '5px',
                    height: '100%',
                    cursor: 'ew-resize',
                    backgroundColor: tc.titleBar,
                    flexShrink: 0,
                    userSelect: 'none',
                }}
            />

            <div ref={rightContentRef} id='right-content' style={{ backgroundColor: tc.panelBg, flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                <div className='seasonal-barchart-parent' style={{ height: `${topChartHeightPct}%`, flexShrink: 0 }}>
                    <SeasonalBarChart {...props} chartTo={chartTo} leftNavWidthPct={leftNavWidthPct} />
                </div>

                <div
                    onMouseDown={handleTopChartResizerMouseDown}
                    style={{
                        height: '5px',
                        width: '100%',
                        cursor: 'ns-resize',
                        backgroundColor: tc.titleBar,
                        flexShrink: 0,
                        userSelect: 'none',
                    }}
                />

                <div className='stock-linechart-parent' style={{ backgroundColor: tc.panelBg, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                    <BottomPanelTabs
                        slides={bottomSlides}
                        activeSlide={visibleBottomSlide}
                        onSelect={goToBottomSlide}
                    />
                    <Swiper
                        onSwiper={(s) => { props.setSwiper(s); swiperRef.current = s; }}
                        navigation={true}
                        className={`mySwiper ${SWIPE_WITH_MOUSE ? '' : 'no-mouse-drag'}`}
                        style={{ flex: 1, minHeight: 0, width: '100%' }}
                        initialSlide={getBottomSlideIndex(visibleBottomSlide, { hasAIScores })}
                        onSlideChange={(swiperCore) => {
                            const { activeIndex } = swiperCore;
                            const semantic = getBottomSlideName(activeIndex, { hasAIScores, fallback: 'wave_stats' });
                            if (preserveRequestedBottomSlide && semantic === visibleBottomSlide) return;
                            SetActiveBottomSlide(semantic);
                            setCookie('BottomWindowName', semantic, 300);
                            const legacyIndex = semantic === 'wave_stats' || semantic === 'ai_scores'
                                ? 1
                                : semantic === 'price_chart' ? 2 : 0;
                            setCookie('WindowNumber', String(legacyIndex), 300);
                        }}
                        allowSlideNext={true}
                        allowSlidePrev={true}
                        simulateTouch={SWIPE_WITH_MOUSE}  // controls mouse dragging; false disables it on desktop
                    >
                        <SwiperSlide
                            role="tabpanel"
                            id={getBottomPanelId('trend_chart')}
                            aria-labelledby={getBottomPanelTabId('trend_chart')}
                            aria-hidden={visibleBottomSlide !== 'trend_chart'}
                            tabIndex={visibleBottomSlide === 'trend_chart' ? 0 : -1}
                        >
                            <SeasonalChart
                                {...props}
                                chartTo={chartTo}
                                sharedBottomPanelNavigation={true}
                                chartTitle="Seasonal Chart"
                                chartData={props.consolidatedSeasonalData}
                            />
                        </SwiperSlide>
                        <SwiperSlide
                            role="tabpanel"
                            id={getBottomPanelId('wave_stats')}
                            aria-labelledby={getBottomPanelTabId('wave_stats')}
                            aria-hidden={visibleBottomSlide !== 'wave_stats'}
                            tabIndex={visibleBottomSlide === 'wave_stats' ? 0 : -1}
                        >
                            <TradeDetail {...props} chartTo={chartTo} sharedBottomPanelNavigation={true} />
                        </SwiperSlide>
                        {hasAIScores && (
                            <SwiperSlide
                                role="tabpanel"
                                id={getBottomPanelId('ai_scores')}
                                aria-labelledby={getBottomPanelTabId('ai_scores')}
                                aria-hidden={visibleBottomSlide !== 'ai_scores'}
                                tabIndex={visibleBottomSlide === 'ai_scores' ? 0 : -1}
                            >
                                <AIScorePanel
                                    viewModel={aiPanelViewModel}
                                    active={activeBottomSlide === 'ai_scores'}
                                    onOpenGuide={() => SetShowAIScoresGuide(true)}
                                />
                            </SwiperSlide>
                        )}
                        <SwiperSlide
                            role="tabpanel"
                            id={getBottomPanelId('price_chart')}
                            aria-labelledby={getBottomPanelTabId('price_chart')}
                            aria-hidden={visibleBottomSlide !== 'price_chart'}
                            tabIndex={visibleBottomSlide === 'price_chart' ? 0 : -1}
                        >
                            <StockLineChart {...props} chartTo={chartTo} priceChartType={priceChartType} sharedBottomPanelNavigation={true} />
                        </SwiperSlide>
                    </Swiper>
                </div>


            </div>
            {showAIScoresGuide && (
                <AIScoresPopup onClose={() => SetShowAIScoresGuide(false)} iconRect={null} />
            )}
        </div>
    );
};

export default DesktopLayout;
