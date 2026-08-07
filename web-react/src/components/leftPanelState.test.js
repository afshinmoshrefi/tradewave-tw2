import {
  LEFT_PANEL_COLLAPSED_KEY,
  parseLeftPanelCollapsed,
  resolveLeftPanelCollapsed,
} from './leftPanelState'

describe('leftPanelState', () => {
  test('uses the stable user-scoped preference key', () => {
    expect(LEFT_PANEL_COLLAPSED_KEY).toBe('leftPanelCollapsed')
  })

  test.each([true, 'true', 1, '1'])(
    'recognizes %p as a collapsed preference',
    value => expect(parseLeftPanelCollapsed(value)).toBe(true),
  )

  test.each([false, 'false', 0, '0', null, undefined, ''])(
    'recognizes %p as an expanded preference',
    value => expect(parseLeftPanelCollapsed(value)).toBe(false),
  )

  test('honors the saved preference on desktop', () => {
    expect(resolveLeftPanelCollapsed({ storedPreference: true, isMobile: false })).toBe(true)
    expect(resolveLeftPanelCollapsed({ storedPreference: false, isMobile: false })).toBe(false)
  })

  test('keeps the opportunity panel available on mobile', () => {
    expect(resolveLeftPanelCollapsed({ storedPreference: true, isMobile: true })).toBe(false)
  })
})
