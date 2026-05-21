// Runtime console gate.
//
// The SAME React build is compiled once on dev and copied to staging + prod
// (ops/DEPLOY_STAGING.md), so we cannot strip debug logs at build time - it would
// strip them everywhere or nowhere. Instead we suppress verbose console output at
// runtime unless the Flask /app/ shell told us we are on dev or staging via
// window.tw2_env. Production (and any unknown deployed env) stays quiet so debug
// logs - several of which print the appserver JWT inside request URLs - never reach
// the production console.
//
// console.warn and console.error are intentionally left intact in every env.
//
// Imported FIRST in index.js so it runs before any component module-level logging.
(function () {
  try {
    // CRA replaces process.env.NODE_ENV at build time: 'development' under
    // `npm start`, 'production' under `npm run build`. Keep logs on the local
    // dev server, where there is no Flask-injected window.tw2_env.
    var isLocalDevServer =
      typeof process !== 'undefined' &&
      process.env &&
      process.env.NODE_ENV === 'development';

    var env = (typeof window !== 'undefined' && window.tw2_env) || '';
    var allow = isLocalDevServer || env === 'dev' || env === 'staging';

    if (!allow) {
      var noop = function () {};
      console.log = noop;
      console.debug = noop;
      console.info = noop;
    }
  } catch (e) {
    /* never let logging config break the app */
  }
})();
