import React, { useContext, useEffect, useState, useRef } from 'react'
import { UserContext } from './UserContext'
import { appserverURL, themeColors } from './Common'
import { getSelectedIDFromSecuritiesList2 } from './Common'
import './styles/InfoPopup.css'
import { GrClose } from "react-icons/gr"
import SelectBox from './SelectBox'
import TextBox from './TextBox'
import CheckBox from './CheckBox'
import { BsPlus, BsTrash3, BsUpload } from "react-icons/bs"
import { GrEdit } from "react-icons/gr"


const WatchlistSettings = (props) => {

    const tc = themeColors(props.UITheme)
    const { browserH, browserW, rdd, globalTextSize, token } = useContext(UserContext)
    const dialogRef = useRef(null)

    // Close on click outside
    useEffect(() => {
        const onMouseDown = (e) => {
            if (dialogRef.current && !dialogRef.current.contains(e.target)) {
                props.SetShowWatchlistSettings(false)
            }
        }
        document.addEventListener('mousedown', onMouseDown)
        return () => document.removeEventListener('mousedown', onMouseDown)
    }, [])

    // Drag support (desktop only)
    const [dragPos, setDragPos] = useState(null)
    const dragRef = useRef({ active: false, offsetX: 0, offsetY: 0 })

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
        if (!dialogRef.current) return
        const rect = dialogRef.current.getBoundingClientRect()
        dragRef.current = { active: true, offsetX: e.clientX - rect.left, offsetY: e.clientY - rect.top }
        e.preventDefault()
    }

    const [message, SetMessage] = useState('')
    const [msgColor, SetMsgColor] = useState('red')
    const [newText, SetNewText] = useState('')
    const [selWatchlist, SetSelWatchlist] = useState('')
    const [watchlistItems, SetWatchlistItems] = useState([])
    const [newSymbol, SetNewSymbol] = useState('')
    const [selResourceGroup, SetSelResourceGroup] = useState('')

    // CSV import state
    const [csvMode, SetCsvMode] = useState(false)
    const [csvParsedSymbols, SetCsvParsedSymbols] = useState([])
    const [csvDetection, SetCsvDetection] = useState(null)
    const [csvWatchlistName, SetCsvWatchlistName] = useState('')
    const [csvImporting, SetCsvImporting] = useState(false)
    const [csvStep, SetCsvStep] = useState(0) // 0=select file, 1=preview, 2=done
    const [csvResult, SetCsvResult] = useState(null)

    var DialogH = '50%';
    var DialogW = '30%';
    var DialogT = '25%';
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
        DialogH = '60%';
        DialogW = '100%';
        DialogT = '15%';
        DialogL = '0';
        title_text_size = '4.5vw';
        textboxWidth = 16;
        button_height = '4vh';
        titleCloseDivWidth = '10%';
        titleCenterDivWidth = '80%';
    }
    else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
        DialogH = '65%';
        DialogW = '60%';
        DialogT = '20%';
        DialogL = '20%';
        title_text_size = '2vw';
        textboxWidth = 17;
        button_height = '5.5vh';
    }
    else if (rdd.isMobile && rdd.isTablet && browserH > browserW) {
        DialogH = '50%';
        DialogW = '70%';
        DialogT = '25%';
        DialogL = '15%';
        title_text_size = '2.2vw';
        textboxWidth = 24;
    }
    else if (rdd.isMobile && rdd.isTablet && browserH < browserW) {
        DialogH = '50%';
        DialogW = '40%';
        DialogT = '25%';
        DialogL = '30%';
        title_text_size = '1.6vw';
        textboxWidth = 19;
    }

    const popupDialogStyle = {
        fontFamily: 'sans-serif',
        fontSize: '0.8vw',
        fontWeight: 'bold',
        position: 'absolute',
        backgroundColor: tc.panelBg,
        color: tc.text,
        height: DialogH,
        width: DialogW,
        ...(dragPos
            ? { position: 'fixed', top: dragPos.y, left: dragPos.x, boxShadow: '0 8px 32px rgba(0,0,0,0.35)' }
            : { top: DialogT, left: DialogL }),
        display: 'flex',
        flexDirection: 'column',
        border: '2px solid ' + tc.border,
        alignItems: 'center',
        zIndex: 7800
    }

    // Merge related resource groups into single entries for watchlist dropdown
    // US Stocks: DOW 30(0), NASDAQ 100(1), S&P 500(2), RUSSELL 1000(3), WILSHIRE 5000(4) -> use 4 (broadest)
    // Indices: INDICES COMMON(5), INDICES ALL(6) -> use 6 (broadest)
    // Forex: FOREX LIQUID(9), FOREX ALL(8) -> use 8 (broadest)
    const mergedGroups = {
        usStocks:  { ids: [0, 1, 2, 3, 4], label: 'US Stocks', resourceId: 4 },
        indices:   { ids: [5, 6],           label: 'INDICES',    resourceId: 6 },
        forex:     { ids: [8, 9],           label: 'FOREX',      resourceId: 8 },
    }
    const allMergedIds = Object.values(mergedGroups).flatMap(g => g.ids)

    // build condensed securities group list: merge related groups into single entries
    const watchlistResourceList = (() => {
        if (!props.securityTypeList || props.securityTypeList.length === 0) return []
        let seen = {}
        let result = []
        // filter out separator and watchlist entries from the combined securities list
        const baseList = props.securityTypeList.filter(x => x.type !== 'SEP' && x.type !== 'WL')
        for (let item of baseList) {
            let merged = Object.values(mergedGroups).find(g => g.ids.includes(item.id))
            if (merged) {
                if (!seen[merged.label]) {
                    result.push({ id: merged.resourceId, value: merged.label, label: merged.label })
                    seen[merged.label] = true
                }
            } else if (item.value !== 'More...') {
                result.push(item)
            }
        }
        return result
    })()

    // helper: normalize resource name for display (map any merged group ID to its merged label)
    const displayResourceName = (rName, rId) => {
        let merged = Object.values(mergedGroups).find(g => g.ids.includes(Number(rId)))
        if (merged) return merged.label
        return rName || ''
    }

    // build SelectBox option list from watchlists - show resource group in label
    const watchlistOptions = props.watchlists.map(w => ({
        id: w.id,
        value: w.name,
        label: w.name + (w.resourceName ? ' (' + displayResourceName(w.resourceName, w.resourceId) + ')' : '')
    }))

    // get the resource group for the currently selected watchlist
    const getSelectedWatchlistResource = () => {
        let w = props.watchlists.find(w => w.name === selWatchlist)
        return w || {}
    }

    // on mount, select the first watchlist if any and set default resource group
    useEffect(() => {
        if (props.watchlists.length > 0 && selWatchlist === '') {
            let defWL = props.watchlists.find(w => w.isDefault)
            let name = defWL ? defWL.name : props.watchlists[0].name
            SetSelWatchlist(name)
            fetchItems(name)
        }
        if (watchlistResourceList.length > 0 && selResourceGroup === '') {
            SetSelResourceGroup(watchlistResourceList[0].value)
        }
    }, [])

    const fetchItems = (name) => {
        let asURL = appserverURL()
        fetch(`${asURL}/get_user_watchlist_items/${name}?token=${token}`)
            .then(res => res.json())
            .then(data => {
                if (data['watchlist_items'] && Array.isArray(data['watchlist_items'])) {
                    SetWatchlistItems(data['watchlist_items'])
                }
            })
            .catch(err => console.log('fetch watchlist items error:', err.message))
    }

    const isDefault = () => {
        let w = props.watchlists.find(w => w.name === selWatchlist)
        return w ? w.isDefault : false
    }

    const isAddToSecurities = () => {
        let w = props.watchlists.find(w => w.name === selWatchlist)
        return w ? (w.addToSecurities || false) : false
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleAddNew = () => {
        if (props.watchlists.length >= props.numWatchlistsAllowed) {
            SetMessage('Maximum # of Watchlists for your level is reached')
            SetMsgColor('red')
            return
        }

        if (newText.trim().length === 0) {
            SetMessage('Enter a new Watchlist Name then click "Add Watchlist"')
            SetMsgColor('red')
            return
        }

        if (selResourceGroup === '') {
            SetMessage('Select a securities group first')
            SetMsgColor('red')
            return
        }

        for (let i = 0; i < props.watchlists.length; i++) {
            if (props.watchlists[i].name === newText.trim()) {
                SetMessage(`${newText} name already exists`)
                SetMsgColor('red')
                return
            }
        }

        SetMessage('')
        let mergedMatch = Object.values(mergedGroups).find(g => g.label === selResourceGroup)
        let resourceId = mergedMatch ? mergedMatch.resourceId : getSelectedIDFromSecuritiesList2(props.securityTypeList, selResourceGroup)
        let asURL = appserverURL()
        fetch(`${asURL}/add_user_watchlist_name/${newText.trim()}/${resourceId}/${selResourceGroup}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                if (data['watchlist_names_list'] === 'limit_reached') {
                    SetMessage('Maximum # of Watchlists for your level is reached')
                    SetMsgColor('red')
                    return
                }
                if (data['watchlist_names_list'] === 'duplicate') {
                    SetMessage(`${newText} name already exists`)
                    SetMsgColor('red')
                    return
                }
                props.SetWatchlists(data['watchlist_names_list'])
                SetMessage(`${newText} has been added`)
                SetMsgColor('green')

                if (data['new_watchlist'] && data['new_watchlist'].isDefault) {
                    props.SetDefaultWatchlistName(data['new_watchlist'].name)
                    props.SetDefaultWatchlistItems([])
                }

                if (selWatchlist === '') {
                    SetSelWatchlist(newText.trim())
                    SetWatchlistItems([])
                }
                SetNewText('')
            })
            .catch(err => console.log('add watchlist error:', err.message))
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleEdit = () => {
        if (selWatchlist === '') {
            SetMessage('Select a watchlist first')
            SetMsgColor('red')
            return
        }

        if (newText.trim() === '') {
            SetMessage(`Enter a new name for ${selWatchlist}`)
            SetMsgColor('red')
            return
        }

        if (newText.trim() === selWatchlist) {
            SetMessage('New name is the same as current name')
            SetMsgColor('red')
            return
        }

        for (let i = 0; i < props.watchlists.length; i++) {
            if (props.watchlists[i].name === newText.trim()) {
                SetMessage(`${newText} name already exists`)
                SetMsgColor('red')
                return
            }
        }

        SetMessage('')
        let oldName = selWatchlist
        let newName = newText.trim()
        let asURL = appserverURL()
        fetch(`${asURL}/edit_user_watchlist_name/${oldName}/${newName}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                props.SetWatchlists(data['watchlist_names_list'])
                SetSelWatchlist(newName)
                SetMessage(`${oldName} is now changed to ${newName}`)
                SetMsgColor('green')

                if (props.defaultWatchlistName === oldName) {
                    props.SetDefaultWatchlistName(newName)
                }
            })
            .catch(err => console.log('edit watchlist error:', err.message))
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleDelete = () => {
        if (selWatchlist === '') {
            SetMessage('Select a watchlist first')
            SetMsgColor('red')
            return
        }

        if (watchlistItems.length > 0) {
            if (!window.confirm(`${selWatchlist} has ${watchlistItems.length} symbol${watchlistItems.length > 1 ? 's' : ''}. Delete this watchlist?`)) return
        }

        SetMessage('')
        let delName = selWatchlist
        let asURL = appserverURL()
        fetch(`${asURL}/del_user_watchlist_name/${delName}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                props.SetWatchlists(data['watchlist_names_list'])
                SetMessage(`${delName} has been deleted`)
                SetMsgColor('green')
                SetWatchlistItems([])
                SetNewText('')

                if (props.defaultWatchlistName === delName) {
                    props.SetDefaultWatchlistName('')
                    props.SetDefaultWatchlistItems([])
                }

                if (data['watchlist_names_list'].length > 0) {
                    SetSelWatchlist(data['watchlist_names_list'][0].name)
                    fetchItems(data['watchlist_names_list'][0].name)
                } else {
                    SetSelWatchlist('')
                }
            })
            .catch(err => console.log('del watchlist error:', err.message))
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleSetDefault = () => {
        if (selWatchlist === '') return

        let asURL = appserverURL()
        fetch(`${asURL}/set_default_watchlist/${selWatchlist}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                props.SetWatchlists(data['watchlist_names_list'])
                props.SetDefaultWatchlistName(selWatchlist)
                props.SetDefaultWatchlistItems(watchlistItems)
                SetMessage(`${selWatchlist} is now the default watchlist`)
                SetMsgColor('green')
            })
            .catch(err => console.log('set default watchlist error:', err.message))
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleSetAddToSecurities = () => {
        if (selWatchlist === '') return
        const current = isAddToSecurities()
        let asURL = appserverURL()
        fetch(`${asURL}/set_watchlist_add_to_securities/${selWatchlist}/${!current}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                props.SetWatchlists(data['watchlist_names_list'])
                SetMessage(current ? 'Removed from securities list' : 'Added to securities list')
                SetMsgColor('green')
            })
            .catch(err => console.log('set addToSecurities error:', err.message))
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const watchlistChanged = (event) => {
        let value = event.target.value
        SetSelWatchlist(value)
        SetNewText(value)
        SetMessage('')
        fetchItems(value)
    }

    const resourceGroupChanged = (event) => {
        SetSelResourceGroup(event.target.value)
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleBlur = (event) => {
        SetNewText(event.target.value)
    }
    const handleEnter = (event) => {
        SetNewText(event.target.value)
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleSymbolBlur = (event) => {
        SetNewSymbol(event.target.value)
    }
    const handleSymbolEnter = (event) => {
        let val = event.target.value
        SetNewSymbol(val)
        if (event.key === 'Enter' && val.trim().length > 0) handleAddSymbol(val)
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleAddSymbol = (overrideSym) => {
        if (selWatchlist === '') {
            SetMessage('Select a watchlist first')
            SetMsgColor('red')
            return
        }

        let raw = overrideSym !== undefined ? overrideSym : newSymbol
        if (raw.trim().length === 0) {
            SetMessage('Enter a symbol to add')
            SetMsgColor('red')
            return
        }

        if (watchlistItems.length >= props.numWatchlistItemsAllowed) {
            SetMessage('Maximum # of symbols for your level is reached')
            SetMsgColor('red')
            return
        }

        let sym = raw.trim().toUpperCase()

        // get the resource ID for this watchlist's securities group
        // for merged groups, always validate against the broadest universe
        let wl = props.watchlists.find(w => w.name === selWatchlist)
        let mergedGrp = wl ? Object.values(mergedGroups).find(g => g.ids.includes(Number(wl.resourceId))) : null
        let resourceId = wl ? (mergedGrp ? mergedGrp.resourceId : wl.resourceId) : 0

        // validate symbol via NameFromTicker before adding
        let asURL = appserverURL()
        SetMessage('Validating...')
        SetMsgColor(tc.text)
        fetch(`${asURL}/NameFromTicker/${resourceId}/${sym}?token=${token}`)
            .then(res => res.json())
            .then(g => {
                if (g['name'] && g['name'] !== '') {
                    // symbol is valid - add it
                    fetch(`${asURL}/add_user_watchlist_item/${selWatchlist}/${sym}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                        .then(res => res.json())
                        .then(data => {
                            if (data['watchlist_items'] === 'duplicate') {
                                SetMessage(`${sym} already in this watchlist`)
                                SetMsgColor('red')
                                return
                            }
                            if (data['watchlist_items'] === 'limit_reached') {
                                SetMessage('Maximum # of symbols for your level is reached')
                                SetMsgColor('red')
                                return
                            }
                            SetWatchlistItems(data['watchlist_items'])
                            SetMessage(`${sym} (${g['name']}) added`)
                            SetMsgColor('green')
                            SetNewSymbol('')

                            if (selWatchlist === props.defaultWatchlistName) {
                                props.SetDefaultWatchlistItems(data['watchlist_items'])
                            }
                        })
                        .catch(err => { SetMessage('Error adding symbol'); SetMsgColor('red'); console.log('add watchlist item error:', err.message) })
                } else {
                    let rName = wl ? displayResourceName(wl.resourceName, wl.resourceId) : ''
                    SetMessage(`${sym} not found in ${rName}`)
                    SetMsgColor('red')
                }
            })
            .catch(err => { SetMessage('Error validating symbol'); SetMsgColor('red'); console.log('NameFromTicker error:', err.message) })
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    // CSV Import handlers
    //-------------------------------------------------------------------------------------------------------------------------------------
    const resetCsvImport = () => {
        SetCsvMode(false)
        SetCsvParsedSymbols([])
        SetCsvDetection(null)
        SetCsvWatchlistName('')
        SetCsvImporting(false)
        SetCsvStep(0)
        SetCsvResult(null)
    }

    const handleCsvFileSelect = (event) => {
        let file = event.target.files[0]
        if (!file) return

        SetMessage('')
        let reader = new FileReader()
        reader.onload = (e) => {
            let text = e.target.result
            let lines = text.split(/\r?\n/).filter(l => l.trim().length > 0)
            if (lines.length === 0) {
                SetMessage('CSV file is empty')
                SetMsgColor('red')
                return
            }

            // detect header row - look for known symbol column names
            let headerNames = ['symbol', 'ticker', 'sym', 'stock', 'symbols']
            let firstRow = lines[0].split(',').map(c => c.trim().replace(/"/g, '').toLowerCase())
            let symColIdx = -1
            for (let i = 0; i < firstRow.length; i++) {
                if (headerNames.includes(firstRow[i])) { symColIdx = i; break }
            }

            let startRow = 0
            if (symColIdx >= 0) {
                startRow = 1 // skip header
            } else {
                symColIdx = 0 // no header found, use first column
            }

            // extract symbols
            let seen = new Set()
            let symbols = []
            for (let i = startRow; i < lines.length && symbols.length < 500; i++) {
                let cols = lines[i].split(',')
                if (cols.length > symColIdx) {
                    let sym = cols[symColIdx].trim().replace(/"/g, '').toUpperCase()
                    if (sym.length > 0 && !seen.has(sym)) {
                        seen.add(sym)
                        symbols.push(sym)
                    }
                }
            }

            if (symbols.length === 0) {
                SetMessage('No symbols found in CSV')
                SetMsgColor('red')
                return
            }

            SetCsvParsedSymbols(symbols)

            // auto-fill watchlist name from filename (without extension)
            let fname = file.name.replace(/\.(csv|txt)$/i, '').trim()
            if (fname.length > 0) SetCsvWatchlistName(fname)

            // detect resource group
            detectResourceGroup(symbols)
        }
        reader.readAsText(file)
    }

    const detectResourceGroup = (symbols) => {
        SetMessage('Detecting securities group...')
        SetMsgColor(tc.text)
        let asURL = appserverURL()
        let encoded = window.btoa(symbols.join(','))
        fetch(`${asURL}/detect_symbols_group/${encoded}?token=${token}`)
            .then(res => res.json())
            .then(data => {
                if (data['error'] === 'no_symbols') {
                    SetMessage('No symbols to detect')
                    SetMsgColor('red')
                    return
                }
                if (data['error'] === 'no_matches') {
                    SetMessage('No symbols matched any securities group')
                    SetMsgColor('red')
                    return
                }
                if (data['error']) {
                    SetMessage('Error detecting group: ' + data['error'])
                    SetMsgColor('red')
                    return
                }
                SetCsvDetection(data)
                SetCsvStep(1)
                SetMessage('')
            })
            .catch(err => { SetMessage('Error detecting group'); SetMsgColor('red'); console.log('detect error:', err.message) })
    }

    const handleCsvImport = () => {
        if (!csvDetection) return
        let name = csvWatchlistName.trim()
        if (name.length === 0) {
            SetMessage('Enter a watchlist name')
            SetMsgColor('red')
            return
        }

        // check duplicate name
        if (props.watchlists.some(w => w.name === name)) {
            SetMessage(`"${name}" already exists`)
            SetMsgColor('red')
            return
        }

        // check max watchlists
        if (props.watchlists.length >= props.numWatchlistsAllowed) {
            SetMessage('Maximum # of Watchlists for your level is reached')
            SetMsgColor('red')
            return
        }

        SetCsvImporting(true)
        SetMessage('Creating watchlist...')
        SetMsgColor(tc.text)

        let det = csvDetection['detected_group']
        let resourceId = det['resource_id']
        let resourceName = det['resource_name']
        let validSymbols = csvDetection['valid_symbols']
        let asURL = appserverURL()

        // step 1: create watchlist with detected resource group
        fetch(`${asURL}/add_user_watchlist_name/${name}/${resourceId}/${resourceName}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                if (data['watchlist_names_list'] === 'limit_reached') {
                    SetMessage('Maximum # of Watchlists for your level is reached')
                    SetMsgColor('red')
                    SetCsvImporting(false)
                    return
                }
                if (data['watchlist_names_list'] === 'duplicate') {
                    SetMessage(`"${name}" already exists`)
                    SetMsgColor('red')
                    SetCsvImporting(false)
                    return
                }

                props.SetWatchlists(data['watchlist_names_list'])

                if (data['new_watchlist'] && data['new_watchlist'].isDefault) {
                    props.SetDefaultWatchlistName(data['new_watchlist'].name)
                    props.SetDefaultWatchlistItems([])
                }

                // step 2: bulk add symbols
                let encoded = window.btoa(validSymbols.join(','))
                fetch(`${asURL}/bulk_add_watchlist_items/${name}/${encoded}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
                    .then(res => res.json())
                    .then(bulkData => {
                        SetCsvResult(bulkData)
                        SetCsvStep(2)
                        SetCsvImporting(false)
                        SetMessage('')

                        // update selected watchlist to the new one
                        SetSelWatchlist(name)
                        SetWatchlistItems(bulkData['watchlist_items'] || [])

                        if (data['new_watchlist'] && data['new_watchlist'].isDefault) {
                            props.SetDefaultWatchlistItems(bulkData['watchlist_items'] || [])
                        }
                    })
                    .catch(err => { SetMessage('Error adding symbols'); SetMsgColor('red'); SetCsvImporting(false); console.log('bulk add error:', err.message) })
            })
            .catch(err => { SetMessage('Error creating watchlist'); SetMsgColor('red'); SetCsvImporting(false); console.log('csv import error:', err.message) })
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    const handleDeleteSymbol = (sym) => {
        let asURL = appserverURL()
        fetch(`${asURL}/del_user_watchlist_item/${selWatchlist}/${sym}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                SetWatchlistItems(data['watchlist_items'])
                SetMessage(`${sym} removed`)
                SetMsgColor('green')

                if (selWatchlist === props.defaultWatchlistName) {
                    props.SetDefaultWatchlistItems(data['watchlist_items'])
                }
            })
            .catch(err => console.log('del watchlist item error:', err.message))
    }

    //-------------------------------------------------------------------------------------------------------------------------------------
    return (
        <div ref={dialogRef} style={popupDialogStyle}>

            <div style={{ width: '100%', height: '8%', backgroundColor: tc.titleBar, display: 'flex', flexShrink: 0 }}>
                <div style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: 'transparent' }}></div>
                <div className='div_basic' style={{ height: '100%', width: titleCenterDivWidth, backgroundColor: 'transparent', cursor: rdd.isMobile ? 'default' : 'move' }} onMouseDown={handleTitleMouseDown}><span style={{ fontSize: title_text_size, color: tc.textOnControl }}>Watchlist Settings</span></div>
                <div className='div_basic' onClick={() => { props.SetShowWatchlistSettings(false) }} style={{ height: '100%', width: titleCloseDivWidth, backgroundColor: tc.closeBtnBg, cursor: 'pointer' }}><GrClose size={grclose_iconsize} /></div>
            </div>

            <div style={{ width: '100%', flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '8px 0', colorScheme: props.UITheme === 'dark' ? 'dark' : 'light' }}>

                {/* Watchlist count */}
                <div className='div_basic' style={{ width: '80%', backgroundColor: tc.statLabelBg, height: '2.2em', borderBottom: '4px solid ' + tc.border, paddingTop: '4px', fontSize: globalTextSize, marginBottom: '8px', flexShrink: 0 }}>
                    Watchlists: {props.watchlists.length} / {props.numWatchlistsAllowed}
                </div>

                {/* Resource group selector for new watchlist */}
                <div className='div_basic' style={{ width: '80%', height: 'auto', backgroundColor: 'transparent', marginBottom: '6px', flexShrink: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', marginRight: '5px', backgroundColor: 'transparent', width: '35%' }}>
                        <span style={{ fontSize: globalTextSize, color: tc.text }}>Securities Group:</span>
                    </div>
                    <div style={{ backgroundColor: 'transparent', width: '65%' }}>
                        <SelectBox optionList={watchlistResourceList} name="wl_resource_group" value={selResourceGroup} sbChanged={resourceGroupChanged} />
                    </div>
                </div>

                {/* Add watchlist row */}
                <div className='div_basic' style={{ width: '80%', height: 'auto', backgroundColor: 'transparent', marginBottom: '6px', flexShrink: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', marginRight: '5px', backgroundColor: 'transparent', width: '50%' }}>
                        <button onClick={handleAddNew} style={{ width: '97%', height: button_height }}><BsPlus size={icon_sizeP} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Add Watchlist</button>
                    </div>
                    <div style={{ backgroundColor: 'transparent', width: '50%' }}>
                        <TextBox name='wl_new_name' text={newText} tbBlur={handleBlur} width={textboxWidth} tbEnter={handleEnter} tooltipContent={props.tooltipSW ? 'b,Enter Watchlist Name' : ''} />
                    </div>
                </div>

                {/* Import CSV button */}
                <div className='div_basic' style={{ width: '80%', height: 'auto', backgroundColor: 'transparent', marginBottom: '6px', flexShrink: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', marginRight: '5px', backgroundColor: 'transparent', width: '50%' }}>
                        <button onClick={() => { SetCsvMode(!csvMode); if (csvMode) resetCsvImport() }} style={{ width: '97%', height: button_height }}>
                            <BsUpload size={icon_sizeE} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;{csvMode ? 'Cancel Import' : 'Import CSV'}
                        </button>
                    </div>
                    <div style={{ backgroundColor: 'transparent', width: '50%' }}></div>
                </div>

                {/* CSV Import Panel */}
                {csvMode && (
                    <div style={{ width: '80%', border: '1px solid ' + tc.border, padding: '8px', marginBottom: '6px', flexShrink: 0, backgroundColor: tc.panelBg }}>

                        {/* Step 0: Select file */}
                        {csvStep === 0 && (
                            <div style={{ fontSize: globalTextSize, color: tc.text }}>
                                <div style={{ marginBottom: '6px' }}>Select a CSV file with a Symbol column:</div>
                                <input type="file" accept=".csv,.txt" onChange={handleCsvFileSelect}
                                    style={{ fontSize: globalTextSize, color: tc.text, width: '100%' }} />
                            </div>
                        )}

                        {/* Step 1: Preview */}
                        {csvStep === 1 && csvDetection && (
                            <div style={{ fontSize: globalTextSize, color: tc.text }}>
                                <div style={{ marginBottom: '4px' }}>
                                    Detected: <span style={{ color: 'green', fontWeight: 'bold' }}>{csvDetection['detected_group']['resource_name']}</span>
                                </div>
                                <div style={{ marginBottom: '4px' }}>
                                    Valid: <span style={{ color: 'green' }}>{csvDetection['valid_symbols'].length}</span>
                                    {csvDetection['invalid_symbols'].length > 0 && (
                                        <span> &nbsp;|&nbsp; Invalid: <span style={{ color: 'red' }}>{csvDetection['invalid_symbols'].length}</span></span>
                                    )}
                                </div>
                                {csvDetection['invalid_symbols'].length > 0 && (
                                    <div style={{ marginBottom: '4px', color: tc.textSecondary, fontSize: '0.85em', maxHeight: '40px', overflowY: 'auto' }}>
                                        Not matched: {csvDetection['invalid_symbols'].slice(0, 20).join(', ')}{csvDetection['invalid_symbols'].length > 20 ? '...' : ''}
                                    </div>
                                )}
                                {csvDetection['all_groups'].length > 1 && (
                                    <div style={{ marginBottom: '4px', color: tc.textSecondary, fontSize: '0.85em' }}>
                                        Other matches: {csvDetection['all_groups'].slice(1).map(g => `${g['resource_name']} (${g['match_count']})`).join(', ')}
                                    </div>
                                )}
                                {csvDetection['valid_symbols'].length > props.numWatchlistItemsAllowed && (
                                    <div style={{ marginBottom: '4px', color: 'orange' }}>
                                        Note: Your tier allows {props.numWatchlistItemsAllowed} symbols. {csvDetection['valid_symbols'].length - props.numWatchlistItemsAllowed} will be skipped.
                                    </div>
                                )}
                                <div style={{ display: 'flex', alignItems: 'center', marginTop: '6px', marginBottom: '6px' }}>
                                    <span style={{ marginRight: '5px' }}>Name:</span>
                                    <input type="text" value={csvWatchlistName} onChange={(e) => SetCsvWatchlistName(e.target.value)}
                                        style={{ flex: 1, padding: '3px 5px', fontSize: globalTextSize }} />
                                </div>
                                <div style={{ display: 'flex', gap: '5px' }}>
                                    <button onClick={handleCsvImport} disabled={csvImporting} style={{ height: button_height, flex: 1 }}>
                                        {csvImporting ? 'Creating...' : 'Create Watchlist'}
                                    </button>
                                    <button onClick={resetCsvImport} style={{ height: button_height, flex: 1 }}>Cancel</button>
                                </div>
                            </div>
                        )}

                        {/* Step 2: Done */}
                        {csvStep === 2 && csvResult && (
                            <div style={{ fontSize: globalTextSize, color: tc.text }}>
                                <div style={{ color: 'green', marginBottom: '4px' }}>
                                    Created "{csvResult['watchlist_name']}" with {csvResult['added_count']} symbols
                                </div>
                                {csvResult['skipped_duplicate'] > 0 && (
                                    <div style={{ marginBottom: '4px', color: tc.textSecondary }}>{csvResult['skipped_duplicate']} duplicates skipped</div>
                                )}
                                {csvResult['skipped_limit'] > 0 && (
                                    <div style={{ marginBottom: '4px', color: 'orange' }}>{csvResult['skipped_limit']} symbols skipped (tier limit)</div>
                                )}
                                <button onClick={resetCsvImport} style={{ height: button_height, marginTop: '4px' }}>Done</button>
                            </div>
                        )}
                    </div>
                )}

                {/* Edit/Delete + SelectBox row */}
                <div style={{ width: '80%', backgroundColor: 'transparent', marginBottom: '6px', flexShrink: 0 }}>
                    <div className='div_basic' style={{ width: '100%', height: 'auto', backgroundColor: 'transparent' }}>
                        <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', height: '100%', width: '50%', backgroundColor: 'transparent', flexDirection: 'row' }}>
                            <button onClick={handleEdit} style={{ width: '45%', marginRight: '5px', height: button_height }}><GrEdit size={icon_sizeE} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Edit</button>
                            <button onClick={handleDelete} style={{ width: '50%', height: button_height }}><BsTrash3 size={icon_sizeD} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Delete</button>
                        </div>
                        <div style={{ paddingLeft: '5px', display: 'flex', justifyContent: 'left', alignItems: 'center', height: '100%', width: '50%', backgroundColor: 'transparent' }}>
                            <SelectBox optionList={watchlistOptions} name="watchlists" value={selWatchlist} sbChanged={watchlistChanged} />
                        </div>
                    </div>
                </div>

                {/* Default checkbox */}
                <div style={{ width: '80%', display: 'flex', alignItems: 'center', marginBottom: '8px', fontSize: globalTextSize, flexShrink: 0 }}>
                    <CheckBox name="wl_default" cbChanged={handleSetDefault} checked={isDefault()} />
                    <span style={{ marginLeft: '6px', color: tc.text }}>Default Watchlist</span>
                </div>

                {/* Add to Securities List checkbox */}
                <div style={{ width: '80%', display: 'flex', alignItems: 'center', marginBottom: '8px', fontSize: globalTextSize, flexShrink: 0 }}>
                    <CheckBox name="wl_add_to_securities" cbChanged={handleSetAddToSecurities} checked={isAddToSecurities()} />
                    <span style={{ marginLeft: '6px', color: tc.text }}>Add to Securities List</span>
                </div>

                {/* Message */}
                <div style={{ width: '80%', textAlign: 'center', marginBottom: '8px', flexShrink: 0 }}>
                    <span style={{ color: msgColor, fontSize: globalTextSize }}>{message}</span>
                </div>

                {/* Symbols section */}
                {selWatchlist !== '' && (
                    <>
                        <div style={{ width: '80%', borderTop: '1px solid ' + tc.border, paddingTop: '8px', marginBottom: '6px', flexShrink: 0 }}>
                            <div className='div_basic' style={{ backgroundColor: tc.statLabelBg, height: '2.2em', width: '100%', borderBottom: '4px solid ' + tc.border, paddingTop: '4px', fontSize: globalTextSize }}>
                                Symbols in {selWatchlist}: {watchlistItems.length} / {props.numWatchlistItemsAllowed}
                            </div>
                        </div>

                        {/* Add symbol row */}
                        <div className='div_basic' style={{ width: '80%', height: 'auto', backgroundColor: 'transparent', marginBottom: '6px', flexShrink: 0 }}>
                            <div style={{ display: 'flex', justifyContent: 'right', paddingRight: '5px', alignItems: 'center', marginRight: '5px', backgroundColor: 'transparent', width: '50%' }}>
                                <button onClick={handleAddSymbol} style={{ width: '97%', height: button_height }}><BsPlus size={icon_sizeP} style={{ fill: "black", verticalAlign: "middle" }} />&nbsp;Add Symbol</button>
                            </div>
                            <div style={{ backgroundColor: 'transparent', width: '50%' }}>
                                <TextBox name='wl_new_symbol' text={newSymbol} tbBlur={handleSymbolBlur} width={textboxWidth} tbEnter={handleSymbolEnter} tooltipContent={props.tooltipSW ? 'b,Enter Ticker Symbol' : ''} />
                            </div>
                        </div>

                        {/* Symbol list */}
                        <div style={{ width: '80%', maxHeight: '150px', overflowY: 'auto', border: '1px solid ' + tc.border, flexShrink: 0, colorScheme: props.UITheme === 'dark' ? 'dark' : 'light' }}>
                            {watchlistItems.map((sym, idx) => (
                                <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 8px', fontSize: globalTextSize, color: tc.text, borderBottom: idx < watchlistItems.length - 1 ? '1px solid ' + tc.border : 'none' }}>
                                    <span>{sym}</span>
                                    <BsTrash3 size={11} style={{ cursor: 'pointer', fill: tc.text, opacity: 0.6 }} onClick={() => handleDeleteSymbol(sym)} />
                                </div>
                            ))}
                            {watchlistItems.length === 0 && (
                                <div style={{ padding: '8px', fontSize: globalTextSize, color: tc.textSecondary, textAlign: 'center' }}>No symbols added yet</div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    )
}
export default WatchlistSettings
