export const TOOLTIP_ENABLED_KEY = 'tw_tooltips_enabled';
export const LEGACY_TOOLTIP_ENABLED_KEY = 'tw_tooltips';

export const initialTooltipsEnabled = (storedPreference, legacyPreference) => {
  const preference = storedPreference === null || typeof storedPreference === 'undefined'
    ? legacyPreference
    : storedPreference;
  if (preference === null || typeof preference === 'undefined') return true;

  return preference === true
    || preference === 1
    || preference === '1'
    || preference === 'true';
};
