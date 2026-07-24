// TextBoxS is for search.  got too lazy to make all the changes to regular textbox 

import React, { useContext } from 'react'
import Tippy from '@tippyjs/react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'

const TextBoxS = ({
    tooltipContent,
    name,
    text,
    width,
    curText,
    handleOnChange,
    onFocus,
    onBlur,
    onKeyDown,
    onClear,
    placeholder,
    title,
    ariaLabel,
    ariaDescribedBy,
}) => {

    const { browserH, browserW, rdd, globalTextSize, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    var searchTextBoxWidth = 24;
    var textBoxHeight = '2.7vh'


    if      (rdd.isMobile && !rdd.isTablet && browserH > browserW) {textBoxHeight = '3.8vh'; searchTextBoxWidth=16;}
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { textBoxHeight = '7.8vh'; }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { textBoxHeight = '3.8vh'; }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { }




    // if (rdd.isMobile) {
    //     if (browserH > browserW) {
    //         if (rdd.isTablet) {
    //         }
    //         else {
    //             textBoxHeight = '3.8vh'
    //         }
    //     }
    //     else { // landscape
    //         if (rdd.isTablet) {
    //         }
    //         else {
    //             textBoxHeight = '7.8vh'
    //         }
    //     }
    // }



    var ttc = '';
    var ttp = 'right';
    if (tooltipContent !== undefined) {
        ttc = tooltipContent.slice(2);
        switch (tooltipContent.substring(0, 1)) {
            case 'r': ttp = 'right'; break;
            case 'l': ttp = 'left'; break;
            case 't': ttp = 'top'; break;
            case 'b': ttp = 'bottom'; break;
            default:break;
        }
    }

    return (

        <Tippy placement={ttp} disabled={!ttc} content={
            <div theme="tw" >
                {ttc}
            </div>
        }>

            <div style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
                <input
                    type="text"
                    value={curText}
                    onChange={handleOnChange}
                    onFocus={onFocus}
                    onBlur={onBlur}
                    onKeyDown={onKeyDown}
                    size={searchTextBoxWidth}
                    name={name}
                    id={name}
                    placeholder={placeholder}
                    title={title}
                    aria-label={ariaLabel}
                    aria-describedby={ariaDescribedBy}
                    style={{ fontSize: globalTextSize, height: textBoxHeight, backgroundColor: tc.inputBg, color: tc.text, border: '1px solid ' + tc.inputBorder, paddingRight: '16px' }}
                />
                {onClear && (
                    <span
                        onMouseDown={curText ? onClear : undefined}
                        style={{ position: 'absolute', right: '4px', cursor: curText ? 'pointer' : 'default', color: tc.text, fontSize: '11px', lineHeight: 1, userSelect: 'none', visibility: curText ? 'visible' : 'hidden' }}
                    >✕</span>
                )}
            </div>
        </Tippy>
    )
}

export default TextBoxS
