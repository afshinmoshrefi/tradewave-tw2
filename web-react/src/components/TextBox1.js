import React, { useState, useEffect, useContext } from 'react'
import { UserContext } from './UserContext'
import Tippy from '@tippyjs/react'
import { userAccessToSelectedSecurity, themeColors } from './Common'



const TextBox = ({ tooltipContent, name, text, width, tbBlur, tbEnter, securityTypeList2, selectedSecurity, browserH, browserW, qparams }) => {


    const { wpUserLevels, rdd, globalTextSize, loggedinUser, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)
    const [curText, SetCurText] = useState(text)



    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) { }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) { }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) { }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) { }





    //---------------------------------------------------------------------------
    useEffect(() => {
        SetCurText(text)  //holding state in the component just to make sure 
    }, [text])
    //---------------------------------------------------------------------------
    const handleOnChange = (event) => {

        // console.log('event triggered in textbox ',event.target.value,event)

        console.log('name=', name)

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
                <input type="text" value={curText} onBlur={tbBlur} onChange={handleOnChange} onKeyPress={tbEnter} size={width} id={name} style={{ fontWeight: textFontWeight, fontSize: textboxFontSize, height: textHeight, paddingLeft: paddingText, textAlign: textAlign, backgroundColor: tc.inputBg, color: tc.text, border: '1px solid ' + tc.inputBorder }} />
            </div>

        </Tippy>

    )
}

export default TextBox
