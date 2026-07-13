import React, { useContext, useEffect, useMemo, useRef, useState } from 'react'
import { UserContext } from './UserContext'
import { appserverURL, themeColors } from './Common'
import './styles/InfoPopup.css'
import './styles/Portfolios.css'
import { GrClose } from "react-icons/gr";
import { MdOutlineTitle } from "react-icons/md"; // <MdOutlineTitle />
import { MdOutlinePublishedWithChanges, MdUnpublished } from "react-icons/md";

// import SelectBox from './SelectBox'
// import TextBox from './TextBox'
import { BsTrash3 } from "react-icons/bs"
// import { GrEdit } from "react-icons/gr";

import { IoHomeOutline } from "react-icons/io5";
import { FaLink } from "react-icons/fa";
import { MdClear } from "react-icons/md";


const PublishArticle = (props) => {

    const maxCharacters = 1000; // maximum number of characters allowed in a note

    const { numReportsAllowed, browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    const [text, SetText] = useState("");

    const [message, SetMessage] = useState("")
    const [msgColor, SetMsgColor] = useState('red')
    const [articlePrompt, SetArticlePrompt] = useState('');

    // Utility function to format today's date as YYYY-MM-DD
    const getTodayDate = () => {
        const today = new Date();
        const month = String(today.getMonth() + 1).padStart(2, '0');
        const day = String(today.getDate()).padStart(2, '0');
        const year = today.getFullYear();
        return `${year}-${month}-${day}`;
    };


    // const [publishDate, setPublishDate] = useState(getTodayDate());

    const [publishDate, setPublishDate] = useState(() => {
        const r = props.selectedPortfolioRec;

        if (r && r.article_queued === true) {
            return r.article_publish_date;
        }

        return getTodayDate();
    });

    const [dashboardDialog_TLHW, SetDashboardDialog_TLHW] = useState(''); // this the main portfolio dialog TOp Left Height Width - coordinates are used to place a transparent div over the dashboard before rendering notes dilaog - this to enable clciking outside of the dialog and then closing the dialog.

    const [dragPos, setDragPos] = useState(null)
    const [dragSize, setDragSize] = useState(null)
    const dragRef = useRef({ active: false, offsetX: 0, offsetY: 0 })
    const dialogRef = useRef(null)

    useEffect(() => {
        const onMouseMove = (e) => {
            if (!dragRef.current.active) return
            const x = Math.max(0, Math.min(window.innerWidth - 200, e.clientX - dragRef.current.offsetX))
            const y = Math.max(0, Math.min(window.innerHeight - 60, e.clientY - dragRef.current.offsetY))
            setDragPos({ x, y })
        }
        const onMouseUp = () => { dragRef.current.active = false }
        window.addEventListener('mousemove', onMouseMove)
        window.addEventListener('mouseup', onMouseUp)
        return () => {
            window.removeEventListener('mousemove', onMouseMove)
            window.removeEventListener('mouseup', onMouseUp)
        }
    }, [])

    const handleTitleMouseDown = (e) => {
        if (rdd.isMobile) return
        if (e.detail === 2) { setDragPos(null); setDragSize(null); return }
        const el = dialogRef.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        dragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top }
        if (!dragSize) setDragSize({ w: rect.width, h: rect.height })
        e.preventDefault()
    }

    const [articleURL, SetArticleURL] = useState(null);
    const [newsHomeURL, SetNewsHomeUrl] = useState(null);
    const [articleMode, SetArticleMode] = useState('2');  // default Mode 1


    const [articlePublishState, SetArticlePublishState] = useState(false);


    var DialogH = '80%';
    var DialogW = '60%';
    var DialogT = '10%';
    var DialogL = '20%';
    var grclose_iconsize = 17;
    var icon_sizeP = 15;
    var icon_sizeE = 12;
    var icon_sizeD = 12;
    var title_text_size = '1vw';
    var button_height = '2.5vh'
    var textboxWidth = 24;

    var titleCloseDivWidth = '5%';
    var titleCenterDivWidth = '90%';

    var cancel_width = '25%';
    var save_width = '25%';

    var charIndicatorFontSize = '0.7vw'; // this is indicator showing number of chars typed

    var textareaFont = '0.8vw';

    var icon_trash_size = 15;
    var icon_size = 20;

    var articleQueueButtonText = 'Article Queue';
    var createPromptButtonText = 'Create Prompt';
    var loadHTMLButtonText = 'Load HTML';
    var recHeroButtonText = 'Rec Hero';
    var delArticleButtonText = 'Del Article';


    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
        DialogH = '40%';
        DialogW = '100%';
        DialogT = '18%';
        DialogL = '0';
        grclose_iconsize = 17;
        title_text_size = '4.5vw';
        textboxWidth = 16;
        button_height = '4vh';
        titleCloseDivWidth = '10%';
        titleCenterDivWidth = '80%';

        cancel_width = '33%';
        save_width = '28%'
        charIndicatorFontSize = '3vw';
        textareaFont = '3.1vw';

        articleQueueButtonText = 'Queue';
        createPromptButtonText = 'Prompt';
        loadHTMLButtonText = 'Load';
        recHeroButtonText = 'Hero';
        delArticleButtonText = 'Del';


    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {

        DialogT = '10%';
        DialogL = '20%';
        DialogH = '70%';
        DialogW = '60%';
        grclose_iconsize = 17;
        title_text_size = '2vw';
        textboxWidth = 17;
        button_height = '5.3vh';

        cancel_width = '40%';
        save_width = '28%'
        charIndicatorFontSize = '1.8vw';
        textareaFont = '2vw';

        articleQueueButtonText = 'Queue';
        createPromptButtonText = 'Prompt';
        loadHTMLButtonText = 'Load';
        recHeroButtonText = 'Hero';
        delArticleButtonText = 'Del';

        textareaFont = '1.7vw';

    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserW < 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';
        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 24;
        charIndicatorFontSize = '1.9vw';
        textareaFont = '2.2vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserH < 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';
        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 19;
        charIndicatorFontSize = '1.1vw';
        textareaFont = '1.3vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';
        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 26;
        charIndicatorFontSize = '2vw';
        textareaFont = '2vw';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserW > 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';
        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 23;
        charIndicatorFontSize = '1.1vw';
        textareaFont = '1.3vw';
    }
    //------------------------------------------------------------------------------------------------------------
    const DashboardCover = {
        height: dashboardDialog_TLHW['height'],
        width: dashboardDialog_TLHW['width'],
        top: dashboardDialog_TLHW['top'],
        left: dashboardDialog_TLHW['left'],
        backgroundColor: 'transparent',
        display: 'flex',
        position: 'absolute',
        zIndex: 6000
    }
    //------------------------------------------------------------------------------------------------------------
    const popupDialogStyle = {
        fontFamily: 'sans-serif',
        fontSize: '0.8vw',
        fontWeight: 'bold',
        backgroundColor: tc.panelBg,
        height: DialogH,
        width: DialogW,
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid ' + tc.border,
        alignItems: 'center',
        zIndex: 7000,
        ...(dragPos
            ? { position: 'fixed', top: dragPos.y, left: dragPos.x, width: dragSize?.w, height: dragSize?.h, boxShadow: '0 8px 32px rgba(0,0,0,0.35)' }
            : { position: 'absolute', top: DialogT, left: DialogL, height: DialogH, width: DialogW })
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // this useMemo is for retreiving the coordinates of the parent Div, Report Dashboard
    useMemo(() => {

        const elem = document.querySelector('.dialog-popup-reports-dashboard');
        const rect = elem.getBoundingClientRect();
        if (rect) {
            SetDashboardDialog_TLHW(rect);
        }
    }, []);
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {
        const asURL = appserverURL();

        const url = `${asURL}/get_news_home_url/?token=${token}`;

        fetch(url)
            .then(response => {
                if (!response.ok) throw new Error(response.status);
                return response.json();
            })
            .then(data => {

                if (data.ok && data.news_home_url) {

                    SetNewsHomeUrl(data.news_home_url);
                }
            })
            .catch(err => {
                console.log("Failed to fetch news home URL:", err.message);
            });
    }, []);  // run once on dialog open
    //-------------------------------------------------------------------------------------------------------------------------------------
    useEffect(() => {
        // when dialog opens / selected pattern changes, try to load HTML
        load_article_html();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleTextChange = (event) => {
        SetText(event.target.value);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const copyToClipboard = async (text) => {
        try {
            await navigator.clipboard.writeText(text);
            console.log('Text copied to clipboard');
        } catch (err) {
            console.error('Failed to copy: ', err);
        }
    };



    //-------------------------------------------------------------------------------------------------------------------------------------
    // mode can be:
    // default - works as it does now - default and '0' are the same thing
    // hero    - only recreates the hero image
    // '0', '1', '2'  the 3 modes of prompt and article generation: 
    // '0' : prompt generated with web search embded in prompt
    // '1' : perplexity sonar-pro is called for websearch - results are then used to create an article generation prompt 
    //       with no web search
    // '2' : full automation - perplexity sonar-pro does websearch - prompt if generated with the results and then 
    //       gpt 5.1 api is called - 
    //-------------------------------------------------------------------------------------------------------------------------------------
    const create_article_prompt = (mode = '0') => {

        let userid = loggedinUser;
        let note = '-';
        var r = props.selectedPortfolioRec;
        var asURL = appserverURL();
        const articleDate = publishDate; // This is the publication date (YYYY-MM-DD)

        // ==========================================================
        // >>> START: NEW LOGIC FOR MODE '2' (Async Workflow) <<<
        // ==========================================================
        if (mode === '2') {
            SetMessage('Starting article workflow (mode 2) ...');
            SetMsgColor('darkblue');

            // console.log('rrrrrrrrrrrrrrrrrrrrrrrrr=',r)

            // New appserver route for async writing: /write_article_queue/
            // Route signature: /resourceID/symbol/date/days_hold/years/userid/publish_date
            let workflowUrl = `${asURL}/write_article_queue/${r['resourceID']}/${r['symbol']}/${r['date']}/${r['days_hold']}/${r['years']}/${r['direction']}/${userid}/${articleDate}?token=${token}`;

            fetch(workflowUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                .then((response) => {
                    if (!response.ok) {
                        throw new Error(response.status);
                    }
                    return response.json();
                })
                .then((data) => {
                    if (data.status === "queued") {
                        SetMsgColor('darkgreen');
                        SetMessage('Article queued on server for generation).');


                        props.SetReportsList([]);



                        setTimeout(() => {
                            props.SetShowArticlePublish(false);

                        }, 1200);

                    } else {
                        // Handle server-side failure response (e.g., status: "failed")
                        SetMsgColor('red');
                        SetMessage(data.reason || 'Article workflow failed to start.');
                    }
                })
                .catch((error) => {
                    console.error("Workflow failed:", error);
                    SetMsgColor('red');
                    SetMessage(`Error starting workflow: ${error.message}`);
                });

            return; // EXIT FUNCTION after starting async workflow
        }
        // ==========================================================
        // >>> END: NEW LOGIC FOR MODE '2' <<<
        // ==========================================================


        // Fallback URL for Modes 0 and 'hero' (synchronous prompt/image creation)
        // Original route signature: /resourceID/symbol/date/days_hold/years/userid/mode/note
        // Note: This still uses r['date'] (the trade date) and the original article_prompt route.
        let url = `${asURL}/article_prompt/${r['resourceID']}/${r['symbol']}/${r['date']}/${r['days_hold']}/${r['years']}/${userid}/${mode}/${note}?token=${token}`;


        if (mode === 'hero') {
            SetMessage('Hero image recreation started ...');
            SetMsgColor('darkgreen');
        } else {
            SetMessage('Creating article prompt (mode 0) ...');
            SetMsgColor('darkgreen');
        }

        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status);
                }
                return response.json();
            })
            .then((data) => {

                if (mode === 'hero') {
                    if (data.message === 'success') {
                        SetMsgColor('darkgreen');
                        SetMessage('Hero image recreated.');
                    } else {
                        SetMsgColor('red');
                        SetMessage(data.reason || 'Hero recreation failed');
                    }
                    return;
                }

                // ---------- MODE 2: article_html ----------
                if (mode === '2') {
                    SetMsgColor('darkgreen');
                    SetMessage('Article HTML generated.');
                    SetText(data['article_html'] || '');
                    return;
                }

                // ---------- MODE 0: article_prompt ----------
                SetArticlePrompt(data['article_prompt']);
                copyToClipboard(data['article_prompt']);
                SetMsgColor('darkgreen');
                SetMessage('Article prompt created and loaded to clipboard.');
                SetText(data['article_prompt']);
            })
            .catch((error) => {
                console.error('Article prompt creation failed:', error);
                SetMsgColor('red');
                SetMessage(`Error creating article prompt: ${error.message}`);
            });
    };
    //-------------------------------------------------------------------------------------------------------------------------------------
    const open_article = () => {
        if (!articleURL) {
            SetMsgColor('darkred');
            SetMessage('No article URL available.');
            return;
        }
        window.open(articleURL, "_blank", "noopener,noreferrer");
    };
    //-------------------------------------------------------------------------------------------------------------------------------------
    // @app.route('/article_load/<string:resourceID>/<string:symbol>/<string:date>/<string:days>/<string:years>/<string:userid>', methods=['GET'])
    const load_article_html = () => {

        let userid = loggedinUser;
        const r = props.selectedPortfolioRec;
        const asURL = appserverURL();

        // appserver route:
        // /article_load/<resourceID>/<symbol>/<date>/<days>/<years>/<userid>?token=...
        const url = `${asURL}/article_load/${r['resourceID']}/${r['symbol']}/${r['date']}/${r['days_hold']}/${r['years']}/${userid}?token=${token}`;

        // console.log('article load url =', url);

        SetMsgColor('black');
        SetMessage('Loading existing article HTML ...');

        fetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // non-2xx => error
                }
                return response.json();
            })
            .then((data) => {
                // Expected shape from appserver/blog_queue:
                // { found: bool, html: string|null, reason: string, ... }
                // console.log('dddddddddd=', data)
                if (!data.found || !data.html) {
                    SetMsgColor('darkred');
                    SetMessage(data.reason || 'No saved article HTML found for this pattern.');
                    return;
                }

                // Push HTML into editor
                if (data.html) {
                    SetText(data.html);
                }
                if (data.url) {
                    SetArticleURL(data.url);
                }
                SetMsgColor('darkgreen');
                SetMessage('Existing article HTML loaded.');
            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('Article not found');
                    SetMsgColor('darkred');
                    SetMessage('No Article for current pattern');
                } else {
                    console.log('Error:', error.message);
                    SetMsgColor('darkred');
                    SetMessage(error.message);
                }
            });
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handle_del_text = () => {
        SetText('');
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // publish the article so that it can be added to the where ever this html article is supposed to become available
    //-------------------------------------------------------------------------------------------------------------------------------------
    const publish_html_article = async () => {
        const userid = loggedinUser;
        const r = props.selectedPortfolioRec;
        const asURL = appserverURL();
        // const token = window.token; // wherever you store it

        const url = `${asURL}/article_publish/${r.resourceID}/${r.symbol}/${r.date}/${r.days_hold}/${r.years}/${r.direction}/${userid}?token=${token}`;

        try {
            SetMsgColor('blue');
            SetMessage('Publishing HTML Article');

            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'text/html' },
                body: text, // your large HTML string - this is the text inside the <textarea>
            });

            // if (!resp.ok) throw new Error(`${resp.status}`);

            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(`Server error ${resp.status}: ${text}`);
            }

            const data = await resp.json();

            SetMsgColor('darkgreen');
            SetMessage('Article Published');
            props.SetReportsList([]);
            load_article_html();         // refresh this dialog
        } catch (err) {
            console.log('Error:', err.message);
            SetMessage(err.message);
        }
    }
    //----------------------------------------------------------------------------------------------
    const delete_html_article_confirm = () => {
        let title = 'Delete Article';
        let content = `Delete ${props.selectedPortfolioRec['symbol']} Article`

        if (props.selectedPortfolioRec['article_queued']) {
            content = `Delete ${props.selectedPortfolioRec['symbol']} Article From the Queue`
        }
        props.SetDialogProp({ title: title, contentText: content, button1Text: 'Canel', button2Text: 'Delete', coverDivColor: 'rgb(222,222,222,0)', ExecuteFuncAfterConfirmation: delete_html_article })
        props.SetDialogType('info-box');
        props.SetInfoBoxVisible(true)
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // delete the article by publishing 'remove' with the same route as article_publish
    //-------------------------------------------------------------------------------------------------------------------------------------
    const delete_html_article = async () => {
        const userid = loggedinUser;
        const r = props.selectedPortfolioRec;
        const asURL = appserverURL();

        const url = `${asURL}/article_delete/${r.resourceID}/${r.symbol}/${r.date}/${r.days_hold}/${r.years}/${userid}?token=${token}`;

        try {
            SetMsgColor('red');
            SetMessage('Deleting article...');

            const resp = await fetch(url, { method: 'POST' });
            const text = await resp.text();
            console.log('[delete_html_article] status =', resp.status, 'body =', text);

            if (!resp.ok) {
                throw new Error(`Server error ${resp.status}: ${text}`);
            }

            let data = {};
            try {
                data = JSON.parse(text);
            } catch (_) { }
            console.log('[delete_html_article] parsed =', data);

            SetMsgColor('darkgreen');
            SetMessage('Article Deleted');

            SetText('');
            SetArticleURL(null);
            props.SetReportsList([]);
            load_article_html();
            setTimeout(() => {
                props.SetShowArticlePublish(false);
            }, 500);

        } catch (err) {
            console.log('Error in delete_html_article:', err);
            SetMsgColor('red');
            SetMessage(err.message);
        }
    };
    //-------------------------------------------------------------------------------------------------------------------------------------
    function formated_opp_string() {
        var r = props.selectedPortfolioRec;

        // console.log('rrrrrrrrrrrrrrrrrrrrr', r)

        let fstr = `resource_id:${r['resourceID']} symbol:${r['symbol']}   date:${r['date']}   days:${r['days_hold']}   years:${r['years']}`

        let ret = '';

        if (r['article_queued']) {
            return <div><span>{fstr}</span>&nbsp;&nbsp;<span style={{ color: 'red' }}>Queued</span></div>
        }
        else {
            return <div><span>{fstr}</span></div>
        }
    }


    const toggle_publish_state = () => {
        SetArticlePublishState(!articlePublishState);
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const r = props.selectedPortfolioRec || {};

    return (

        <div style={DashboardCover} onClick={() => { props.SetShowArticlePublish(false); }}>

            <div ref={dialogRef} style={popupDialogStyle} onClick={(e) => { e.stopPropagation(); }}>

                {/* title bar  */}
                <div style={{ width: '100%', height: '8%', backgroundColor: tc.titleBar, display: 'flex', cursor: rdd.isMobile ? 'default' : 'move' }} onMouseDown={handleTitleMouseDown}>
                    <div style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'transparent' }}></div>
                    <div className='div_basic' style={{ height: '100%', width: titleCenterDivWidth, backgroundColor: 'transparent' }}><span style={{ fontSize: title_text_size, color: 'whitesmoke' }}>Publish Article</span></div>
                    <div className='div_basic' onClick={() => { props.SetShowArticlePublish(false); }} style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: tc.closeBtnBg }}><GrClose size={grclose_iconsize} /></div>
                </div>

                <div className='div_basic' style={{ width: '100%', height: '92%', backgroundColor: 'transparent', flexDirection: 'column', color: tc.text }}>

                    <div style={{ fontSize: textareaFont, height: '10%', width: '100%', backgroundColor: UITheme === 'dark' ? tc.statLabelBg : 'lightgreen', display: 'flex', alignItems: 'center', paddingLeft: '10px' }}>
                        {formated_opp_string()}
                    </div>

                    {/* top buttons  */}

                    <div style={{ height: '10%', width: '100%', backgroundColor: UITheme === 'dark' ? tc.tableHeaderBg : 'lightblue', display: 'flex', alignItems: 'center', paddingLeft: '10px' }}>

                        {/* <button onClick={() => create_article_prompt('0')}>Create Prompt</button> <span>&nbsp;</span> */}


                        <button onClick={() => create_article_prompt('2')}>
                            {articleQueueButtonText}
                        </button>
                        <span>&nbsp;</span>

                        <input
                            type="date"
                            id="publish_date_input"
                            lang="en-CA"
                            value={publishDate} // Set the value from state (defaults to today)
                            onChange={(e) => setPublishDate(e.target.value)} // Update state on user change
                        />

                        <span>&nbsp;</span>

                        {/* CREATE PROMPT - only if NO article exists AND NOT queued */}
                        {!r.article_exists && !r.article_queued && (
                            <button onClick={() => create_article_prompt('0')}>
                                {createPromptButtonText}
                            </button>
                        )}
                        {/* <span>&nbsp;</span> */}

                        {/* LOAD HTML - only if article exists */}
                        {r.article_exists && (
                            <button onClick={load_article_html}>
                                {loadHTMLButtonText}
                            </button>
                        )}
                        <span>&nbsp;</span>

                        {/* REC HERO - only if article exists */}
                        {r.article_exists && (
                            <button onClick={() => create_article_prompt('hero')}>
                                {recHeroButtonText}
                            </button>


                        )}


                        {/* DELETE ARTICLE - always visible */}
                        {/* DEL ARTICLE - only if article exists OR queued */}
                        {(r.article_exists || r.article_queued) && (
                            <>
                                <span>&nbsp;</span>
                                <button onClick={delete_html_article_confirm}> {delArticleButtonText}</button>
                                <span>&nbsp;&nbsp;</span>
                                <BsTrash3 size={icon_size * 0.84} style={{ fill: tc.text, cursor: 'pointer' }} onClick={delete_html_article_confirm} />
                                <span>&nbsp;&nbsp;</span>
                            </>
                        )}




                        {/* {articlePublishState
                            ? <MdOutlinePublishedWithChanges size={icon_size} style={{ fill: "darkgreen", cursor: 'pointer' }} onClick={toggle_publish_state} />
                            : <MdUnpublished size={icon_size} style={{ fill: "red", cursor: 'pointer' }} onClick={toggle_publish_state} />
                        } */}


                        {/* when article doesn't exist the publish button doesn't show  */}
                        {r.article_exists && (
                            articlePublishState
                                ? <MdOutlinePublishedWithChanges size={icon_size} style={{ fill: "darkgreen", cursor: "pointer" }} onClick={toggle_publish_state} />
                                : <MdUnpublished size={icon_size} style={{ fill: "red", cursor: "pointer" }} onClick={toggle_publish_state} />
                        )}


                        {/* when article doesn't exist the publish button is grayed out   */}
                        {/* {articlePublishState
                            ? <MdOutlinePublishedWithChanges size={icon_size}
                                style={{ fill: (r.article_exists ? "darkgreen" : "gray"), cursor: (r.article_exists ? "pointer" : "not-allowed") }}
                                onClick={r.article_exists ? toggle_publish_state : undefined}
                            />
                            : <MdUnpublished size={icon_size}
                                style={{ fill: (r.article_exists ? "red" : "gray"), cursor: (r.article_exists ? "pointer" : "not-allowed") }}
                                onClick={r.article_exists ? toggle_publish_state : undefined}
                            />
                        } */}




                        <span>&nbsp;&nbsp;</span>

                        <IoHomeOutline size={icon_size} style={{ cursor: 'pointer' }} onClick={() => { if (newsHomeURL) { window.open(newsHomeURL, "_blank"); } }} /><span>&nbsp;&nbsp;</span>


                        <FaLink onClick={open_article} size={icon_size * 0.9} /><span>&nbsp;</span>

                        {/* <MdOutlineTitle /> */}


                        <MdClear size={icon_size * 1.3} onClick={handle_del_text} /><span>&nbsp;</span>

                    </div>

                    <div style={{ height: '70%', width: '100%', backgroundColor: UITheme === 'dark' ? tc.panelBg : 'pink' }}>
                        <textarea
                            value={text}
                            style={{ height: '100%', width: '100%', padding: '5px', resize: 'none', fontSize: textareaFont, backgroundColor: UITheme === 'dark' ? 'rgb(40, 37, 55)' : 'white', color: tc.text }}
                            onChange={handleTextChange}
                        />
                    </div>

                    <div style={{ height: '10%', width: '100%', backgroundColor: UITheme === 'dark' ? tc.statLabelBg : 'lightgray', display: 'flex', alignItems: 'center', paddingLeft: '10px' }}>
                        <button onClick={publish_html_article}>Publish / Update HTML Article</button>&nbsp;&nbsp;
                        {/* < size={icon_trash_size} style={{ color: 'red', verticalAlign: "middle", marginRight: '1vw', fill: "gray" }} onClick={handle_del_text} /> */}
                        <span style={{ color: msgColor, fontSize: globalTextSize }}>{message}</span>
                    </div>

                </div>

            </div >
        </div>
    )
}
export default PublishArticle
