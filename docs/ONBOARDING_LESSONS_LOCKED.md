# TradeWave Onboarding - Locked Lesson Deck (v1, pre-framing-refine)
_7 days x 3 screens. Refine the COPY per the 3 framings; keep the structure._

## Navigation spec
WITHIN A DAY (always exactly 3 screens): a Back / Next bar at the bottom pages through that day's 3 screens. A 3-dot progress rail sits at the top (one dot per screen, current dot filled) so the user always sees the day is short and finite - this finite signal is the single biggest anti-bail lever the verdicts named, so it is mandatory. Back is HIDDEN (not rendered) on screen 1 of a day - never greyed-but-dead, because a literal beginner reads a dead button as broken. Back never jumps to yesterday. On screen 3 (the 'Try It Now' screen) the Next button becomes 'Done for Today'. BEFORE the box collapses, it shows a one-line confirm so the user never thinks they lost it: 'Nice work - I'm still here under the lightbulb. Day N+1 is ready tomorrow.' Then it collapses to the lightbulb hint. 'Done for Today' does NOT advance into the next day - the next day is gated by the calendar (getOnboardingDay), so tomorrow's lesson opens fresh tomorrow.

ACROSS DAYS / REVISIT: a small 'Lessons' link in the header (NOT a row of 7 visible day-tabs - seven slots telegraphs 'long course' and works against the calm tone) opens a simple list of Day 1 through the current unlocked day. Tapping any UNLOCKED earlier day reopens it at screen 1 in review mode with a soft 'Reviewing Day N' label; Back/Next walk that day's 3 screens; a 'Back to Today' link returns to the live day. Review never resets or re-locks progress. FUTURE days show as locked but WARM, not a wall: each locked row teases its payoff instead of just blocking - 'Day 5: spot the fake winners', 'Day 7: the 100-year window' - so the lock reads as a coming attraction, never a paywall or punishment. The user can never page FORWARD past the current day, which holds the 7-day pacing.

A small 'where am I' line shows at the top on open so restore-vs-new-day is never invisible: 'Day 3 - new lesson today' on a fresh day vs 'Day 3 - picking up where you left off' on a same-day reopen.

## Day-start spec
The day shown is driven by the existing getOnboardingDay() counter (1-based, clamped to 7), backed by the existing localStorage tw_onboard_started_at - never guessed. Track the furthest day auto-opened in localStorage (tw_lesson_lastopened = day number). On the FIRST open of a calendar day greater than tw_lesson_lastopened, the box AUTO-OPENS to screen 1 of THAT new day with a gentle fade-and-rise and a clear 'Day N of 7 - new lesson today' label, then updates tw_lesson_lastopened so it auto-opens only ONCE per day. The auto-open must never cover what the user is reading and must be instantly draggable with an obvious (x); an auto-popup that ambushes a beginner over a busy trading screen is a fail condition.

SAME-DAY REOPEN (after a close): the box restores to the EXACT screen the user last viewed that day (per-day index tw_lesson_screen_<day>), with the label 'Day N - picking up where you left off', so closing to look at the chart and reopening never loses their place. If they already finished today's 3 screens, reopening lands on screen 3 with a calm 'You're all caught up - Day N+1 is ready tomorrow' and the 'Lessons' link, and it never re-nags.

NEW DAY ALWAYS STARTS FRESH at screen 1 and resets that day's saved screen index. SKIPPED DAYS never stack or fire all at once: if the counter advanced while the box was closed, the next open honors the newest unlocked day at screen 1, and any missed earlier days stay unlocked in the 'Lessons' list for self-paced catch-up. The drag position is remembered (tw_lesson_pos) so the box reopens where the user parked it - WITH a 'snap back to center' safety so a box parked off-screen or somewhere weird can always be recovered. After Day 7 the box opens to the Day 7 review and the lightbulb stays available forever. If the whole arc was dismissed (existing tw_onboard_dismissed), the box stays closed but the lightbulb still reopens it on demand.

