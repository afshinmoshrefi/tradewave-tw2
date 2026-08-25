export const GETTING_STARTED_VIDEO_ID = '7ZQoj2e93oo';
export const GETTING_STARTED_VIDEO_URL = `https://youtu.be/${GETTING_STARTED_VIDEO_ID}`;
export const GETTING_STARTED_VIDEO_EMBED_URL = `https://www.youtube-nocookie.com/embed/${GETTING_STARTED_VIDEO_ID}?rel=0`;

// Version this key when every customer should see a materially new onboarding video.
// Common.js scopes it to the signed-in customer, so accounts sharing one browser do
// not suppress each other's first view.
export const GETTING_STARTED_VIDEO_SEEN_KEY = 'tw_getting_started_video_seen_v1';

export const shouldAutoOpenGettingStartedVideo = seen => seen !== true;
