import {
  GETTING_STARTED_VIDEO_EMBED_URL,
  GETTING_STARTED_VIDEO_SEEN_KEY,
  GETTING_STARTED_VIDEO_URL,
  shouldAutoOpenGettingStartedVideo,
} from './gettingStartedVideo';

describe('getting started video state', () => {
  test('uses a versioned customer-scoped preference key', () => {
    expect(GETTING_STARTED_VIDEO_SEEN_KEY).toBe('tw_getting_started_video_seen_v2');
  });

  test('opens until the customer has closed the video once', () => {
    expect(shouldAutoOpenGettingStartedVideo(null)).toBe(true);
    expect(shouldAutoOpenGettingStartedVideo(false)).toBe(true);
    expect(shouldAutoOpenGettingStartedVideo(true)).toBe(false);
  });

  test('uses the privacy-enhanced player without autoplay', () => {
    expect(GETTING_STARTED_VIDEO_URL).toBe('https://youtu.be/7ZQoj2e93oo');
    expect(GETTING_STARTED_VIDEO_EMBED_URL).toContain('youtube-nocookie.com/embed/7ZQoj2e93oo');
    expect(GETTING_STARTED_VIDEO_EMBED_URL).toContain('autoplay=0');
    expect(GETTING_STARTED_VIDEO_EMBED_URL).toContain('cc_load_policy=0');
    expect(GETTING_STARTED_VIDEO_EMBED_URL).not.toContain('cc_load_policy=1');
  });
});
