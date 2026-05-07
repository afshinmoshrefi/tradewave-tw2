import React, { useContext } from 'react'
import Tippy from '@tippyjs/react'

import { UserContext } from './UserContext'
import { themeColors } from './Common'

const CheckBox = ({ tooltipContent, label, cbChanged, checked, textSide, textColor, disabled }) => { //textSide is either left or right. default left

    const { checkboxZoom, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    var cb_text_color = textColor;


    if (cb_text_color === undefined){
        cb_text_color = 'white';
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

        <Tippy  placement={ttp} disabled={!ttc} content={
            <div theme="tw" >
                {ttc}
            </div>
        }>
            {textSide === 'right'
                ?
                <div style={{ whiteSpace: "nowrap", display: 'flex', alignItems: 'center', backgroundColor: 'transparent', opacity: disabled ? 0.75 : 1 }}>

                    <div style={{ height: '100%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }} >
                        <input type="checkbox" value={label} onChange={disabled ? undefined : cbChanged} checked={checked} disabled={disabled} style={{ zoom: checkboxZoom }} />
                    </div>

                    {label !== 'email_reminder' && label !== 'popup_reminder' &&
                        <div style={{ height: '100%', backgroundColor: 'transparent' }} >
                            <span style={{ color: cb_text_color, }}>{label}</span>
                        </div>
                    }


                </div>
                :
                <div style={{ whiteSpace: "nowrap", display: 'flex', alignItems: 'center', backgroundColor: 'transparent', opacity: disabled ? 0.75 : 1 }}>
                    {label !== 'email_reminder' && label !== 'popup_reminder' &&
                        <div style={{ height: '100%', backgroundColor: 'transparent' }} >
                            <span style={{ color: cb_text_color, }}>{label}</span>
                        </div>
                    }
                    <div style={{ height: '100%', backgroundColor: 'transparent', display: 'flex', alignItems: 'center' }} >
                        <input type="checkbox" value={label} name={label} onChange={disabled ? undefined : cbChanged} checked={checked} disabled={disabled} style={{ zoom: checkboxZoom }} />
                    </div>

                </div>
            }
        </Tippy>
    )
}

export default CheckBox
