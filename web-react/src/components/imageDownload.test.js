import { downloadCanvasAsJpeg } from './imageDownload';

describe('downloadCanvasAsJpeg', () => {
  beforeEach(() => {
    URL.createObjectURL = jest.fn(() => 'blob:tradewave-snapshot');
    URL.revokeObjectURL = jest.fn();
  });

  afterEach(() => {
    jest.useRealTimers();
    jest.restoreAllMocks();
  });

  test('downloads an attached Blob link using the requested filename', async () => {
    jest.useFakeTimers();
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const canvas = {
      toBlob: callback => callback(new Blob(['jpeg'], { type: 'image/jpeg' })),
    };

    await downloadCanvasAsJpeg(canvas, 'TRV-snapshot.jpg');

    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(click).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[download="TRV-snapshot.jpg"]')).toBeNull();

    jest.runAllTimers();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:tradewave-snapshot');
  });

  test('falls back to a data URL when canvas Blob export is unavailable', async () => {
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const canvas = { toDataURL: jest.fn(() => 'data:image/jpeg;base64,abc') };
    const originalCreateObjectURL = URL.createObjectURL;
    URL.createObjectURL = undefined;

    await downloadCanvasAsJpeg(canvas, 'fallback.jpg');

    expect(canvas.toDataURL).toHaveBeenCalledWith('image/jpeg');
    expect(click).toHaveBeenCalledTimes(1);
    URL.createObjectURL = originalCreateObjectURL;
  });
});
