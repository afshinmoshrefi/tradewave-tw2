import { hasTaraPanelLayout, initialTaraPanelOpen } from './taraPanelPreference';

describe('Tara panel preference', () => {
  const desktop = { isMobile: false, isTablet: false, width: 1440, height: 900 };

  test('opens on the first desktop visit', () => {
    expect(initialTaraPanelOpen({ ...desktop, storedPreference: null })).toBe(true);
  });

  test('restores an explicit closed preference', () => {
    expect(initialTaraPanelOpen({ ...desktop, storedPreference: false })).toBe(false);
  });

  test('restores an explicit open preference', () => {
    expect(initialTaraPanelOpen({ ...desktop, storedPreference: true })).toBe(true);
  });

  test('does not open on a phone or overwrite its desktop preference', () => {
    const phone = { isMobile: true, isTablet: false, width: 390, height: 844 };
    expect(hasTaraPanelLayout(phone)).toBe(false);
    expect(initialTaraPanelOpen({ ...phone, storedPreference: true })).toBe(false);
  });

  test('treats tablet landscape as the desktop layout', () => {
    const tabletLandscape = { isMobile: true, isTablet: true, width: 1180, height: 820 };
    expect(hasTaraPanelLayout(tabletLandscape)).toBe(true);
    expect(initialTaraPanelOpen({ ...tabletLandscape, storedPreference: null })).toBe(true);
  });
});
