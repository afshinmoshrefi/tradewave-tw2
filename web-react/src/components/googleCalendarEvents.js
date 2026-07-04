// Shared Google Calendar event machinery for TradeWave seasonal patterns.
// Used by BOTH the AddGC dialog (Portfolio Manager -> calendar icon, custom
// time/reminders) and the one-click notify bell on the wave viewer toolbar
// (SeasonalBarChart). Keep ALL event-content logic here so the two paths can
// never drift apart.
//
// OAuth: ONE client for all environments (2026-07-04 origin_mismatch fix).
// Google's consent popup validates the page's JS origin against the client's
// "Authorized JavaScript origins" list - all site origins (tradewave.ai, www,
// tw2-dev, tw2-stage) are registered on this tradeseasonals@gmail client in
// console.cloud.google.com -> APIs & Services -> Credentials.
// CSP note: nginx must allow accounts.google.com (script/frame/connect) and
// www.googleapis.com (connect) - see ops/nginx/snippets/security_headers.conf.

export const GC_CLIENT_ID = '914262652560-gbih917rcpp57gfci0v94es7bu9k42uu.apps.googleusercontent.com'
export const GC_SCOPES = 'https://www.googleapis.com/auth/calendar'
export const GSI_SRC = 'https://accounts.google.com/gsi/client'

// Idempotent GIS script loader. Unlike a naive appendChild, resolves when an
// already-present tag has finished loading (window.google check).
export const loadGsiScript = () =>
    new Promise((resolve, reject) => {
        if (window.google && window.google.accounts && window.google.accounts.oauth2) return resolve()
        let script = document.querySelector(`script[src="${GSI_SRC}"]`)
        if (!script) {
            script = document.createElement('script')
            script.src = GSI_SRC
            document.body.appendChild(script)
        }
        script.addEventListener('load', () => resolve())
        script.addEventListener('error', (err) => reject(err))
        // Already loaded before listeners attached (cached script tag):
        if (window.google && window.google.accounts && window.google.accounts.oauth2) resolve()
    })

