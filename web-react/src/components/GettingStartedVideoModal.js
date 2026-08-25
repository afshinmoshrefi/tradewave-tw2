import React, { useEffect } from 'react';
import ReactDOM from 'react-dom';
import {
  GETTING_STARTED_VIDEO_EMBED_URL,
  GETTING_STARTED_VIDEO_URL,
} from './gettingStartedVideo';
import './styles/GettingStartedVideoModal.css';

const GettingStartedVideoModal = ({ UITheme, onClose }) => {
  useEffect(() => {
    const handleKeyDown = event => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleBackdropClick = event => {
    if (event.target === event.currentTarget) onClose();
  };

  return ReactDOM.createPortal(
    <div
      className={`tw-getting-started-video-overlay tw-getting-started-video-overlay--${UITheme === 'light' ? 'light' : 'dark'}`}
      onMouseDown={handleBackdropClick}
      role="presentation"
    >
      <section
        className="tw-getting-started-video-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tw-getting-started-video-title"
      >
        <button
          type="button"
          className="tw-getting-started-video-close"
          aria-label="Close Getting Started video"
          onClick={onClose}
        >
          &times;
        </button>

        <div className="tw-getting-started-video-copy">
          <div className="tw-getting-started-video-eyebrow">Getting Started</div>
          <h2 id="tw-getting-started-video-title">Find Your First Wave</h2>
          <p>Watch this quick tour, then try the same steps in the Wave Viewer.</p>
        </div>

        <div className="tw-getting-started-video-frame">
          <iframe
            src={GETTING_STARTED_VIDEO_EMBED_URL}
            title="TradeWave Getting Started video"
            allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        </div>

        <div className="tw-getting-started-video-actions">
          <a href={GETTING_STARTED_VIDEO_URL} target="_blank" rel="noreferrer">
            Open on YouTube
          </a>
          <button type="button" onClick={onClose}>Start Exploring</button>
        </div>
      </section>
    </div>,
    document.body
  );
};

export default GettingStartedVideoModal;
