import React from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import SecuritiesMenuTip from './SecuritiesMenuTip'
import SelectBox from './SelectBox'
import { UserContext } from './UserContext'

const props = {anchor:{left:1400,bottom:900},UITheme:'dark',onAcknowledge:jest.fn(() => Promise.resolve()),onDismiss:jest.fn()}
beforeEach(() => jest.clearAllMocks())
test.each([['Got It',false],['Customize Lists',true]])('%s acknowledges with the intended destination', async (label,customize) => {
    render(<SecuritiesMenuTip {...props} />)
    expect(screen.getByRole('dialog')).toHaveTextContent('bonds or crypto')
    expect(screen.getByRole('button',{name:'Customize Lists'})).toHaveFocus()
    fireEvent.click(screen.getByRole('button',{name:label}))
    await waitFor(() => expect(props.onAcknowledge).toHaveBeenCalledWith(customize))
})
test('failed persistence keeps the explanation visible and allows retry', async () => {
    const save=jest.fn().mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce()
    render(<SecuritiesMenuTip {...props} onAcknowledge={save} />)
    fireEvent.click(screen.getByRole('button',{name:'Got It'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Please try again')
    fireEvent.click(screen.getByRole('button',{name:'Got It'}))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2))
    expect(props.onDismiss).not.toHaveBeenCalled()
})
test('Escape dismisses without acknowledging and keyboard focus stays in dialog', () => {
    render(<SecuritiesMenuTip {...props} />)
    const first=screen.getByRole('button',{name:'Customize Lists'}), last=screen.getByRole('button',{name:'Got It'})
    fireEvent.keyDown(first,{key:'Tab',shiftKey:true})
    expect(last).toHaveFocus()
    fireEvent.keyDown(last,{key:'Tab'})
    expect(first).toHaveFocus()
    fireEvent.keyDown(first,{key:'Escape'})
    expect(props.onDismiss).toHaveBeenCalledTimes(1)
    expect(props.onAcknowledge).not.toHaveBeenCalled()
})
test('shared select intercepts only securities openings by pointer or keyboard', () => {
    const open=jest.fn(event => event.preventDefault()), changed=jest.fn()
    const context={rdd:{isMobile:false},UITheme:'dark',globalTextSize:'12px',onSecuritiesMenuOpen:open}
    const list=[{id:1,value:'US',label:'US'}]
    const {rerender}=render(<UserContext.Provider value={context}><SelectBox name="securityTypeList" optionList={list} value="US" sbChanged={changed} /></UserContext.Provider>)
    fireEvent.pointerDown(screen.getByRole('combobox'))
    fireEvent.keyDown(screen.getByRole('combobox'),{key:'ArrowDown'})
    expect(open).toHaveBeenCalledTimes(2)
    rerender(<UserContext.Provider value={context}><SelectBox name="years" optionList={list} value="US" sbChanged={changed} /></UserContext.Provider>)
    fireEvent.pointerDown(screen.getByRole('combobox'))
    fireEvent.keyDown(screen.getByRole('combobox'),{key:'ArrowDown'})
    expect(open).toHaveBeenCalledTimes(2)
})

test('opening touch click does not dismiss; a new outside pointer dismisses', () => {
    render(<SecuritiesMenuTip {...props} />)
    const dialog=screen.getByRole('dialog'), backdrop=dialog.parentElement
    fireEvent.click(backdrop)
    expect(props.onDismiss).not.toHaveBeenCalled()
    fireEvent.pointerDown(dialog)
    expect(props.onDismiss).not.toHaveBeenCalled()
    fireEvent.pointerDown(backdrop)
    expect(props.onDismiss).toHaveBeenCalledTimes(1)
    expect(props.onAcknowledge).not.toHaveBeenCalled()
})
