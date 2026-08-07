export const LEFT_PANEL_COLLAPSED_KEY = 'leftPanelCollapsed'

export const parseLeftPanelCollapsed = (value) => (
  value === true || value === 'true' || value === 1 || value === '1'
)

export const resolveLeftPanelCollapsed = ({ storedPreference, isMobile = false }) => (
  !isMobile && parseLeftPanelCollapsed(storedPreference)
)
