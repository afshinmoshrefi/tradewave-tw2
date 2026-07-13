// Pure instrumentation for the automated headless-Chrome screenshot harness.
// No behavior changes - flags only. Safe to call from anywhere; no-ops when
// window is unavailable (SSR-proof guard).

export function markCaptureReady(name, meta) {
  if (typeof window === 'undefined') return;
  window.__twCapture = window.__twCapture || { ready: {}, meta: {} };
  window.__twCapture.ready[name] = true;
  window.__twCapture.meta[name] = meta || {};
  window.__twCapture.meta[name].ts = Date.now();
}

export function clearCaptureReady(name) {
  if (typeof window === 'undefined') return;
  window.__twCapture = window.__twCapture || { ready: {}, meta: {} };
  window.__twCapture.ready[name] = false;
}
