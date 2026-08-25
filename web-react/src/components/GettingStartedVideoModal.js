import React, { useEffect } from 'react';
import ReactDOM from 'react-dom';
import { BsCameraVideoFill } from 'react-icons/bs';
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
        <header className="tw-getting-started-video-header">
          <div className="tw-getting-started-video-heading-icon" aria-hidden="true">
            <BsCameraVideoFill />
          </div>
          <div className="tw-getting-started-video-copy">
            <div className="tw-getting-started-video-eyebrow">Getting Started Video</div>
            <h2 id="tw-getting-started-video-title">Learn TradeWave in 4 Minutes</h2>
          </div>
          <button
            type="button"
            className="tw-getting-started-video-close"
            aria-label="Close Getting Started video"
            onClick={onClose}
          >
            &times;
          </button>
        </header>

        <div className="tw-getting-started-video-frame">
          <iframe
            src={GETTING_STARTED_VIDEO_EMBED_URL}
            title="TradeWave Getting Started video"
            allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        </div>

        <footer className="tw-getting-started-video-footer">
          <p>Use the video icon in the toolbar to watch this guide again.</p>
          <div className="tw-getting-started-video-actions">
            <a href={GETTING_STARTED_VIDEO_URL} target="_blank" rel="noreferrer">
              Watch in a New Tab
            </a>
            <button type="button" onClick={onClose}>Go to Wave Viewer</button>
          </div>
        </footer>
      </section>
    </div>,
    document.body
  );
};

export default GettingStartedVideoModal;
