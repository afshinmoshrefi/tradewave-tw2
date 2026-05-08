import React, { useContext, useEffect, useState, useRef } from 'react'
import { UserContext } from './UserContext'
import { appserverURL, themeColors } from './Common'
import './styles/InfoPopup.css'
import { GrClose } from "react-icons/gr"
import { BsPlus, BsTrash3 } from "react-icons/bs"
import { GrEdit } from "react-icons/gr"
import CheckBox from './CheckBox'


const SecuritiesGroupSettings = (props) => {

    const tc = themeColors(props.UITheme)
    const { browserH, browserW, rdd, globalTextSize, token, loggedinUser } = useContext(UserContext)
    const dialogRef = useRef(null)

    const [message, SetMessage] = useState('')
    const [msgColor, SetMsgColor] = useState('red')
    const [activeTab, SetActiveTab] = useState('groups') // 'groups' or 'admin'

    // Admin: create new published list
    const [newListName, SetNewListName] = useState('')
    const [newListResourceId, SetNewListResourceId] = useState('')
    const [newListSymbols, SetNewListSymbols] = useState('')
    const [editingList, SetEditingList] = useState(null) // name of list being edited
    const [editSymbols, SetEditSymbols] = useState('')

    // Close on click outside
    useEffect(() => {
        const onMouseDown = (e) => {
            if (dialogRef.current && !dialogRef.current.contains(e.target)) {
                props.SetShowSecuritiesGroupSettings(false)
            }
        }
        document.addEventListener('mousedown', onMouseDown)
        return () => document.removeEventListener('mousedown', onMouseDown)
    }, [])

    // Drag support
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

    var DialogH = '60%';
    var DialogW = '35%';
    var DialogT = '20%';
    var DialogL = '32%';
    var grclose_iconsize = 17;
    var title_text_size = '1vw';
    var headingSize = '0.8vw';
    var labelSize = '0.75vw';
    var bannerHeight = '10%';
    var titleCloseDivWidth = '6%';
    var titleCenterDivWidth = '88%';

    if (rdd.isMobile && !rdd.isTablet && browserH > browserW) {
        DialogH = '70%'; DialogW = '100%'; DialogT = '10%'; DialogL = '0';
        title_text_size = '4.5vw'; headingSize = '3.5vw'; labelSize = '3vw'; bannerHeight = '7%';
        titleCloseDivWidth = '10%'; titleCenterDivWidth = '80%';
    } else if (rdd.isMobile && !rdd.isTablet && browserH < browserW) {
        DialogH = '70%'; DialogW = '60%'; DialogT = '15%'; DialogL = '20%';
        title_text_size = '2vw'; headingSize = '1.5vw'; labelSize = '1.2vw';
    } else if (rdd.isMobile && rdd.isTablet) {
        DialogH = '60%'; DialogW = '50%'; DialogT = '20%'; DialogL = '25%';
        title_text_size = '1.8vw'; headingSize = '1.4vw'; labelSize = '1.1vw';
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

    // Get the full securities list (unfiltered) from securityTypeList in props
    // This is the original list before filtering by prefs
    const allGroups = (props.securityTypeList2 || []).filter(x => x.value !== '' && x.label !== 'More...')

    const isGroupHidden = (groupValue) => {
        return (props.securitiesPrefs.hidden_groups || []).includes(groupValue)
    }

    const isPublishedEnabled = (plName) => {
        return (props.securitiesPrefs.enabled_published || []).includes(plName)
    }

    const savePrefs = (newPrefs) => {
        let asURL = appserverURL()
        fetch(`${asURL}/set_securities_prefs?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newPrefs)
        })
            .then(res => res.json())
            .then(data => {
                if (data['securities_prefs']) {
                    props.SetSecuritiesPrefs(data['securities_prefs'])
                }
            })
            .catch(err => console.log('save securities prefs error:', err.message))
    }

    const toggleGroup = (groupValue) => {
        let hidden = [...(props.securitiesPrefs.hidden_groups || [])]
        if (hidden.includes(groupValue)) {
            hidden = hidden.filter(v => v !== groupValue)
        } else {
            hidden.push(groupValue)
        }
        const newPrefs = { ...props.securitiesPrefs, hidden_groups: hidden }
        props.SetSecuritiesPrefs(newPrefs)
        savePrefs(newPrefs)
    }

    const togglePublished = (plName) => {
        let enabled = [...(props.securitiesPrefs.enabled_published || [])]
        if (enabled.includes(plName)) {
            enabled = enabled.filter(v => v !== plName)
        } else {
            enabled.push(plName)
        }
        const newPrefs = { ...props.securitiesPrefs, enabled_published: enabled }
        props.SetSecuritiesPrefs(newPrefs)
        savePrefs(newPrefs)
    }

    const resetToDefault = () => {
        const newPrefs = { hidden_groups: [], enabled_published: [] }
        props.SetSecuritiesPrefs(newPrefs)
        savePrefs(newPrefs)
        SetMessage('Reset to default - all groups visible')
        SetMsgColor('green')
    }

    // ---- Admin functions ----
    const resourceOptions = Object.entries(props.resourceObj || {}).map(([id, name]) => ({
        id: parseInt(id), value: id, label: name
    }))

    const handleCreatePublishedList = () => {
        if (!newListName.trim()) { SetMessage('Enter a list name'); SetMsgColor('red'); return }
        if (!newListResourceId) { SetMessage('Select a securities group'); SetMsgColor('red'); return }
        if (!newListSymbols.trim()) { SetMessage('Enter symbols separated by commas'); SetMsgColor('red'); return }

        let symbols = newListSymbols.split(',').map(s => s.trim().toUpperCase()).filter(s => s)

        let asURL = appserverURL()
        fetch(`${asURL}/create_published_list?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: newListName.trim(),
                resource_id: newListResourceId,
                symbols: symbols
            })
        })
            .then(res => res.json())
            .then(data => {
                if (data['error'] === 'duplicate_name') {
                    SetMessage('A list with this name already exists')
                    SetMsgColor('red')
                } else if (data['published_lists']) {
                    props.SetPublishedLists(data['published_lists'])
                    SetNewListName('')
                    SetNewListSymbols('')
                    SetNewListResourceId('')
                    SetMessage('Published list created')
                    SetMsgColor('green')
                }
            })
            .catch(err => { SetMessage('Error creating list'); SetMsgColor('red') })
    }

    const handleDeletePublishedList = (name) => {
        let asURL = appserverURL()
        fetch(`${asURL}/delete_published_list/${encodeURIComponent(name)}?token=${token}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
            .then(res => res.json())
            .then(data => {
                if (data['published_lists']) {
                    props.SetPublishedLists(data['published_lists'])
                    SetMessage(`Deleted: ${name}`)
                    SetMsgColor('green')
                }
            })
            .catch(err => { SetMessage('Error deleting list'); SetMsgColor('red') })
    }

    const handleStartEdit = (pl) => {
        SetEditingList(pl.name)
        SetEditSymbols(pl.symbols.join(', '))
    }

    const handleSaveEdit = (name) => {
        let symbols = editSymbols.split(',').map(s => s.trim().toUpperCase()).filter(s => s)
        let asURL = appserverURL()
        fetch(`${asURL}/update_published_list?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, updates: { symbols: symbols } })
        })
            .then(res => res.json())
            .then(data => {
                if (data['published_lists']) {
                    props.SetPublishedLists(data['published_lists'])
                    SetEditingList(null)
                    SetMessage('List updated')
                    SetMsgColor('green')
                }
            })
            .catch(err => { SetMessage('Error updating list'); SetMsgColor('red') })
    }

    const handleToggleEnabled = (pl) => {
        let asURL = appserverURL()
        fetch(`${asURL}/update_published_list?token=${token}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: pl.name, updates: { enabled: !pl.enabled } })
        })
            .then(res => res.json())
            .then(data => {
                if (data['published_lists']) {
                    props.SetPublishedLists(data['published_lists'])
                }
            })
            .catch(err => console.log('toggle enabled error:', err.message))
    }

    const rowStyle = {
        display: 'flex', alignItems: 'center', padding: '3px 8px',
        borderBottom: '1px solid ' + (tc.border || '#444'), width: '100%'
    }

    const tabStyle = (isActive) => ({
        width: props.isAdmin ? '33%' : '50%',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        backgroundColor: isActive ? tc.panelBg : (tc.titleBar || '#444'),
        borderBottom: isActive ? 'none' : '1px solid ' + (tc.border || '#444'),
        borderRight: '1px solid ' + (tc.border || '#444')
    })

    return (
        <div style={{ position: 'absolute', width: '100%', height: '100%', left: 0, top: 0, zIndex: 7000, backgroundColor: 'rgba(0,0,0,0)' }}>
            <div ref={dialogRef} style={popupDialogStyle} onClick={(e) => e.stopPropagation()}>

                {/* Title bar */}
                <div style={{ width: '100%', height: bannerHeight, backgroundColor: tc.titleBar || 'gray', display: 'flex', cursor: 'move' }}
                    onMouseDown={handleTitleMouseDown}>
                    <div style={{ height: '100%', width: titleCloseDivWidth }}></div>
                    <div style={{ height: '100%', width: titleCenterDivWidth, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <span style={{ fontSize: title_text_size, color: tc.titleText || 'whitesmoke' }}>Securities Groups</span>
                    </div>
                    <div style={{ height: '100%', width: titleCloseDivWidth, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', backgroundColor: tc.closeBtn || 'lightgray' }}
                        onClick={() => props.SetShowSecuritiesGroupSettings(false)}>
                        <GrClose size={grclose_iconsize} />
                    </div>
                </div>

                {/* Tabs */}
                <div style={{ width: '100%', height: '6%', display: 'flex', fontSize: headingSize }}>
                    <div style={tabStyle(activeTab === 'groups')} onClick={() => SetActiveTab('groups')}>
                        <span style={{ color: tc.text }}>My Groups</span>
                    </div>
                    <div style={tabStyle(activeTab === 'published')} onClick={() => SetActiveTab('published')}>
                        <span style={{ color: tc.text }}>Published Lists</span>
                    </div>
                    {props.isAdmin &&
                        <div style={tabStyle(activeTab === 'admin')} onClick={() => SetActiveTab('admin')}>
                            <span style={{ color: tc.text }}>Admin</span>
                        </div>
                    }
                </div>

                {/* Message */}
                {message && <div style={{ width: '100%', padding: '4px 8px', fontSize: labelSize, color: msgColor, textAlign: 'center' }}>{message}</div>}

                {/* Content area */}
                <div style={{ width: '100%', flex: 1, overflowY: 'auto', padding: '4px 0' }}>

                    {/* ==== MY GROUPS TAB ==== */}
                    {activeTab === 'groups' && <>
                        <div style={{ padding: '4px 8px', fontSize: labelSize, color: tc.text || '#aaa', textAlign: 'center' }}>
                            Uncheck groups to hide them from the securities dropdown
                        </div>
                        {allGroups.map((g, i) => (
                            <div key={i} style={rowStyle}>
                                <CheckBox
                                    name={`grp_${g.value}`}
                                    checked={!isGroupHidden(g.label)}
                                    cbChanged={() => toggleGroup(g.label)}
                                />
                                <span style={{ marginLeft: '8px', fontSize: labelSize, color: tc.text }}>{g.label}</span>
                                {g.type === 'P' && <span style={{ marginLeft: '6px', fontSize: '0.6vw', color: 'gold' }}>★</span>}
                            </div>
                        ))}
                        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px' }}>
                            <button onClick={resetToDefault}
                                style={{ padding: '4px 16px', fontSize: labelSize, cursor: 'pointer' }}>
                                Reset to Default
                            </button>
                        </div>
                    </>}

                    {/* ==== PUBLISHED LISTS TAB ==== */}
                    {activeTab === 'published' && <>
                        <div style={{ padding: '4px 8px', fontSize: labelSize, color: tc.text || '#aaa', textAlign: 'center' }}>
                            Check published lists to add them to your securities dropdown
                        </div>
                        {props.publishedLists.length === 0 &&
                            <div style={{ padding: '20px', textAlign: 'center', fontSize: labelSize, color: tc.text || '#888' }}>
                                No published lists available
                            </div>
                        }
                        {props.publishedLists.map((pl, i) => (
                            <div key={i} style={rowStyle}>
                                <CheckBox
                                    name={`pl_${pl.name}`}
                                    checked={isPublishedEnabled(pl.name)}
                                    cbChanged={() => togglePublished(pl.name)}
                                />
                                <span style={{ marginLeft: '8px', fontSize: labelSize, color: tc.text }}>{pl.name}</span>
                                <span style={{ marginLeft: '8px', fontSize: '0.6vw', color: tc.text || '#888' }}>
                                    ({pl.resource_name} · {pl.symbols ? pl.symbols.length : 0} symbols)
                                </span>
                            </div>
                        ))}
                    </>}

                    {/* ==== ADMIN TAB ==== */}
                    {activeTab === 'admin' && props.isAdmin && <>
                        <div style={{ padding: '8px', fontSize: labelSize, color: tc.text || '#aaa', textAlign: 'center' }}>
                            Create and manage published securities lists
                        </div>

                        {/* Create new list */}
                        <div style={{ padding: '8px', borderBottom: '2px solid ' + (tc.border || '#444') }}>
                            <div style={{ fontSize: headingSize, color: tc.text, marginBottom: '6px' }}>Create New List</div>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '4px', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: labelSize, color: tc.text, minWidth: '40px' }}>Name:</span>
                                <input type="text" value={newListName} onChange={(e) => SetNewListName(e.target.value)}
                                    placeholder="e.g. Optionable Stocks"
                                    style={{ flex: 1, minWidth: '120px', padding: '2px 4px', fontSize: labelSize }} />
                            </div>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '4px', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: labelSize, color: tc.text, minWidth: '40px' }}>Group:</span>
                                <select value={newListResourceId} onChange={(e) => SetNewListResourceId(e.target.value)}
                                    style={{ flex: 1, minWidth: '120px', padding: '2px 4px', fontSize: labelSize }}>
                                    <option value="">Select resource group</option>
                                    {resourceOptions.map(r => <option key={r.id} value={r.value}>{r.label}</option>)}
                                </select>
                            </div>
                            <div style={{ display: 'flex', gap: '6px', alignItems: 'flex-start', marginBottom: '4px', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: labelSize, color: tc.text, minWidth: '40px', paddingTop: '4px' }}>Symbols:</span>
                                <textarea value={newListSymbols} onChange={(e) => SetNewListSymbols(e.target.value)}
                                    placeholder="AAPL, MSFT, NVDA, ..."
                                    rows={3}
                                    style={{ flex: 1, minWidth: '120px', padding: '2px 4px', fontSize: labelSize, resize: 'vertical' }} />
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                <button onClick={handleCreatePublishedList}
                                    style={{ padding: '4px 16px', fontSize: labelSize, cursor: 'pointer' }}>
                                    <BsPlus size={14} style={{ verticalAlign: 'middle' }} /> Create
                                </button>
                            </div>
                        </div>

                        {/* Existing published lists */}
                        <div style={{ padding: '8px' }}>
                            <div style={{ fontSize: headingSize, color: tc.text, marginBottom: '6px' }}>Existing Published Lists</div>
                            {props.publishedLists.length === 0 &&
                                <div style={{ fontSize: labelSize, color: tc.text || '#888', textAlign: 'center', padding: '10px' }}>No published lists</div>
                            }
                            {props.publishedLists.map((pl, i) => (
                                <div key={i} style={{ ...rowStyle, flexDirection: 'column', alignItems: 'flex-start' }}>
                                    <div style={{ display: 'flex', width: '100%', alignItems: 'center' }}>
                                        <CheckBox name={`en_${pl.name}`} checked={pl.enabled} cbChanged={() => handleToggleEnabled(pl)} />
                                        <span style={{ marginLeft: '6px', fontSize: labelSize, color: tc.text, flex: 1 }}>
                                            {pl.name} <span style={{ color: tc.text || '#888', fontSize: '0.6vw' }}>({pl.resource_name} · {pl.symbols.length} symbols)</span>
                                        </span>
                                        <GrEdit size={12} style={{ cursor: 'pointer', marginRight: '8px' }}
                                            onClick={() => editingList === pl.name ? SetEditingList(null) : handleStartEdit(pl)} />
                                        <BsTrash3 size={12} style={{ cursor: 'pointer', fill: 'red' }}
                                            onClick={() => handleDeletePublishedList(pl.name)} />
                                    </div>
                                    {editingList === pl.name && (
                                        <div style={{ width: '100%', marginTop: '4px' }}>
                                            <textarea value={editSymbols} onChange={(e) => SetEditSymbols(e.target.value)}
                                                rows={3}
                                                style={{ width: '100%', padding: '2px 4px', fontSize: labelSize, resize: 'vertical' }} />
                                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '6px', marginTop: '2px' }}>
                                                <button onClick={() => SetEditingList(null)} style={{ fontSize: labelSize, cursor: 'pointer', padding: '2px 10px' }}>Cancel</button>
                                                <button onClick={() => handleSaveEdit(pl.name)} style={{ fontSize: labelSize, cursor: 'pointer', padding: '2px 10px' }}>Save</button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </>}

                </div>

            </div>
        </div>
    )
}
export default SecuritiesGroupSettings
