import React from 'react';

const RELOAD_COUNT_KEY = 'tw_error_reload_count';
const RELOAD_TIMESTAMP_KEY = 'tw_error_reload_ts';
const MAX_RELOADS = 3;           // max reloads within the time window
const RELOAD_WINDOW_MS = 30000;  // 30 second window

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, tooManyReloads: false };
  }

  static getDerivedStateFromError(error) {
    // Check if we've been reloading too many times (infinite loop protection)
    try {
      const now = Date.now();
      const lastTs = parseInt(sessionStorage.getItem(RELOAD_TIMESTAMP_KEY) || '0', 10);
      let count = parseInt(sessionStorage.getItem(RELOAD_COUNT_KEY) || '0', 10);

      if (now - lastTs > RELOAD_WINDOW_MS) {
        // Outside the window, reset counter
        count = 1;
      } else {
        count += 1;
      }

      sessionStorage.setItem(RELOAD_COUNT_KEY, count.toString());
      sessionStorage.setItem(RELOAD_TIMESTAMP_KEY, now.toString());

      if (count >= MAX_RELOADS) {
        return { hasError: true, tooManyReloads: true };
      }
    } catch (e) { /* sessionStorage unavailable */ }

    return { hasError: true, tooManyReloads: false };
  }

  componentDidCatch(error, errorInfo) {
    const where = this.props.name ? `[${this.props.name}] ` : '';
    console.error(`TradeWave error caught: ${where}`, error, errorInfo);
  }

  // Reset just this boundary's error state (for nested panels — don't reload the whole app).
  handleRetryPanel = () => {
    try {
      sessionStorage.removeItem(RELOAD_COUNT_KEY);
      sessionStorage.removeItem(RELOAD_TIMESTAMP_KEY);
    } catch (e) { /* ignore */ }
    this.setState({ hasError: false, tooManyReloads: false });
  }

  handleReload = () => {
    this.setState({ hasError: false, tooManyReloads: false });
    window.location.reload();
  }

  handleResetAndReload = () => {
    // Full reset: clear all TradeWave session/local state that could cause crashes
    try {
      sessionStorage.removeItem(RELOAD_COUNT_KEY);
      sessionStorage.removeItem(RELOAD_TIMESTAMP_KEY);
    } catch (e) { /* ignore */ }
    this.setState({ hasError: false, tooManyReloads: false });
    window.location.reload();
  }

  render() {
    if (this.state.hasError) {
      // Nested boundaries (those with a `name` prop) render a compact panel-sized
      // fallback that lets the rest of the app keep working. Top-level boundaries
      // (no name, e.g. the one wrapping <App /> in index.js) keep the full-screen
      // "Session interrupted" / "Something went wrong" UI.
      const isNested = !!this.props.name;

      if (isNested) {
        return (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            justifyContent: 'center', minHeight: '120px', padding: '16px',
            fontFamily: 'system-ui, sans-serif',
            backgroundColor: 'rgba(255,255,255,0.03)',
            border: '1px dashed rgba(255,255,255,0.15)',
            borderRadius: '8px', color: '#e0e0e0', textAlign: 'center',
          }}>
            <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '6px' }}>
              {this.props.name} encountered an error
            </div>
            <div style={{ fontSize: '12px', opacity: 0.65, marginBottom: '12px' }}>
              This panel could not render. The rest of the app is still working.
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={this.handleRetryPanel}
                style={{
                  backgroundColor: '#3b82f6', color: '#fff', border: 'none',
                  borderRadius: '6px', padding: '6px 16px', fontSize: '12px',
                  fontWeight: 600, cursor: 'pointer',
                }}
              >
                Retry panel
              </button>
              <button
                onClick={this.handleReload}
                style={{
                  backgroundColor: 'transparent', color: '#9ca3af',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '6px', padding: '6px 16px', fontSize: '12px',
                  fontWeight: 600, cursor: 'pointer',
                }}
              >
                Reload app
              </button>
            </div>
          </div>
        );
      }

      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100vh', fontFamily: 'system-ui, sans-serif',
          backgroundColor: '#1e1e2e', color: '#e0e0e0', padding: '20px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '36px', fontWeight: 700, marginBottom: '16px' }}>TradeWave</div>
          <div style={{
            backgroundColor: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: '12px', padding: '24px 32px', maxWidth: '440px',
          }}>
            {this.state.tooManyReloads ? (
              <>
                <div style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>
                  Something went wrong
                </div>
                <div style={{ fontSize: '14px', opacity: 0.7, marginBottom: '20px', lineHeight: 1.5 }}>
                  TradeWave encountered a repeated error. Click below to do a full reset and reload.
                </div>
                <button
                  onClick={this.handleResetAndReload}
                  style={{
                    backgroundColor: '#3b82f6', color: '#fff', border: 'none',
                    borderRadius: '8px', padding: '10px 28px', fontSize: '15px',
                    fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  Reset and Reload
                </button>
              </>
            ) : (
              <>
                <div style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>
                  Session interrupted
                </div>
                <div style={{ fontSize: '14px', opacity: 0.7, marginBottom: '20px', lineHeight: 1.5 }}>
                  This usually happens when your session expires after being idle.
                  Click below to reload.
                </div>
                <button
                  onClick={this.handleReload}
                  style={{
                    backgroundColor: '#3b82f6', color: '#fff', border: 'none',
                    borderRadius: '8px', padding: '10px 28px', fontSize: '15px',
                    fontWeight: 600, cursor: 'pointer',
                  }}
                >
                  Reload TradeWave
                </button>
              </>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}