## Dismiss/reopen spec
CLOSE: the (x) hides the box and pins a small, premium lightbulb/help hint where the old Tara launcher sat. The FIRST time the user ever closes the box, the lightbulb pulses once AND shows a one-time bubble 'Your lessons live here' - several verdicts warned a beginner will silently lose the whole series if the reopen affordance isn't unmistakable, so this first-close cue is mandatory and fires only once (flag tw_lesson_hintseen). After that the lightbulb sits quietly, always visible.

REOPEN: clicking the lightbulb restores the box to exactly where the user left off - the same day, the same screen (tw_lesson_screen_<day>), and the same drag position (tw_lesson_pos), with the appropriate 'picking up where you left off' or 'all caught up' label. It is a resume, never a restart.

A 'Start day over' link is available in the header so a user who got dropped into a mid-day screen and feels lost can restart today's 3 screens from screen 1 without affecting any other day. The lightbulb persists across days and forever after Day 7 as the permanent refresher entry point; closing is never destructive and never ends the series.

## Build notes
DATA + STATE
- Ship the deck as a static JS const (lessonDeck[7].screens[3], each {title, body, pointer}) - 21 screens, no fetch. Keep titles in AP Title Case with no terminal period; bodies sentence case. No em-dashes anywhere (use ' - '); the deck already complies.
- Day selection reuses the EXISTING getOnboardingDay() (1-based, clamp 1..7) on tw_onboard_started_at. Do NOT add a parallel counter. New localStorage keys: tw_lesson_lastopened (int day), tw_lesson_screen_<day> (0..2 per-day index), tw_lesson_pos ({x,y}), tw_lesson_hintseen (bool). Respect existing tw_onboard_dismissed.

VERIFIED TERM BINDINGS (do not drift from the live UI)
- '% Wins' / '% Profitable': SeasonalChartStats.js stat_labels show '% Wins' on the compact label set (lines ~27/32) and '% Profitable' on the wide set (line ~22/44); underlying data key is 'Percent Profitable'. Copy says '% Wins (sometimes labeled % Profitable)' - correct, keep both.
- 'Sharpe Ratio' / 'SR': same component shows 'Sharpe Ratio' (wide) and 'SR' (compact). Copy binds 'the Sharpe Ratio, or SR' - correct.
- 'PE+2': OppTable.js:72-86 computes the label from (currentYear % 4): 0=PE, 1=PE+1, 2=PE+2, 3=PE+3. 2026%4=2 => 'PE+2', and the tooltip (OppTable.js:1341) reads 'presidential election-cycle year'. ACTION ITEM: the Day-5 copy hardcodes 'PE+2', which is only correct in 2026-2026-style midterm years. Either (a) render the live PELabel into the Day-5 strings via a {peLabel} token so the lesson always matches the button (recommended), or (b) accept the lessons are written for the current cycle and gate/refresh the copy yearly. Do not let a beginner read 'PE+2' while the button says 'PE+1'.
- 'years buttons (10, 15, 17, 20)': confirm the live button set still reads 10/15/17/20 before shipping Day 4; if a market/config changes the set, update the Day-4 'Click 17' instruction to a button that exists, or generalize to 'the highest years button.'

FLOATING BOX (draggable)
- Reuse the existing Tara launcher anchor/position so the lightbulb lands exactly where users expect. The box is a fixed-position card; drag via the header bar (pointer events, clamp into viewport, persist tw_lesson_pos on drop). Provide a 'snap back to center' control + auto-recenter if the persisted pos is off-screen.
- Auto-open on a NEW day must fade-and-rise (not modal, no backdrop that blocks the chart/table), stay draggable immediately, and show an obvious (x). Set tw_lesson_lastopened on auto-open so it fires once/day.

PAGING (day-keyed)
- Within-day: 3-dot rail (top) + Back/Next (bottom). Hide Back on screen index 0 (do not render). Screen index 2 swaps Next -> 'Done for Today'; on click show the one-line confirm, write tw_lesson_screen_<day>=2, then collapse to lightbulb. Never auto-advance past the calendar day.
- 'Lessons' header link: list Day 1..currentDay unlocked (review mode, soft 'Reviewing Day N', 'Back to Today' exit) + locked future rows with warm teases. Block forward paging past currentDay.
- 'Start day over' header link: reset tw_lesson_screen_<day>=0 for the live day only.

