export const LEFT_PANEL_COLLAPSED_KEY = 'leftPanelCollapsed'
export const CHATBOT_OPEN_KEY = 'chatbotOpen'

export const parseLeftPanelCollapsed = (value) => (
  value === true || value === 'true' || value === 1 || value === '1'
)

export const resolveLeftPanelCollapsed = ({ storedPreference, isMobile = false }) => (
  !isMobile && parseLeftPanelCollapsed(storedPreference)
)

export const parseChatbotOpen = (value) => (
  value === true || value === 'true' || value === 1 || value === '1'
)

// Tara starts open for a user who has never made a choice. After that, the
// user's explicit open/closed preference is restored on every visit.
export const resolveChatbotOpen = (storedPreference) => (
  storedPreference == null ? true : parseChatbotOpen(storedPreference)
)
