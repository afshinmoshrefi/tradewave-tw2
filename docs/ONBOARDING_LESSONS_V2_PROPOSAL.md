# Onboarding Lessons v2 — Proposal (2026-07-04)

Goal: get a new user educated enough in 7 days to be productive (and ideally
profitable) on their own — because a user who can read the data is the user who
subscribes. Day 7 now closes the funnel honestly: the trial-end screen and the
existing usage-measured recommendation card, on the rule of never selling what
their own week says they don't need.

Every fix below is grounded in the verified current UI (SeasonalBarChart,
SeasonalChart dots, dynamic years menu, PE checkbox, Notify me bell, + save,
TrialConversionCard). Voice rules preserved: human, confident, honest, no
advice, no em-dashes (use " - ").

Owner issues addressed, by day:
- Day 3: date-range copy matches the real bordered MM-DD box in the control bar.
- Day 3: stats-table directions match the real dots (above the bottom chart,
  right side, two white one red, red = current view, middle = Wave Stats).
- Day 4: "three years proves nothing" replaced with a positive depth argument
  anchored to what TradeWave actually shows (starts at 10 years).
- Day 4: stress-test copy explains the menu only offers the years the stock
  actually has (young stock = shorter menu = hold it to a higher bar).
- Day 5: fully year-agnostic. New live tokens {year} and {cyclePhrase}
  ("a midterm year" / "an election year" / ...) computed the same way
  {peLabel} already is. Works in 2027, 2028, forever.
