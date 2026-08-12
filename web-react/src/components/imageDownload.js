export const downloadCanvasAsJpeg = (canvas, filename) => {
  if (!canvas) return Promise.reject(new Error('Screenshot canvas is unavailable'));

  const downloadName = filename || 'TradeWave-snapshot.jpg';
  const clickDownload = (href, revokeAfterClick = false) => {
    const link = document.createElement('a');
    link.download = downloadName;
    link.href = href;
    link.style.display = 'none';

    // Chrome can ignore a delayed click on a detached data-link. Attaching a
    // Blob-backed link keeps screenshot downloads reliable after rendering.
    document.body.appendChild(link);
    link.click();
    link.remove();

    if (revokeAfterClick) {
      window.setTimeout(() => URL.revokeObjectURL(href), 1000);
    }
  };

  if (typeof canvas.toBlob !== 'function' || typeof URL.createObjectURL !== 'function') {
    clickDownload(canvas.toDataURL('image/jpeg'));
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    canvas.toBlob(blob => {
      if (!blob) {
        reject(new Error('Screenshot image could not be created'));
        return;
      }

      const objectUrl = URL.createObjectURL(blob);
      clickDownload(objectUrl, true);
      resolve();
    }, 'image/jpeg', 0.92);
  });
};
