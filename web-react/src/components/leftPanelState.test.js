import {
  CHATBOT_OPEN_KEY,
  LEFT_PANEL_COLLAPSED_KEY,
  parseChatbotOpen,
  parseLeftPanelCollapsed,
  resolveChatbotOpen,
  resolveLeftPanelCollapsed,
} from './leftPanelState'

describe('Wave Viewer left panel state', () => {
  test('uses a stable saved-setting key', () => {
    expect(LEFT_PANEL_COLLAPSED_KEY).toBe('leftPanelCollapsed')
  })

  test.each([true, 'true', 1, '1'])(
    'recognizes %p as a collapsed preference',
    (value) => expect(parseLeftPanelCollapsed(value)).toBe(true),
  )

  test.each([false, 'false', 0, '0', null, undefined])(
    'recognizes %p as an open preference',
    (value) => expect(parseLeftPanelCollapsed(value)).toBe(false),
  )

  test('defaults to open and never collapses the mobile layout', () => {
    expect(resolveLeftPanelCollapsed({ storedPreference: null })).toBe(false)
    expect(resolveLeftPanelCollapsed({ storedPreference: true, isMobile: true })).toBe(false)
  })

  test('uses a stable saved-setting key for Tara', () => {
    expect(CHATBOT_OPEN_KEY).toBe('chatbotOpen')
  })

  test.each([true, 'true', 1, '1'])(
    'recognizes %p as an open Tara preference',
    (value) => expect(parseChatbotOpen(value)).toBe(true),
  )

  test.each([false, 'false', 0, '0'])(
    'recognizes %p as a closed Tara preference',
    (value) => expect(parseChatbotOpen(value)).toBe(false),
  )

  test('opens Tara by default and restores an explicit closed preference', () => {
    expect(resolveChatbotOpen(null)).toBe(true)
    expect(resolveChatbotOpen(undefined)).toBe(true)
    expect(resolveChatbotOpen(false)).toBe(false)
  })
})
