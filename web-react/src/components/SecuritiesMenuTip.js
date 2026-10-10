import React, { useEffect, useRef, useState } from 'react'
import ReactDOM from 'react-dom'
import { themeColors } from './Common'

export default function SecuritiesMenuTip({ anchor, UITheme, onAcknowledge, onDismiss }) {
    const tc = themeColors(UITheme)
    const dialog = useRef(null)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState('')
    useEffect(() => { dialog.current?.querySelector('button')?.focus() }, [])
    const width = Math.min(360, window.innerWidth - 24)
    const left = Math.max(12, Math.min(anchor.left, window.innerWidth - width - 12))
    const top = Math.max(12, Math.min(anchor.bottom + 8, window.innerHeight - 260))
    const acknowledge = async (customize) => {
        setSaving(true)
        setError('')
        try { await onAcknowledge(customize) }
        catch { setError('Could not save your preference. Please try again.'); setSaving(false) }
    }
    const onKeyDown = (event) => {
        if (event.key === 'Escape' && !saving) { event.preventDefault(); onDismiss() }
        if (event.key === 'Tab') {
            const buttons = [...dialog.current.querySelectorAll('button:not(:disabled)')]
            const first = buttons[0], last = buttons[buttons.length - 1]
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
        }
    }
    const buttonStyle = { padding: '8px 12px', borderRadius: '5px', border: '1px solid '+tc.border, cursor: 'pointer', fontSize: '13px' }
    return ReactDOM.createPortal(
        <div style={{position:'fixed',inset:0,zIndex:12000}} onClick={() => { if (!saving) onDismiss() }}>
            <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="securities-menu-tip-title"
                onClick={event => event.stopPropagation()} onKeyDown={onKeyDown}
                style={{position:'fixed',left,top,width,boxSizing:'border-box',padding:'18px',border:'1px solid '+tc.border,borderRadius:'8px',background:tc.panelBg,color:tc.text,boxShadow:'0 8px 28px rgba(0,0,0,0.35)',fontFamily:'sans-serif',fontSize:'14px',lineHeight:1.5,maxHeight:'calc(100dvh - 24px)',overflowY:'auto'}}>
                <h2 id="securities-menu-tip-title" style={{fontSize:'16px',margin:'0 0 10px'}}>Customize Your Securities Menu</h2>
                <p style={{margin:'0 0 16px'}}>Choose which securities lists appear here. Hide markets you don’t use, such as bonds or crypto, and show or hide lists published by TradeWave.</p>
                {error && <p role="alert" style={{color:tc.text}}>{error}</p>}
                <div style={{display:'flex',gap:'8px',flexWrap:'wrap'}}>
                    <button style={{...buttonStyle,background:'#7657df',color:'white'}} disabled={saving} onClick={() => acknowledge(true)}>Customize Lists</button>
                    <button style={{...buttonStyle,background:tc.panelBg,color:tc.text}} disabled={saving} onClick={() => acknowledge(false)}>Got It</button>
                </div>
            </div>
        </div>, document.body)
}