- Day 6: teaches the real affordances by name: the + (save to portfolio) and
  the Notify me bell (Notifications portfolio + calendar dates for the
  window's open and close).
- Day 7: polished to carry the book's title. Plus a NEW closing screen tied to
  the TRIAL clock (not the lesson counter): trial ends today, here's what
  stays free, and a button into the measured recommendation card.

Legend: [unchanged] = keep current copy verbatim. {tokens} fill live at render.

---

## Day 1 — How These Lessons Work

### Screen 1: About These Daily Lessons  [unchanged]

### Screen 2: Your Job This Week
Lead: Simple goal: find a few good opportunities worth a closer look. That's
the whole game.
- We dig up the names with a real seasonal habit.
- Ranked by what actually happened, strongest on top.
- All week you're on full access - every market, every year of history. Use it hard.
- We point. You decide what's worth a look.

(One added bullet: tells them the week runs on full access. They should feel
the whole product before Day 7 asks them to keep it.)

### Screen 3: Read the Opportunity Table  [unchanged]

### Screen 4: Choose How Many Years You're Seeing
Lead: You are looking at seasonal opportunities based on the last 10 years by
default.
- Click the year selector at the top of the Opportunity Table - it opens on 10 years.
- Select 15.
- Same market, deeper history - a longer test of every name on the list.
  Depth is a theme we'll come back to.

(Last bullet plants the Day 4 depth argument early.)

---

## Day 2 — Meet Tara, Your Analyst  [unchanged, all 3 screens]

---

## Day 3 — See the Whole Track Record

### Screen 1: Read the Date Window Above the Chart   (FIXED)
Lead: Load one onto the chart, then find the small bordered date box in the
control bar right above it - that is the whole trade, written as dates.
- Yours reads '{dateRange}' right now - that's month-day to month-day.
- First date is the buy, second is the sell. That exact window is what
  everything on this screen is measuring.
- Each bar below is one year: what that window returned if you bought the
  first date and sold the second.

### Screen 2: Green Is Up, Red Is Down  [unchanged]

### Screen 3: Open One and Really Look   (FIXED via the {statsIntro} fill string)
Deck copy unchanged. The device-aware fill strings in LessonBox change to
match the real control:

NEW {statsIntro} (desktop):
"Now look just above the bottom chart, on its right side - three small dots,
two white and one red. The red one is the view you're on now. Click the
middle dot - that opens the Wave Stats table."

NEW {statsOpen} (desktop, Day 4 lead): "Click the middle of the three dots
above the bottom chart, on its right side - that's the Wave Stats table"

NEW {statsAt} (desktop, Day 7): "behind the middle dot above the bottom chart"

(Mobile strings stay swipe-based, unchanged.)

---

## Day 4 — Tell the Solid Ones Apart

### Screen 1: Win Rate Isn't the Whole Story  [unchanged]

### Screen 2: A Short Streak Is Still a Short Streak   (REPLACES "Three Years Proves Nothing")
Lead: Every list here opens with 10 years of history behind it, and you can
ask for a lot more. Here's why you should: a perfect run over a few years can
be luck. A strong run over twenty years is a habit.
- Twenty years has been through crashes, rate hikes, elections and panics -
  and the window still worked. That's weather a short streak has never seen.
- So 90% profitable across 20 years beats 100% across 5, almost every time.
- And even the strong ones owe you an off year now and then.

(No more invented "3 out of 3" scenario - the contrast now uses 5 years, the
actual minimum the app offers, and starts from the 10-year default the user
is really looking at.)

### Screen 3: Stress-Test the Years   (FIXED - answers "what if it doesn't have 17 years?")
Lead: Let's push on one and see if it holds.
- Open the year selector in the control bar above the chart - it opens on 10.
- The menu only offers as many years as the stock actually has. A young stock
  might top out at 6 or 8 - that's not an error, that's its whole life so far.
  Shorter record, higher bar.
- Pick the biggest number it offers - now you're asking everything of it.
- % Profitable still holds at full depth? That one's solid.

---

## Day 5 — The Market's Four-Year Clock   (WHOLE DAY NOW YEAR-AGNOSTIC)

Theme: "The Market's Four-Year Clock"
Tease: "the market's four-year clock, and where this year sits"

New live tokens, computed next to the existing {peLabel} logic:
  {year}        -> current year, e.g. "2026"
  {cyclePhrase} -> "an election year" (PE) | "a post-election year" (PE+1) |
                   "a midterm year" (PE+2) | "a pre-election year" (PE+3)
(Article included in the token so "a/an" is always right.)

### Screen 1: Where {year} Sits on the Clock
Lead: Markets watch the election calendar, and it runs on a four-year clock:
election year, then three years that each have their own personality. {year}
is {cyclePhrase}.
- Some opportunities mostly show their face in years like this one - same
  spot on the clock, every cycle.
- It's a tendency, not a guarantee - never forget that part.

### Screen 2: Let the Filter Find Them
Lead: Flip the {peLabel} checkbox above the table and it keeps only the years
that sit where {year} sits, surfacing the names built for a year like this.
- Short list comes back? That's normal. It's a stricter test.
- Empty on the Dow? Try the S&P 500.
- And yes - even these had years they lost.

### Screen 3: Flip On the {peLabel} Filter
Lead: Try it now.
- Click the {peLabel} checkbox above the table.
- Watch the list redraw to only the years that sit where {year} sits.
- Fewer rows is the point, not a bug.
- Click one and size it up like Day 4.

(In 2027 this whole day automatically reads PE+3 / "a pre-election year" /
"2027". Zero maintenance.)

---

## Day 6 — Keep the Good Ones, Catch the Window

### Screen 1: Found a Keeper? Save It   (portfolio named explicitly)
Lead: When the one on your chart clears your bar - won often, steady, plenty
of years behind it - don't let it scroll away. Tap the + above the chart and
it goes into your portfolio.
- Your portfolio is your shortlist. It holds every opportunity you save, and
  it sticks around after the trial ends.
- Saving isn't me telling you to buy. It's your shortlist, your call.

### Screen 2: Then Let the App Watch the Calendar   (Notify me, by name)
Lead: A seasonal opportunity only counts once its window actually opens.
That's what the Notify me bell above the chart is for.
- One click saves it to your Notifications portfolio and puts the window's
  open and close dates on your calendar.
- You get pinged the day the window opens - then forget about it until then.

### Screen 3: Save One, Bell One
Lead: Do both on one you like.
- Click a row to load an opportunity worth keeping onto the chart.
- Tap the + above the chart to save it to your portfolio.
- Hit Notify me so the window can't slip past you.
- Don't have a favorite yet? Save any solid one to practice.

---

## Day 7 — The Hundred-Year Window, Then the Hunt

### Screen 1: The Hundred-Year Window
Lead: Last lesson, and it's my favorite. There is one window on the S&P 500
that has come back, cycle after cycle, for the better part of a century.
- Wars, crashes, a dozen recessions, more than a dozen presidents - and this
  one window keeps showing up.
- Rare and steady - but still a habit, not a promise. It's had losing years,
  and you'll see them on the chart yourself.

### Screen 2: Now You Can Judge It Yourself
Lead: This is the whole week in one move: find it, read the window, count the
reds, check the numbers, save it. You've got all the tools now.
- % Profitable for how often. Sharpe for how rough the ride. The red years to
  keep you honest.
- And depth above everything - 90% across 20 years beats perfect across 5,
  almost every time.

### Screen 3: Go See It, Then Go Hunt
Lead: Run it yourself, then go find your own.
- Open the S&P 500 (SPX) index.
- Find the long window with the {peLabel} filter on.
- Read its red years on the bar chart, then its % Profitable and SR {statsAt}.
- Save it, hit Notify me - and then go hunt.

### Screen 4 (NEW): Before This Window Closes   (the trial close)
Lead: One more honest read, and this time it's about you: your 7 days of full
access end today.
- Explorer stays free forever - the Dow list, 10 years of depth, one saved
  opportunity, and Tara.
- If this week earned a spot in your routine, keep exactly what you used and
  nothing more. The button below reads your week and names the smallest plan
  that covers it.
- We won't point you at the big plan if your week says you don't need it.
  Same rule as the charts: the record decides.

[ Show me my week, measured ]   <- button, opens TrialConversionCard

---

## Mechanics that ship with the copy

1. **The closing screen rides the TRIAL clock, not the lesson counter.**
   Shown when getTrialState().daysRemaining <= 1. A user who signed up but
   first logged in on day 3 hits trial-end at lesson Day 5 - the closing
   screen appends to whatever lesson day they're on, so nobody's trial ends
   silently. TrialConversionCard's trigger gets the same fix (today it fires
   on lesson day >= 7).
2. **New fill tokens** {year} and {cyclePhrase} computed in LessonBox.fill()
   beside the existing {peLabel} switch (year % 4).
3. **Corrected device-aware stats strings** ({statsIntro}/{statsOpen}/{statsAt})
   as written under Day 3.
4. The "Show me my week, measured" button hands off to the existing
   TrialConversionCard (usage-summary-driven, already honest by design).
   No new pricing UI is invented.
5. Day 7 grows to 4 screens - the renderer already adapts (Day 1 has 4).
