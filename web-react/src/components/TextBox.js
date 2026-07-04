import React, { useState, useEffect, useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import Tippy from '@tippyjs/react'
import { userAccessToSelectedSecurity } from './Common'

// Set once a user first focuses the symbol box; gates the one-time
// first-visit pulse so returning users never see it again.
const SYMBOL_SEEN_KEY = 'tw_symbolbox_seen'

const TextBox = ({ tooltipContent, name, text, width, tbBlur, tbEnter, securityTypeList2, selectedSecurity, browserH, browserW, qparams, errorStatus, creditLock, syncNonce }) => {


    const { wpUserLevels, rdd, globalTextSize, loggedinUser, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [curText, SetCurText] = useState(text)

    // The symbol box is the single most important control for a first-time
    // user - it gets a placeholder, an accent border + tinted background, and a
    // gentle pulse on the very first visit (until first click, then never again).
    // Deliberately NO glyph: a magnifier implies search (it's direct entry) and
    // a $ implies a money field / breaks on forex+futures symbols - both rejected.
    const isSymbol = name === 'symbol'
    const [showPulse, SetShowPulse] = useState(() => {
        if (name !== 'symbol') return false
        try { return !window.localStorage.getItem(SYMBOL_SEEN_KEY) } catch (e) { return false }
    })


    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { }

    //---------------------------------------------------------------------------
    useEffect(() => {
        SetCurText(text)  //holding state in the component just to make sure
        // syncNonce: parent bumps it to force a re-sync when `text` did NOT change -
        // e.g. a rejected symbol (not found) must snap the box back to the old symbol.
    }, [text, syncNonce])

    const handleFocus = (event) => { // TradeInstrument.js credit + symbol first-visit pulse
        if (creditLock !== undefined){
            creditLock.current=true;
        }
        if (isSymbol && showPulse) {
            SetShowPulse(false)
            try { window.localStorage.setItem(SYMBOL_SEEN_KEY, '1') } catch (e) { }
        }
    }
    //---------------------------------------------------------------------------
    const handleOnChange = (event) => {

        // console.log('event triggered in textbox ',event.target.value,event)


        // if (name !== 'event_time' && name !== 'shares' && name!=='new_textbox' && name !== 'total_price') {
        if (name === 'symbol' || name === 'date') {
            let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity) // 1/21/2023

            // if ((name === 'date' && loggedinUser === '0') || retArray[0] === 'F') {
            //     return
            // }
            // if (wpUserLevels.length === 1 && wpUserLevels[0] === '1') { //free registered
            //     return; 
            // }

            if (name === 'date' && (loggedinUser === '0' || retArray[0] === 'F')) {
                return
            }

            if (name === 'symbol' && typeof (qparams) === 'string') { // check if name is string and qparams is passed
                // console.log('xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',typeof(qparams))
                if ((loggedinUser === '0' || retArray[0] === 'F')) { // if they have free access disable
                    return
                }

            }
        }



        if (name === 'shares' && (isNaN(event.target.value) || parseInt(event.target.value) > 10000)) return // max shares is 10000

        let tmp = event.target.value;
        if (name !== 'new_textbox') {
            tmp = tmp.toUpperCase()
        }
        SetCurText(tmp)
    }
    //---------------------------------------------------------------------------
    let textHeight = '2.7vh';

    let textAlign = 'center';

    if (name === 'new_textbox') {
        textAlign = 'left';
    }

    if (name === 'shares') textHeight = '2.4vh'

    let textFontWeight = 'normal';
    let paddingText = '0'
    let textboxFontSize = globalTextSize;  // this is to fix tablet portrait 8/31/2022

    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
        if (name === 'shares') {
            textHeight = '3vh';
            textFontWeight = 'bold';
            paddingText = '1vw';
        }
        else if (name === 'total_price') {
            textHeight = '4vh';
            paddingText = '1vw';
            textboxFontSize = '2.8vw';

        }
        else if (name === 'new_textbox') {
            textHeight = '4vh';
            paddingText = '1vw';
            textboxFontSize = '3.0vw';
        }
        else if (name === 'credit' || name === 'num_option_contracts' || 'auto_exit_gain_pct'){
            textHeight = '2.4vh';
            textFontWeight = 'bold';
            paddingText = '1vw';
        }
        // else if (name === 'symbol' || name === 'date'){
        //     textHeight = '8.8vh';
        //     textFontWeight = 'bold';
        //     paddingText = '1vw';
        // }
        else {
            textHeight = '3.8vh';
            textFontWeight = 'bold';
            paddingText = '1vw';
        }
    }
    else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { //smartphone landscape
        if (name === 'date' || name === 'symbol') textHeight = '7vh';
        else if (name === 'total_price' || name === 'shares') {
            textboxFontSize = '1.4vw';
            textHeight = '5.6vh';
        }
        else textHeight = '5.6vh';
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
        textboxFontSize = '1.7vw';
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { //tablet landscape

    }
    else if (!rdd.isMobile) {                                       // desktop
        paddingText = '2px'
    }

    var ttc = '';
    var ttp = 'right';
    if (tooltipContent !== undefined) {
        ttc = tooltipContent.slice(2);
        switch (tooltipContent.substring(0, 1)) {
            case 'r': ttp = 'right'; break;
            case 'l': ttp = 'left'; break;
            case 't': ttp = 'top'; break;
            case 'b': ttp = 'bottom'; break;
            default: break;
        }
    }


    return (


        <Tippy placement={ttp} disabled={!ttc} content={
            <div theme="tw" >
                {ttc}
            </div>
        }>


            <div>
                {/* <input type="text" value={curText} onBlur={tbBlur} onChange={handleOnChange} onKeyPress={tbEnter} size={width} id={name} style={{ fontSize: inputFontSize }} /> */}
                <input type="text" value={curText} onBlur={tbBlur} onFocus={handleFocus} onChange={handleOnChange} onKeyPress={tbEnter}
                    size={isSymbol ? (parseInt(width, 10) || 5) + 2 : width}
                    id={name}
                    className={isSymbol ? 'tw-symbol-input' + (showPulse ? ' tw-symbol-pulse' : '') : undefined}
                    placeholder={isSymbol ? 'Ticker' : undefined}
                    style={{
                        fontWeight: isSymbol ? 'bold' : textFontWeight,
                        fontSize: textboxFontSize,
                        height: textHeight,
                        paddingLeft: paddingText,
                        textAlign: textAlign,
                        border: isSymbol ? '2px solid ' + tc.symbolAccent : '1px solid ' + tc.border,
                        borderRadius: isSymbol ? '3px' : undefined,
                        backgroundColor: isSymbol ? tc.symbolBg : tc.inputBg,
                        color: tc.text,
                    }} />
            </div>

        </Tippy>

    )
}

export default TextBox
