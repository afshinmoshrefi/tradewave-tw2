export const TOOLTIP_ENABLED_KEY = 'tw_tooltips_enabled';

export const initialTooltipsEnabled = (storedPreference) => {
  if (storedPreference === null || typeof storedPreference === 'undefined') return true;

  return storedPreference === true
    || storedPreference === 1
    || storedPreference === '1'
    || storedPreference === 'true';
};