FIRST-CLOSE CUE
- On the very first (x) ever (tw_lesson_hintseen false): pulse the lightbulb once + one-time bubble 'Your lessons live here', then set tw_lesson_hintseen=true. Never repeat.

COPY/READABILITY PASS (done)
- Flesch-Kincaid grade across sampled screens = 1.5-5.4 (all at/under 6th grade). Only edit applied: replaced the above-grade word 'fluke' with 'a one-time thing' (Day 4 S3 body) and kept 'luck' elsewhere; the Day-4 pointer already said 'luck'. House voice + the honesty refrain (Day 1 + Day 5 hard, light touches elsewhere) and the Day-1->Day-7 100-year tease/payoff are preserved.
- Generalized two example labels that were year-specific in the source pointers ('like 2026' -> 'like this one') so the pointer copy doesn't go stale; the in-body '2026' references stay because they're explicitly teaching the current midterm year.

DEPLOY
- React change only: build via `npm run build` (carries PUBLIC_URL=/app/), never raw react-scripts build; deploy by symlink-swap per ops/deploy.sh. gunicorn restart not needed (no Python change). No new appserver/gateway calls - the box is pure client state.

## THE DECK

### Day 1 - What This App Does and Why It Helps You
**[1] Some Stocks Move at the Same Time Each Year**
Think about stores in December. They get busy every year, like clockwork, because of holiday shopping. Some stocks act the same way. They tend to go up (or down) in the same few weeks each year. This happens for real reasons that repeat, like a company's earnings dates or a yearly product launch. That yearly habit has a name. It is called seasonality. This app finds those habits for you and checks them against almost 100 years of market history. By Friday I'll show you one stock window that has worked almost every time for nearly 100 years.
_Try it: Drag this box anywhere. Close it with the x - the lightbulb brings it back._

**[2] Why This Helps You - and Why to Trust It**
Say you were going to buy a stock like NVDA anyway. Instead of guessing, this app tells you when history was on your side. For example: this window finished higher 9 of the last 10 years. Finished higher just means the price went up over that stretch. Now the honest part. If it won 9 of 10 years, that also means it fell 1 of those years. A habit is not a promise. So this app always shows you the years a pattern lost, not just the years it won. That is how you trust a number instead of hoping.
_Try it: Notice we show both: the wins and the losses._

**[3] Try It Now - Open the Opportunity Table**
Let's click something real. Above the chat is the Opportunity Table. It lists stocks whose yearly habit is starting right now. Click the market picker and choose the Dow. The Dow is just the 30 biggest U.S. companies. Watch the list fill in. It looks like a lot of numbers, and that's okay. You only ever read one row at a time. See an empty or short list? Pick a different market like the S&P 500, or come back later. Some days are just quiet, and that is normal.
_Try it: Click the market picker and choose the Dow, then watch the list._

### Day 2 - Meet Tara - Your Plain-English Helper
**[1] Tara Reads the Numbers for You**
Meet Tara. She is a friendly helper that lives in the chat box. Her job is simple. Any number on the screen that looks confusing, you can ask her about it, and she tells you what it means in plain words. Here is the part that matters most. Tara only reads the real data from the app. She does not guess, and she never makes anything up. So she is the friend who has your back all week. You do not have to figure this out alone.
_Try it: Find the chat box. That is where Tara talks to you._

**[2] What's in One Row of the Table**
Now let's read one row together. The big list at the top is the table. Each row is one stock that is entering a strong window right about now. The app puts the best one at the top, so start there. For now, look at just two things. First, the name of the stock. Second, how often that window finished higher in past years. The app calls that number % Wins. A high % Wins means it worked most years. But it is honest too. No stock wins every year, so some years it lost. That is normal, and we will dig into the losing years tomorrow.
_Try it: Look at the top row. Read the stock name and its % Wins._

**[3] Try It Now - Ask Tara a Question**
Time to try it. Click the top row so Tara has a pattern to look at. Then open the chat and ask her something plain, like: Is the top stock's pattern any good? Read her answer in her own words. This is the fastest way to learn. When a number confuses you, you do not have to study it. You just ask Tara, and she explains it. Do this any time you feel stuck this week.
_Try it: No answer yet? Click a row first so Tara has a pattern to talk about._

