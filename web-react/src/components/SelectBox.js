// first 2 characters of tooltip content define the position.  
// l, is left tooltip while b, is bottom tooltip

import React, { useContext } from 'react'
import { UserContext } from './UserContext'
import { themeColors } from './Common'
import Tippy from '@tippyjs/react'
// import 'tippy.js/dist/tippy.css'

const SelectBox = ({ optionList, value, name, suffix, sbChanged, tooltipContent, widthOverride, ariaLabel, fitContainer = false }) => {

    const { rdd, globalTextSize, browserH, browserW, UITheme } = useContext(UserContext)
    const tc = themeColors(UITheme)

    var textAligncustom = 'left';
    if (name === 'minMFEfilters' || name === 'oppBySymbol') textAligncustom = 'center';
    var selectHeight = '2.4vh';
    var selectWidth = '4vw';

    var selectBackgroundColor = tc.selectBg;
    var selectFontSize = globalTextSize;
    var suffix2 = suffix; // added to make changes for tablet portrait 8/31/2022

    if (name === 'portfolios') selectWidth = '6vw'; // desktop for portfolios
    if (name === 'wl_resource_group' || name === 'watchlists') selectWidth = '8vw'; // desktop for watchlist settings


    if (rdd.isMobile && !rdd.isTablet && window.innerHeight > window.innerWidth) { // smartphone portrait
        selectHeight = '3.7vh';
        selectWidth = '18vw';
        switch (name) {
            case 'filter':
                selectWidth = '35vw';
                break;
            case 'years':
                selectWidth = '20vw';
                break;
            case 'partialYears':
                selectWidth = '24vw';
                break;
            case 'securityTypeListP':
                selectWidth = '13em';
                break;
            case 'securityTypeList':
                selectWidth = '40vw';
                break;
            case 'months':
                selectWidth = '15vw';
                break;
            case 'selectedDays': // this is in populate portfolio
                selectWidth = '14vw';
                break;
            case 'waveend':
                selectWidth = '24vw';
                selectHeight = '2vh';
                break;
            case 'earlyexcercise':
                selectWidth = '24vw';
                selectHeight = '2vh';
                break;
            case 'day':
                selectWidth = '12vw';
                break;
            case 'portfolios':
                selectWidth = '25vw';
                selectHeight = '4vh';
                break;
            case 'wl_resource_group':
            case 'watchlists':
                selectWidth = '36vw';
                break;
            case 'numTopOpportunitiesForEmail':
                selectWidth = '46vw';
                selectHeight = '3.3vh';
                break;
            case 'longOrShort':
                selectWidth = '10em';
                break;
            case 'monthsP':
            case 'dayP':
            case 'yearsP':
            case 'partialYearsP':
                selectWidth = '9em';
                break;
            case 'minMFEfilters':
            case 'minMFEpct':
                selectWidth = '3.5em';
                break;
            default:
                break;
        }
    }
    else if (rdd.isMobile && !rdd.isTablet && window.innerHeight < window.innerWidth) { //smartphone landscape
        selectHeight = '7.2vh';
        selectWidth = '18vw';
        switch (name) {
            case 'filter':
                selectWidth = '50vw';
                break;
            case 'months':
                selectWidth = '14vw';
                break;
            case 'years':
                selectWidth = '12vw';
                break;
            case 'monthsAndQtrs':
                selectWidth = '16vw';
                break;
            case 'daysout':
                selectWidth = '14vw';
                break;
            case 'day':
                selectWidth = '10vw';
                break;
            case 'securityTypeList':
                selectWidth = '28vw';
                break;
            case 'portfolios':
                selectWidth = '22vw';
                selectHeight = '5.4vh';
                break;
            case 'wl_resource_group':
            case 'watchlists':
                selectWidth = '36vw';
                break;
            case 'numTopOpportunitiesForEmail':
                selectWidth = '100%';
                selectHeight = '5.4vh';
                break;

            default:
                break;
        }
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight > window.innerWidth) { // tablet portrait
        selectWidth = '14vw';
        selectFontSize = '1.7vw';
        switch (name) {
            case 'filter':
                selectWidth = '50vw';
                break;
            case 'years':
                selectWidth = '8vw';
                suffix2 = 'yrs'
                break;
            case 'partialYears':
                selectWidth = '18vw';
                break;
            case 'securityTypeList':
                selectWidth = '30vw';
                break;
            case 'day':
                selectWidth = '7vw';
                break;
            case 'daysout':
                selectWidth = '10vw';
                suffix2 = 'days';
                break;
            case 'months':
                selectWidth = '15vw';
                break;
            case 'monthsAndQtrs':
                selectWidth = '15vw';
                break;
            case 'portfolios':
                selectWidth = '26vw';
                break;
            case 'wl_resource_group':
            case 'watchlists':
                selectWidth = '28vw';
                break;
            case 'minMFEfilters':
            case 'minMFEpct':
                selectWidth = '4.5em';
                break;
            case 'selectedDays': // this is in populate portfolio
                selectWidth = '6vw';
                break;
            case 'numTopOpportunitiesForEmail':
                selectWidth = '34vw';
                selectHeight = '2.5vh';
                break;
            default:
                break;
        }
    }
    else if (rdd.isMobile && rdd.isTablet && window.innerHeight < window.innerWidth) { //tablet landscape

        selectWidth = '10vw';
        switch (name) {
            case 'filter':
                selectWidth = '18vw';
                break;
            case 'years':
                selectWidth = '6vw';
                break;
            case 'partialYears':
                selectWidth = '9vw';
                break;
            case 'securityTypeList':
                selectWidth = '16vw';
                break;
            case 'day':
                selectWidth = '4vw';
                break;
            case 'daysout':
                selectWidth = '7vw';
                break;
            case 'months':
                selectWidth = '5vw';
                break;
            case 'monthsAndQtrs':
                selectWidth = '9vw';
                break;
            case 'portfolios':
                selectWidth = '14vw';
                break;
            case 'wl_resource_group':
            case 'watchlists':
                selectWidth = '20vw';
                break;
            case 'minMFEfilters':
            case 'minMFEpct':
                selectWidth = '4.5em';
                break;
            case 'selectedDays': // this is in populate portfolio
                selectWidth = '6vw';
                break;
            case 'numTopOpportunitiesForEmail':
                console.log('browserH=', browserH)
                if (browserW > 1024) {   //ipad pro
                    selectWidth = '19vw';
                }
                else { // regular ipad
                    selectWidth = '100%';
                }
                selectHeight = '2.5vh';
                break;

            default:
                break;
        }


    }
    else if (!rdd.isMobile) {                                       // desktop
        selectHeight = '2.7vh';
        switch (name) {

            case 'filter':
                selectWidth = '8vw';
                break;
            case 'monthsAndQtrs':
                selectWidth = '6.5vw';
                break;
            case 'securityTypeList':
                selectWidth = '8vw';
                break;
            case 'waveend':
                // selectWidth = '24vw';
                selectHeight = '2.1vh';
                break;
            case 'earlyexcercise':
                // selectWidth = '24vw';
                selectHeight = '2.1vh';
                break;
            case 'securityTypeListP':
                selectWidth = '11em';
                selectFontSize = '0.6vw';
                break;
            case 'daysout':
                selectWidth = '4.5vw';
                break;
            case 'years':
                selectWidth = '4vw';
                break;
            case 'PEselection':
                selectWidth = '4.5vw';
                break;
            case 'oppBySymbol':
                // Sized for the closed "Best Waves" placeholder - the toolbar row is
                // width-critical; the OPEN dropdown popup still expands to fit the
                // full option labels (Chrome/Firefox/Edge behavior).
                selectWidth = '5.2vw';
                break;
            case 'day':
                selectWidth = '4vw';
                break;
            case 'months':
                selectWidth = '5vw';
                break;
            case 'selectedDays':
                selectWidth = '2.4vw';
                break;
            case 'minMFEfilters':
            case 'minMFEpct':
                selectWidth = '3.4vw';
                selectFontSize = '0.6vw';
                break;
            case 'numTopOpportunitiesForEmail':
                selectWidth = '12vw';
                selectHeight = '2.4vh';
                break;
            case 'longOrShort':
                selectWidth = '12em';
                break;
            case 'monthsP':
            case 'dayP':
            case 'yearsP':
            case 'partialYearsP':
            case 'tradeTypes':
                selectWidth = '9em';
                break;
            // case 'wl_resource_group':
            //     selectWidth = '4vw';
            //     break;
            default:
                break;
        }
    }



    // Caller-supplied width wins over the per-name sizing above (e.g. the Best Waves
    // select widens to fit its "-- Best Waves --" placeholder only when the panel is wide).
    if (widthOverride) selectWidth = widthOverride;

    // console.log('name=', name)


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

    // console.log('sb value=',value)

    return (
        <div style={fitContainer ? { width: '100%', minWidth: 0, display: 'flex', justifyContent: 'center' } : undefined}>

            <Tippy placement={ttp} disabled={!ttc} content={
                <div theme="tw" >
                    {ttc}
                </div>
            }>
                <select aria-label={ariaLabel} onChange={sbChanged} id={name} value={value} style={{ fontSize: selectFontSize, backgroundColor: selectBackgroundColor, color: tc.selectText, border: '1px solid ' + tc.selectBorder, height: selectHeight, width: selectWidth, maxWidth: fitContainer ? '100%' : undefined, minWidth: fitContainer ? 0 : undefined, textAlign: textAligncustom, colorScheme: UITheme === 'dark' ? 'dark' : 'light' }}>
                    {optionList.map((x) => (
                        // x.locked = an over-tier (e.g. above the years cap) option: grayed for the
                        // upgrade nudge but NOT disabled, so selecting it still fires onChange and the
                        // handler can open the upgrade dialog (a disabled <option> can't be clicked).
                        <option key={x.id} value={x.value} hidden={x.hidden === true} disabled={x.type === 'SEP'} style={{ fontSize: globalTextSize, ...((x.type === 'SEP' || x.locked) ? { fontStyle: 'italic', color: '#999' } : {}) }}> {x.label}{suffix2} </option>
                    ))}

                </select>
            </Tippy>

        </div>
    )
}



export default SelectBox
