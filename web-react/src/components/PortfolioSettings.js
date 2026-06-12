import React, { useContext, useEffect, useRef, useState } from 'react'
import { UserContext } from './UserContext'
import { appserverURL, themeColors } from './Common'
import { twFetch } from './twFetch'
import './styles/InfoPopup.css'
import './styles/Portfolios.css'
import { GrClose } from "react-icons/gr";
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import { BsPlus, BsFolderSymlink, BsTrash3 } from "react-icons/bs"
import { GrEdit } from "react-icons/gr";
import { userlist_amp, userlist_auto } from './Common'


const PortfolioSettings = (props) => {


    const tc = themeColors(props.UITheme)
    const { numReportsAllowed, browserH, browserW, tableTitleTextSize, rdd, resourceObj, globalTextSize, infoTextSize, loggedinUser, token } = useContext(UserContext)


    const [message, SetMessage] = useState('')
    const [newText, SetNewText] = useState('')
    const [selPort, SetSelPort] = useState('main')
    const [numOppsSelectedPortfolio, SetNumOppsSelectedPortfolio] = useState(-1)

    const [msgColor, SetMsgColor] = useState('red')
    const [confirmDelete, SetConfirmDelete] = useState(false)

    const [dragPos, setDragPos] = useState(null)
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
        if (e.detail === 2) { setDragPos(null); return }
        const el = dialogRef.current
        if (!el) return
        const rect = el.getBoundingClientRect()
        dragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top }
        e.preventDefault()
    }

    var portfolio_settings_add_button_width = '97%';
    var portfolio_settings_edit_button_width = '45%';
    var portfolio_settings_del_button_width = '50%';

    // var portfolio_settings_textbox_width = ;
    // var portfolio_settings_select_width = ;


    var DialogH = '30%';
    var DialogW = '30%';
    var DialogT = '35%';
    var DialogL = '35%';
    var grclose_iconsize = 17;
    var icon_sizeP = 15;
    var icon_sizeE = 12;
    var icon_sizeD = 12;
    var title_text_size = '1vw';
    var button_height = '2.5vh'
    var textboxWidth = 24;

    var titleCloseDivWidth = '6%';
    var titleCenterDivWidth = '88%';

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
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {

        DialogH = '50%';
        DialogW = '60%';
        DialogT = '35%';
        DialogL = '20%';
        grclose_iconsize = 17;
        title_text_size = '2vw';
        textboxWidth = 17;
        button_height = '5.5vh'
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserW < 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';
        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 24;
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserH < 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';
        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 19;

    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW && browserH > 1024) {

        DialogH = '30%';
        DialogW = '70%';
        DialogT = '35%';
        DialogL = '15%';
        grclose_iconsize = 17;
        title_text_size = '2.2vw';
        textboxWidth = 26;
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW && browserW > 1024) {
        DialogH = '30%';
        DialogW = '40%';
        DialogT = '35%';
        DialogL = '30%';
        grclose_iconsize = 17;
        title_text_size = '1.6vw';
        textboxWidth = 23;

    }
    //------------------------------------------------------------------------------------------------------------
    // If ReportsDashboard has been dragged, position relative to it; otherwise use default percentages
    const rect = props.reportsDashRect;
    const useFixedPos = rect && !rdd.isMobile;

    const popupDialogStyle = {
        fontFamily: 'sans-serif',
        fontSize: '0.8vw',
        fontWeight: 'bold',
        backgroundColor: tc.panelBg,
        color: tc.text,
        height: DialogH,
        width: DialogW,
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid ' + tc.border,
        alignItems: 'center',
        zIndex: 7800,
        ...(dragPos
            ? { position: 'fixed', top: dragPos.y, left: dragPos.x, boxShadow: '0 8px 32px rgba(0,0,0,0.35)' }
            : useFixedPos
                ? { position: 'fixed', top: rect.top + (rect.height * 0.2), left: rect.left + (rect.width * 0.2) }
                : { position: 'absolute', top: DialogT, left: DialogL })
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    // first character of a portfolio name cannot be a special character unless the user has permission
    //-------------------------------------------------------------------------------------------------------------------------------------
    const isFirstCharAllowed = (name) => {
        let allowed = true;
        let c = name.charCodeAt(0);
        let first_char_is_special = (c >= 33 && c <= 47) || (c >= 58 && c <= 64) || (c >= 91 && c <= 96) || (c >= 123 && c <= 126);
        

        // user has permission to create a portfolio name that starts with &
        if (name[0] === '&' && userlist_amp.includes(props.loggedinUser)) {
            first_char_is_special = false;
        }

    
        return first_char_is_special
    };
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleAddNew = () => {

        if (props.portfolios.length === props.numPortfoliosAllowed) {
            SetMessage('Maximum # of Portfolios for your level is reached');
            SetMsgColor('red');
            return;
        }

        if (props.portfolios.length > props.numPortfoliosAllowed) {
            SetMessage('Maximum # of allowed portfolios is exceeded.  Delete Portfolios')
            SetMsgColor('red');
            return;
        }

        if (newText.trim().length == 0) {
            SetMessage('Enter a new Portfolio Name then click "Add Portfolio"')
            SetMsgColor('red');
            return;
        }

        if (isFirstCharAllowed(newText.trim())) {
            SetMessage('First character cannot be a special character')
            SetMsgColor('red');
            return;
        }

        // check if the name is unique before adding it
        for (let i = 0; i < props.portfolios.length; i++) {
            if (props.portfolios[i]['value'] === newText.trim()) {
                SetMessage(`${newText} name already exist`);
                SetMsgColor('red');
                return
            }
        }


        SetMessage(''); // clear red message

        let asURL = appserverURL()
        let url = `${asURL}/add_user_portfolio_name/${newText.trim()}?token=${token}`


        twFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })
            .then((data) => {

                // console.log('add portfolio returned new list:', data['portfolio_names_list'])
                let tmp = []
                for (let i = 0; i < data['portfolio_names_list'].length; i++) {
                    tmp.push({ id: data['portfolio_names_list'][i]['id'], value: data['portfolio_names_list'][i]['name'], label: data['portfolio_names_list'][i]['name'] });
                }
                // console.log('tmp=', tmp)
                props.SetPortfolios(tmp);
                SetMessage(`${newText} has been added`);
                SetMsgColor('green');

                // props.SetSelectedPortfolio(newText)  // set the current portfolio to the newly created portfolio

            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('Add portfolio name: Resource not found'); // handle a 404 error response
                } else {
                    console.log('Add portfolio name Error:', error.message); // handle any other error response
                }
            });

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleBlur = (event) => {
        SetNewText(event.target.value);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleEnter = (event) => {
        SetNewText(event.target.value);
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const portfolioChanged = (event) => {
        let value = event.target.value;
        SetSelPort(value);
        SetNewText(value);




        SetMessage('');
        SetConfirmDelete(false);

        let id = -1;

        // get the portfolio id number of the selected portfolio
        for (let i = 0; i < props.portfolios.length; i++) {
            if (props.portfolios[i]['value'] === value) {
                id = props.portfolios[i]['id']
                // console.log('found id=', id)
                break;
            }
        }

        // get how many opportunities in the selected portfolio

        if (id == -1) {
            console.log('in get_num_opps_for_portfolio profolio id wasn not found')
            return -1;  // not found for some reason
        }

        let asURL = appserverURL();
        let url = `${asURL}/dr_report_list/${id}/0?token=${token}`

        twFetch(url)
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })

            .then((data) => {
                let tmp = data['reports_list'];
                let num = tmp.length;
                SetNumOppsSelectedPortfolio(num); // set number of opportunities for the selected portfolio - used to check if we can delete or not
            })

            .catch((error) => {
                if (error.message === '404') {
                    console.log('Resource not found'); // handle a 404 error response
                    console.log('url=', url)
                } else {
                    console.log('Error:', error.message); // handle any other error response

                }
            });

    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleEdit = () => {
        let oldname = selPort
        let newname = newText.trim()

        if (oldname === 'main') {
            SetMessage('main Portfolio name cannot be edited')
            return;
        }

        if (newname.trim() === '') {
            SetMessage(`Enter a new name for ${oldname}`)
            return;
        }

        // check if potfolio name starts with & - cannot edit and change the name without first character being &
        if (oldname[0] === '&' && newname[0] !== '&'){
            SetMessage('Edited name must start with &');
            return
        }

        // check if the new name is unique before changing 
        for (let i = 0; i < props.portfolios.length; i++) {
            if (props.portfolios[i]['value'] === newname) {
                SetMessage(`${newname} name already exist`);
                return
            }
        }

        SetMessage(''); // clear red message

        let asURL = appserverURL()
        let url = `${asURL}/edit_user_portfolio_name/${oldname}/${newname}?token=${token}`

        // console.log('url=', url)

        twFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status); // throw an error if the response status is not OK
                }
                return response.json();
            })
            .then((data) => {

                let tmp = []
                for (let i = 0; i < data['portfolio_names_list'].length; i++) {
                    tmp.push({ id: data['portfolio_names_list'][i]['id'], value: data['portfolio_names_list'][i]['name'], label: data['portfolio_names_list'][i]['name'] });
                }
                props.SetPortfolios(tmp);
                SetMessage(`${oldname} is now changed to ${newname}`);

            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('edit portfolio name Resource not found'); // handle a 404 error response
                } else {
                    console.log('edit portfolio name -Error:', error.message); // handle any other error response
                }
            });

    }
    //-------------------------------------------------------------------------------------------------------------------------------------

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleDelete = () => {

        let delname = selPort

        if (delname === 'main') {
            SetMessage('main Portfolio cannot be deleted')
            SetMsgColor('red')
            return;
        }

        // if portfolio has opportunities, show confirmation prompt
        if (numOppsSelectedPortfolio > 0 && !confirmDelete) {
            let oppWord = numOppsSelectedPortfolio === 1 ? 'opportunity' : 'opportunities'
            SetMessage(`"${delname}" has ${numOppsSelectedPortfolio} ${oppWord} that will be permanently deleted. This cannot be undone.`)
            SetMsgColor('red')
            SetConfirmDelete(true)
            return
        }

        // proceed with deletion (either empty portfolio or user confirmed)
        SetConfirmDelete(false)
        SetMessage('')

        props.SetSelectedPortfolio('main')

        let asURL = appserverURL()
        let url = `${asURL}/del_user_portfolio_name/${delname}?token=${token}`

        twFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(response.status)
                }
                return response.json();
            })
            .then((data) => {
                let tmp = []
                for (let i = 0; i < data['portfolio_names_list'].length; i++) {
                    tmp.push({ id: data['portfolio_names_list'][i]['id'], value: data['portfolio_names_list'][i]['name'], label: data['portfolio_names_list'][i]['name'] });
                }
                props.SetPortfolios(tmp);
                SetMessage(`${delname} has been deleted.`)
                SetMsgColor('green')
                SetNewText('')
                props.SetSelectedPortfolioID(0)
            })
            .catch((error) => {
                if (error.message === '404') {
                    console.log('del portfolio name Resource not found');
                } else {
                    console.log('del portfolio name -Error:', error.message);
                }
            });
    }
    //-------------------------------------------------------------------------------------------------------------------------------------
    return (

        <div ref={dialogRef} style={popupDialogStyle}   >

            <div style={{ width: '100%', height: '12%', backgroundColor: tc.titleBar, display: 'flex', cursor: rdd.isMobile ? 'default' : 'move' }} onMouseDown={handleTitleMouseDown}>
                <div style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'transparent' }}></div>
                <div className='div_basic' style={{ height: '100%', width: titleCenterDivWidth, backgroundColor: 'transparent' }}><span style={{ fontSize: title_text_size, color: tc.textOnControl }}>Portfolio Settings</span></div>
                <div className='div_basic' onClick={() => { props.SetShowPortfolioSettings(false) }} style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: tc.closeBtnBg }}><GrClose size={grclose_iconsize} /></div>
            </div>

            <div className='div_basic' style={{ width: '100%', height: '88%', backgroundColor: 'transparent', flexDirection: 'column' }}>
                <div className='div_basic' style={{ width: '80%', height: '35%', backgroundColor: 'transparent', paddingBottom: '2%', fontSize: globalTextSize }}>
                    <div className='div_basic' style={{ backgroundColor: tc.statLabelBg, height: '2.5em', width: '100%', borderBottom: '4px solid ' + tc.border, paddingTop: '4px' }}>
                        # Portfolios: {props.portfolios.length} / {props.numPortfoliosAllowed}
                    </div>
                </div>
                <div className='div_basic' style={{ width: '80%', height: '20%', backgroundColor: 'transparent' }}>

                    <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', marginRight: '5px', backgroundColor: 'transparent', width: '50%' }}><button onClick={handleAddNew} style={{ width: portfolio_settings_add_button_width, height: button_height }}><BsPlus size={icon_sizeP} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Add Portfolio</button></div>

                    <div style={{ backgroundColor: 'transparent', width: '50%' }}><TextBox name='new_textbox' text={newText} tbBlur={handleBlur} width={textboxWidth} tbEnter={handleEnter} tooltipContent={props.tooltipSW ? 'b,Enter Portfolio Name' : ''} /></div>

                </div>

                <div style={{ width: '80%', height: '30%', backgroundColor: 'transparent' }}>

                    <div className='div_basic' style={{ width: '100%', height: '60%', backgroundColor: 'transparent' }}>
                        {confirmDelete ? (
                            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', width: '100%', backgroundColor: 'transparent', flexDirection: 'row', gap: '10px' }}>
                                <button onClick={handleDelete} style={{ height: button_height, backgroundColor: '#d32f2f', color: 'white', border: 'none', padding: '0 12px', cursor: 'pointer' }}><BsTrash3 size={icon_sizeD} style={{ verticalAlign: "middle" }} />&nbsp;Delete Forever</button>
                                <button onClick={() => { SetConfirmDelete(false); SetMessage(''); }} style={{ height: button_height, padding: '0 12px' }}>Cancel</button>
                            </div>
                        ) : (
                            <>
                                <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', height: '100%', width: '50%', backgroundColor: 'transparent', flexDirection: 'row' }}>
                                    <button onClick={handleEdit} style={{ width: portfolio_settings_edit_button_width, marginRight: '5px', height: button_height }}><GrEdit size={icon_sizeE} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Edit</button>
                                    <button onClick={handleDelete} style={{ width: portfolio_settings_del_button_width, height: button_height }}><BsTrash3 size={icon_sizeD} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Delete</button>
                                </div>
                                <div style={{ paddingLeft: '5px', display: 'flex', justifyContent: 'left', alignItems: 'center', height: '100%', width: '50%', backgroundColor: 'transparent' }}>
                                    <SelectBox optionList={props.portfolios} name="portfolios" value={selPort} sbChanged={portfolioChanged} />
                                </div>
                            </>
                        )}
                    </div>
                    <div style={{ height: '70%', width: '100%', backgroundColor: 'transparent', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                        <span style={{ color: msgColor, fontSize: globalTextSize }}>{message}</span>
                    </div>
                </div>
            </div>
        </div>
    )
}
export default PortfolioSettings