### Day 3 - The Chart Checks One Pattern Up Close
**[1] What a Pattern Is**
A pattern is just a simple recipe. It has three plain parts: a stock, a start day, and how many days you hold it. For example: buy NVDA, start on June 24, hold for 20 days. That is one pattern. The app also tracks two more things behind the scenes - how many years of history it checked, and whether the stock tends to go up or down in that window. You do not need to set those by hand. The table fills them in for you.
_Try it: Look at any row in the table. Each one is a recipe like this._

**[2] Open One and See Which Years Won or Lost**
Click a row and that one pattern opens on the chart. The chart shows a year-by-year scoreboard. Green means the stock rose that year. Red means it fell. So you might see 8 green and 2 red, which means it went up in 8 years and down in 2. We never hide the red years. A pattern that wins often can still lose some years, and that is normal. Seeing the losses is how you learn which wins you can really trust.
_Try it: Count the green bars and the red bars on the chart. Both matter._

**[3] Try It Now - Find the Win Number**
Your turn. Click any row in the table to open its chart. Now find how often it won. That number is shown as % Wins (sometimes labeled % Profitable). It is just the share of years that went up - like 9 of 10 years. A higher number means history was on your side more often. But remember, even a high number had some losing years mixed in. Chart looks empty? Click a row in the table first, then come back to this card.
_Try it: Find the % Wins label on the chart and read its number._

### Day 4 - How to Trust a Pattern
**[1] A High Win Number Is Only Half the Story**
Look at the two lines on this screen. Both patterns won 8 of their last 10 years. So both look like winners. But the climbs are not the same. One line rises in calm, steady steps. The other one jumps up and down on the way, with scary drops. They end up in the same place, but one ride was a lot bumpier. The app measures how steady the ride was. It calls this the Sharpe Ratio, or SR for short. A higher SR means a smoother ride. Same win count, smoother ride - that is the one that is easier to trust.
_Try it: See the two lines above. The calm one and the jagged one BOTH won 8 of 10. Steadier is safer._

**[2] Don't Trust a Big Number From Only a Few Years**
Say a pattern won 3 out of 3 years. That is 100 percent. It sounds perfect. But 3 tries is just too few to mean much. We call this a small sample. A sample is simply how many years you are looking at. Three coin flips can all land heads by pure luck, but that does not mean the coin always lands heads. Now look at a pattern that won 18 of 20 years. That happened many times, so it is far stronger. And remember, even the strong one lost 2 of those 20 years. No pattern wins every time. More years tested means more trust, not less.
_Try it: When a win rate looks too good, check how many years it is built on. A few years proves little._

**[3] Try It Now - Change the Years**
Let's test a pattern yourself. Find the years buttons near the chart. They say 10, 15, 17, and 20. The app starts on 10 years. Click 17. Now watch the win number. Does it hold up? A pattern that stays strong over more years is sturdier, and you can trust it more. One that falls apart when you add years was probably just luck. There is no wrong answer here. You are only checking. If the numbers barely move, that is a good sign. It means the pattern has been steady across history, not a one-time thing.
_Try it: Click the 17 button and watch the win number. Steady across years means you can lean on it._

### Day 5 - Years Like 2026 Have Their Own Pattern
**[1] Some Years Repeat on a 4-Year Clock**
U.S. elections run on a 4-year clock. That means the same kind of year comes back every 4 years. We call that a cycle. A cycle is just a thing that repeats on a clock, like every 4 years. 2026 is a midterm year. That is the year that falls halfway between the big presidential votes. Some stock habits show up most in years like this. Remember: a habit is not a promise. It is something history did often, not every single time. We always show you the years it lost too, not just the years it won.
_Try it: On the next screen, see how the app shows only the past years that are like this one._

