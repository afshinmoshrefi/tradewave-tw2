// TextBoxInc - TextBox with left/right chevron arrows for incrementing/decrementing
// Used for date nudging: ◀ shifts start date earlier, ▶ shifts start date later

import React, { useState, useEffect, useContext } from 'react'
import { UserContext } from './UserContext'
import { FaChevronLeft, FaChevronRight } from "react-icons/fa"
import Tippy from '@tippyjs/react'
import { themeColors } from './Common'
import { userAccessToSelectedSecurity } from './Common'

const TextBoxInc = ({ tooltipContent, name, text, width, tbBlur, tbEnter, securityTypeList2, selectedSecurity, qparams, onLeftClick, onRightClick }) => {
    const { wpUserLevels, rdd, globalTextSize, loggedinUser, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [curText, SetCurText] = useState(text)

    useEffect(() => {
        SetCurText(text)
    }, [text])

    //---------------------------------------------------------------------------
    const handleOnChange = (event) => {
        if (name === 'symbol' || name === 'date') {
            let retArray = userAccessToSelectedSecurity(securityTypeList2, selectedSecurity)
            if (name === 'date' && (loggedinUser === '0' || retArray[0] === 'F')) {
                return
            }
            if (name === 'symbol' && typeof (qparams) === 'string') {
                if ((loggedinUser === '0' || retArray[0] === 'F')) {
                    return
                }
            }
        }
        let tmp = event.target.value;
        tmp = tmp.toUpperCase()
        SetCurText(tmp)
    }

    //---------------------------------------------------------------------------
    // Responsive sizing (matches TextBox.js)
    let textHeight = '2.7vh';
    let textFontWeight = 'normal';
    let paddingText = '0'
    let textboxFontSize = globalTextSize;
    let iconSize = 10;

    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
        textHeight = '3.8vh';
        textFontWeight = 'bold';
        paddingText = '1vw';
        iconSize = 12;
    }
    else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { // smartphone landscape
        if (name === 'date' || name === 'symbol') textHeight = '7vh';
        else textHeight = '5.6vh';
        iconSize = 10;
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
        textboxFontSize = '1.7vw';
        iconSize = 10;
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { // tablet landscape
        iconSize = 10;
    }
    else if (!rdd.isMobile) { // desktop
        paddingText = '2px'
        iconSize = 10;
    }

    //---------------------------------------------------------------------------
    // Tooltip parsing (same convention as TextBox: first 2 chars = position)
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

    const arrowStyle = {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        padding: '0 3px',
    }

    return (
        <div style={{ display: 'flex', alignItems: 'center' }}>

            <div style={arrowStyle} onClick={onLeftClick}>
                <FaChevronLeft size={iconSize} style={{ fill: tc.text }} />
            </div>

            <Tippy placement={ttp} disabled={!ttc} content={
                <div theme="tw">
                    {ttc}
                </div>
            }>
                <div>
                    <input type="text" value={curText} onBlur={tbBlur} onChange={handleOnChange} onKeyPress={tbEnter} size={width} id={name} style={{ fontWeight: textFontWeight, fontSize: textboxFontSize, height: textHeight, paddingLeft: paddingText, textAlign: 'center', border: '1px solid ' + tc.border, backgroundColor: tc.inputBg, color: tc.text }} />
                </div>
            </Tippy>

            <div style={arrowStyle} onClick={onRightClick}>
                <FaChevronRight size={iconSize} style={{ fill: tc.text }} />
            </div>

        </div>
    )
}

export default TextBoxInc