// ISO "2026-07-06" -> "Jul 6, 2026" (noon local avoids timezone day-shift)
export function friendlyDate(iso) {
    return new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

// "10" -> "last 10 years"; "odd"/"even" -> "odd/even years"; "pe..." -> election-cycle years
export function friendlyYears(years) {
    const y = String(years);
    if (/^\d+$/.test(y)) return `last ${y} years`;
    if (y === 'odd' || y === 'even') return `${y} years`;
    if (y.toLowerCase().startsWith('pe')) return 'election-cycle years';
    return `${y} years`;
}

// If the ISO date falls on a weekend, return the next Monday (reminders should
// fire on a trading day); otherwise return the date unchanged.
export function shiftWeekendToNextMonday(iso) {
    const dtz = new Date();
    const mins = dtz.getTimezoneOffset();
    const ltzo = `${String(Math.floor(mins / 60)).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`;
    const date = new Date(`${iso}T06:00:00-${ltzo}`); // 6AM local, avoids off-by-one
    const dayOfWeek = date.getDay();
    if (dayOfWeek === 0 || dayOfWeek === 6) {
        const daysUntilMonday = dayOfWeek === 0 ? 1 : 8 - dayOfWeek;
        date.setDate(date.getDate() + daysUntilMonday);
        return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    }
    return iso;
}

// "2:30PM" -> ["14:30:00", "15:30:00"] (start + 1h end, capped before midnight).
// 12-hour edge cases matter: 12:xxAM is 00:xx and 12:xxPM stays 12:xx.
export function convertEventTime24(timeStr) {
    const ampm = timeStr.substring(timeStr.length - 2);
    const tmp = timeStr.substring(0, timeStr.length - 2);
    let [hours, min] = tmp.split(':').map((s) => parseInt(s, 10));

    if (ampm === 'PM' && hours !== 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;

    // End time = start + 1h, but never past midnight (keep the event same-day):
    // 11:00PM -> 23:00-23:30, 11:30PM -> 23:30-23:45.
    let endHours = hours + 1;
    let endMin = min;
    if (endHours >= 24) {
        endHours = 23;
        endMin = min === 0 ? 30 : 45;
    }

    const pad = (n) => String(n).padStart(2, '0');
    return [`${pad(hours)}:${pad(min)}:00`, `${pad(endHours)}:${pad(endMin)}:00`];
}

// Build ONE Google Calendar event dict ('start' or 'end' bookend of the pattern).
//
// Event content design (2026-07-04, modeled on Seasonax/Equity Clock/Almanac
// conventions): scannable title = ticker + direction + which bookend; short
// stat-backed body; links to BOTH the wave viewer (deep link) and the shareable
// report; created/saved dates; one-line research-not-advice footer. Google
// Calendar renders <b>/<br>/<a> - keep to that subset (Apple/Outlook ICS sync
// shows raw tags, so heavier HTML is a liability).
//
// p = { rid, ticker, direction, date1, date2, days, years, resource_group,
//       slug, sharpe_ratio, publishDate, stats,           // stats = ChartData4 stats dict or null
//       eventTime, emailReminder, popupReminder,          // user prefs (defaults: '8:00AM', true, true)
//       reminderDate1, reminderDate2 }                    // weekend-shifted reminder dates (ISO)
export function buildPatternEventDict(start_or_end, p) {

    // window.location.origin (NOT .host): the href needs the https:// scheme,
    // otherwise Google Calendar treats it as a relative link and it 404s.
    const report_url = `${window.location.origin}/r/${p.slug}/`;
    // Same ?o= deep-link format App.js parses: base64("rid|symbol|date1|days|years")
    const viewer_url = `${window.location.origin}/app/?o=${window.btoa(`${p.rid}|${p.ticker}|${p.date1}|${p.days}|${p.years}`)}`;
    const [eventTime24_1, eventTime24_2] = convertEventTime24(p.eventTime);

    const dirWord = String(p.direction).toLowerCase().startsWith('s') ? 'Short' : 'Long';
    const range_text = `${friendlyDate(p.date1)} to ${friendlyDate(p.date2)}`;
    const is_start = start_or_end === 'start';

    // Historical-evidence line - only when stats are available.
    let stats_line = '';
    if (p.stats && p.stats['Percent Profitable']) {
        const nw = parseInt(p.stats['Num Winners'], 10);
        const nl = parseInt(p.stats['Num Losers'], 10);
        const counts = (!isNaN(nw) && !isNaN(nl)) ? ` (${nw} of ${nw + nl} years)` : '';
        const avg = p.stats['Avg Profit'] ? ` · Avg gain ${p.stats['Avg Profit']}` : '';
        const sharpe = p.sharpe_ratio ? ` · Sharpe ratio ${p.sharpe_ratio}` : '';
        stats_line = `Historical record (${friendlyYears(p.years)}): ${p.stats['Percent Profitable']} of years profitable${counts}${avg}${sharpe}<br><br>`;
    }

    // Weekend-shift note: the reminder was moved to the next Monday when the
    // true pattern date lands on a weekend - say so, or the event date looks wrong.
    const actual_date = is_start ? p.date1 : p.date2;
    const reminder_date = is_start ? p.reminderDate1 : p.reminderDate2;
    const shift_note = actual_date !== reminder_date
        ? `Note: the pattern's actual ${is_start ? 'start' : 'end'} date, ${friendlyDate(actual_date)}, falls on a weekend - this reminder is set for ${friendlyDate(reminder_date)}, the next trading day.<br>`
        : '';

    const saved_line = p.publishDate ? `Pattern saved to your portfolio ${friendlyDate(String(p.publishDate).substring(0, 10))} · ` : '';
    const created_text = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

    const description =
        `<b>Seasonal pattern window ${is_start ? 'opens' : 'closes'} today.</b><br>` +
        `${p.ticker} · ${dirWord} · ${range_text} (${p.days} days) · ${p.resource_group}<br><br>` +
        stats_line +
        `<a href="${viewer_url}">Open this pattern in the TradeWave Wave Viewer</a><br>` +
        `<a href="${report_url}">View the shareable report</a><br><br>` +
        shift_note +
        `${saved_line}Calendar events created ${created_text} by <a href="https://tradewave.ai">tradewave.ai</a><br>` +
        `Historical research for educational purposes, not advice or a recommendation.`;

    const summary = `${p.ticker} ${dirWord} — TradeWave Seasonal ${is_start ? 'Start' : 'End'} (${friendlyDate(p.date1)} – ${friendlyDate(p.date2)})`;

    const overrides = [];
    if (p.emailReminder) overrides.push({ 'method': 'email', 'minutes': 24 * 60 });
    if (p.popupReminder) overrides.push({ 'method': 'popup', 'minutes': 5 });

    return {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': `${reminder_date}T${eventTime24_1}`,
            'timeZone': Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        'end': {
            'dateTime': `${reminder_date}T${eventTime24_2}`,
            'timeZone': Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        'reminders': {
            'useDefault': false,
            'overrides': overrides,
        },
    };
}

// Insert both events with one access token; resolves to the parsed JSON results.
export const insertCalendarEvents = (accessToken, eventDicts) =>
    Promise.all(eventDicts.map((dict) =>
        fetch('https://www.googleapis.com/calendar/v3/calendars/primary/events', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + accessToken },
            body: JSON.stringify(dict),
        }).then((resp) => resp.json())
    ))

// One-shot token flow: loads GIS, requests an access token (popup - MUST be
// called within a user gesture / transient activation), and resolves with the
// token. Rejects on load failure, popup block, or user cancel.
export const requestCalendarAccessToken = () =>
    loadGsiScript().then(() => new Promise((resolve, reject) => {
        const tc = window.google.accounts.oauth2.initTokenClient({
            client_id: GC_CLIENT_ID,
            scope: GC_SCOPES,
            callback: (tokenResponse) => {
                if (tokenResponse && tokenResponse.access_token) resolve(tokenResponse.access_token)
                else reject(new Error('no access token'))
            },
            error_callback: (err) => reject(new Error((err && err.type) || 'oauth error')),
        })
        tc.requestAccessToken()
    }))