**[2] Show Only Years Like This One**
The app can hide every year that is not like 2026. Then you see what tends to work in a midterm year, and nothing else. This helps because a year like this one can act different from a normal year. Look for the PE+2 button above the table. PE+2 is the app's short name for this kind of election-cycle year. One simple idea here: same-kind-of-years only. Even with this on, some of those years still lost. A good habit shows up often, but never every time.
_Try it: Find the PE+2 button sitting just above the opportunity table._

**[3] Try It Now - Turn On PE+2**
Go ahead and click the PE+2 button now. Watch the table change. It will show patterns that have worked in midterm years like 2026. Did your list get short? That is normal. Fewer patterns pass this stricter test. A short list of strong ones is exactly what you want. Less is fine here. Even these stronger patterns lost in some years, so always check the win record before you trust one.
_Try it: Click a row in the new list to open that pattern on the chart and see its year-by-year record._

### Day 6 - Save It and Get Reminded
**[1] Save a Pattern You Like**
When you find a good window, save it so you do not lose it. A good window means three things: it won often, it was steady year to year, and it was tested over many years (not just a few). Saving keeps that pattern in your own list so you can find it again fast. Here is the part that matters most: saved patterns stay with your account even after your free trial ends. Your work does not disappear. Remember, every pattern has off years too. A window that won 9 of the last 10 years still lost 1 of them.
_Try it: Find a row you like in the table, click it to open it on the chart, then look for the save star._

**[2] Set a Reminder for When It Opens**
A pattern only matters when its window starts. The window is the stretch of days when history was on your side. If that window opens in three months, you do not want to watch the calendar every day. So set a reminder. The app remembers the date for you and pings you the day the window opens. That way you can forget about it until it is time to act. For example, say a strong NVDA window starts in October. Set the reminder now, go live your life, and the app taps you on the shoulder in October.
_Try it: On a saved pattern, look for the reminder bell and turn it on._

**[3] Try It Now - Save One and Set Its Reminder**
Time to use the keep-it tools for real. Pick the best pattern you have found so far. Click the save star to add it to your list. Then turn on its reminder bell so the app pings you when its window opens. That is it. Now your favorite pattern is saved and will not get lost, and you do not have to track the date yourself. Have not found a favorite yet? Save any strong one for now. You can always remove it later.
_Try it: Click the save star, then click the reminder bell. Two clicks and you are set._

### Day 7 - The 100-Year Window and Your First Real Pick
**[1] The Big One - a Window Strong for Almost 100 Years**
On Day 1 we promised you a special one. Here it is. A year like 2026 is a midterm year, which means it lands in the middle of a 4-year cycle in the markets. In these years, one window in the S&P 500 (a big group of 500 large companies) has finished higher in almost every cycle for about 100 years. That is one of the longest, steadiest habits we can find. It is rare and it is strong. But it is still a habit, not a promise. It has had down years too, and it could have one again. A pattern this old is worth a serious look, and that is exactly why checking deep history pays off.
_Try it: Open the chart on this S&P window and watch the green and red years line up._

**[2] Read It Like You Learned This Week**
You can now check this window yourself. Use the same steps from this week. First, look at % Wins to see how often it finished higher. Next, look at the years it lost - the red bars next to the green ones - so you know the down years are real. Then make sure it stays strong across many years, not just a few. Last, check the SR (the steadiness score) so you know the wins were calm and not all luck. Reading it yourself is the real win. Quick check: which would you trust more, a window that won 100% of 3 years, or one that won 90% of 17 years? The 17-year one. More tries means a steadier, more trustworthy number.
_Try it: Find % Wins and SR on the window and say what each one tells you._

**[3] Try It Now - Find, Check, and Save One Pattern**
Time to drive. Here is the full loop in your own hands. Pick a market at the top. Scan the table for a pattern that starts today. Click a row to open it on the chart. Check the win number and the steadiness, and look at the years it lost too. If you are unsure, ask Tara - she reads the real numbers in plain words and never makes them up. When you find one you trust, save it and set a reminder so it pings you when its window opens. Saved patterns stay with you even after the trial ends. You now know how to find, check, trust, and keep a seasonal pattern. That is the whole skill. The box is always right here under the lightbulb whenever you want a refresher. Nice work.
_Try it: Save one pattern you trust and turn on its reminder._
