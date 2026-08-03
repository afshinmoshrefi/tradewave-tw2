export const TARA_PANEL_OPEN_KEY = 'tw_tara_panel_open';

export const hasTaraPanelLayout = ({ isMobile, isTablet, width, height }) => {
  return !isMobile || (isTablet && height < width);
};

export const initialTaraPanelOpen = ({ isMobile, isTablet, width, height, storedPreference }) => {
  if (!hasTaraPanelLayout({ isMobile, isTablet, width, height })) return false;

  // Tara is discoverable on the first desktop visit. Once the user explicitly
  // opens or closes it, their user-scoped preference wins on later visits.
  if (storedPreference === null || typeof storedPreference === 'undefined') return true;

  return storedPreference === true || storedPreference === 1 || storedPreference === '1' || storedPreference === 'true';
};
