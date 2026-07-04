// =====================================================================
// onboardingLessons.js - the 7-day onboarding deck (human voice).
//
// Pure data. LessonBox.js renders it. Day 1 Screen 1 introduces what the daily
// lessons ARE; the real per-subscription WELCOME lives in its own dialog
// (SubscriptionWelcomeModal.js), not here.
// SHAPE: LESSONS = [ { day, theme, tease, chatbotLesson?, desktopOnly?,
//                      screens: [ N x { title, lead, bullets, pointer } ] } ]
//   Most days have 3 screens; Day 1 has 4. The renderer adapts to screens.length.
//   desktopOnly  dropped from the deck on mobile; LessonBox indexes by POSITION.
//   {peLabel}    (Day 5) renders live as PE+2 (the CheckBox above the table).
//   {year}       (Day 5, "Onboarding Lessons v2") renders the live current year,
//                e.g. "2026". Computed in LessonBox.fill() beside {peLabel}.
//   {cyclePhrase}(Day 5, "Onboarding Lessons v2") renders the live election-cycle
//                phrase for {year} (article included): "an election year" (PE) |
//                "a post-election year" (PE+1) | "a midterm year" (PE+2) |
//                "a pre-election year" (PE+3). Same year % 4 switch as {peLabel},
//                so it is always in sync with the button the lesson points at -
//                this makes all of Day 5 year-agnostic, forever.
//   {dateRange}  (Day 3) renders the live date-range label of the loaded pattern.
//   {statsIntro}/{statsOpen}/{statsAt} (Days 3/4/7) render DEVICE-AWARE directions to the
//                Wave Stats table: desktop = the middle of the 3-dot carousel above the
//                bottom chart, on its right side; mobile portrait = swipe left to the
//                Wave Stats slide. Filled in LessonBox.fill().
//   Voice: human, confident, honest, no advice, no em-dashes (use ' - ').
//
// TRIAL_CLOSE_SCREEN ("Onboarding Lessons v2", 2026-07-04): NOT part of the static
// LESSONS array - it is a single extra screen exported on its own and appended
// DYNAMICALLY by LessonBox at render time to whichever lesson day the user's trial
// clock actually closes on (getTrialState().onTrial && daysRemaining <= 1), not
// hardcoded to Day 7 screen 4. A late starter whose trial ends on lesson Day 5
// gets it appended to Day 5 instead, so nobody's trial ends silently. It carries a
// `cta` field ({label, action}) that LessonBox renders as a prominent button; the
// "conversion-card" action hands off to the existing usage-measured
// TrialConversionCard. Never appended for a non-trial (paying) user.
// =====================================================================

export const LESSONS = [
  {
    "day": 1,
    "theme": "How These Lessons Work",
    "tease": "how these daily lessons work - start here",
    "screens": [
      {
        "title": "About These Daily Lessons",
        "lead": "This little box is your guide. One short lesson a day for a week, each one teaching you a single thing and then handing you the wheel.",
        "bullets": [
          "Quick to read, then you go try it yourself.",
          "By the end you'll read the data on your own.",
          "Ready? Let's take the first look together."
        ],
        "pointer": ""
      },
      {
        "title": "Your Job This Week",
        "lead": "Simple goal: find a few good opportunities worth a closer look. That's the whole game.",
        "bullets": [
          "We dig up the names with a real seasonal habit.",
          "Ranked by what actually happened, strongest on top.",
          "All week you're on full access - every market, every year of history. Use it hard.",
          "We point. You decide what's worth a look."
        ],
        "pointer": ""
      },
      {
        "title": "Read the Opportunity Table",
        "lead": "It is already open, over on the left. Let's read it together.",
        "bullets": [
          "Look left - the Opportunity Table is already open.",
          "It lists today's strongest opportunities, best on top.",
          "Click any row to load that one and take a look.",
          "Want another market? Use the picker at the top - try the Dow."
        ],
        "pointer": ""
      },
      {
        "title": "Choose How Many Years You're Seeing",
        "lead": "You are looking at seasonal opportunities based on the last 10 years by default.",
        "bullets": [
          "Click the year selector at the top of the Opportunity Table - it opens on 10 years.",
          "Select 15.",
          "Same market, deeper history - a longer test of every name on the list. Depth is a theme we'll come back to."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 2,
    "theme": "Meet Tara, Your Analyst",
    "tease": "meet Tara, who actually read the data for you",
    "chatbotLesson": true,
    "desktopOnly": true,
    "screens": [
      {
        "title": "Meet Tara, Your Analyst",
        "lead": "See the chat icon down in the bottom-left? That's Tara. Think of her as the friend who actually read the data so you don't have to squint at it.",
        "bullets": [
          "Click an opportunity and ask her about it in plain English.",
          "She works off the real record, nothing made up.",
          "She'll never tell you to buy. That part stays yours."
        ],
        "pointer": ""
      },
      {
        "title": "What One Row Is Telling You",
        "lead": "Every row is one security over one window of the year. SR stands for Sharpe Ratio, it's a technical finance term showing profit consistency year to year.",
        "bullets": [
          "Higher means year to year profit has been more consistent.",
          "Just remember, the historical opportunities are probabilities - there is no guarantee of it repeating."
        ],
        "pointer": ""
      },
      {
        "title": "Ask Tara About the Top Row",
        "lead": "Your turn.",
        "bullets": [
          "Click the top row.",
          "Ask her: how strong is this window historically? Show me the win rate and Sharpe.",
          "See what her analysis is based on - the historical performance."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 3,
    "theme": "See the Whole Track Record",
    "tease": "see an opportunity's whole track record",
    "screens": [
      {
        "title": "Read the Date Window Above the Chart",
        "lead": "Load one onto the chart, then find the small bordered date box in the control bar right above it - that is the whole trade, written as dates.",
        "bullets": [
          "Yours reads '{dateRange}' right now - that's month-day to month-day.",
          "First date is the buy, second is the sell. That exact window is what everything on this screen is measuring.",
          "Each bar below is one year: what that window returned if you bought the first date and sold the second."
        ],
        "pointer": ""
      },
      {
        "title": "Green Is Up, Red Is Down",
        "lead": "It's a scoreboard, and we don't fudge it. Green years went up, red years went down, and we leave the red right where it is.",
        "bullets": [
          "Count the green. Count the red. Both belong to the record.",
          "Seeing the losses is how you trust the wins."
        ],
        "pointer": ""
      },
      {
        "title": "Open One and Really Look",
        "lead": "Go read one for yourself.",
        "bullets": [
          "Click any row to pull up its chart.",
          "Count the green years, then count the red.",
          "{statsIntro}",
          "Find Percent Profitable there - even the high numbers had a few rough years behind them."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 4,
    "theme": "Tell the Solid Ones Apart",
    "tease": "tell the solid ones from the lucky ones",
    "screens": [
      {
        "title": "Win Rate Isn't the Whole Story",
        "lead": "Here's where you start to size one up properly. {statsOpen} - and read two numbers. % Profitable tells you how often it finished up. Sharpe Ratio tells you how rough the ride was getting there.",
        "bullets": [
          "Sharpe Ratio is the difference between a steady climb and a white-knuckle one.",
          "The ones you want win often AND don't put you through it.",
          "Steady beats lucky."
        ],
        "pointer": ""
      },
      {
        "title": "A Short Streak Is Still a Short Streak",
        "lead": "Every list here opens with 10 years of history behind it, and you can ask for a lot more. Here's why you should: a perfect run over a few years can be luck. A strong run over twenty years is a habit.",
        "bullets": [
          "Twenty years has been through crashes, rate hikes, elections and panics - and the window still worked. That's weather a short streak has never seen.",
          "So 90% profitable across 20 years beats 100% across 5, almost every time.",
          "And even the strong ones owe you an off year now and then."
        ],
        "pointer": ""
      },
      {
        "title": "Stress-Test the Years",
        "lead": "Let's push on one and see if it holds.",
        "bullets": [
          "Open the year selector in the control bar above the chart - it opens on 10.",
          "The menu only offers as many years as the stock actually has. A young stock might top out at 6 or 8 - that's not an error, that's its whole life so far. Shorter record, higher bar.",
          "Pick the biggest number it offers - now you're asking everything of it.",
          "% Profitable still holds at full depth? That one's solid."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 5,
    "theme": "The Market's Four-Year Clock",
    "tease": "the market's four-year clock, and where this year sits",
    "screens": [
      {
        "title": "Where {year} Sits on the Clock",
        "lead": "Markets watch the election calendar, and it runs on a four-year clock: election year, then three years that each have their own personality. {year} is {cyclePhrase}.",
        "bullets": [
          "Some opportunities mostly show their face in years like this one - same spot on the clock, every cycle.",
          "It's a tendency, not a guarantee - never forget that part."
        ],
        "pointer": ""
      },
      {
        "title": "Let the Filter Find Them",
        "lead": "Flip the {peLabel} checkbox above the table and it keeps only the years that sit where {year} sits, surfacing the names built for a year like this.",
        "bullets": [
          "Short list comes back? That's normal. It's a stricter test.",
          "Empty on the Dow? Try the S&P 500.",
          "And yes - even these had years they lost."
        ],
        "pointer": ""
      },
      {
        "title": "Flip On the {peLabel} Filter",
        "lead": "Try it now.",
        "bullets": [
          "Click the {peLabel} checkbox above the table.",
          "Watch the list redraw to only the years that sit where {year} sits.",
          "Fewer rows is the point, not a bug.",
          "Click one and size it up like Day 4."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 6,
    "theme": "Keep the Good Ones, Catch the Window",
    "tease": "keep the good ones, catch the window",
    "screens": [
      {
        "title": "Found a Keeper? Save It",
        "lead": "When the one on your chart clears your bar - won often, steady, plenty of years behind it - don't let it scroll away. Tap the + above the chart and it goes into your portfolio.",
        "bullets": [
          "Your portfolio is your shortlist. It holds every opportunity you save, and it sticks around after the trial ends.",
          "Saving isn't me telling you to buy. It's your shortlist, your call."
        ],
        "pointer": ""
      },
      {
        "title": "Then Let the App Watch the Calendar",
        "lead": "A seasonal opportunity only counts once its window actually opens. That's what the Notify me bell above the chart is for.",
        "bullets": [
          "One click saves it to your Notifications portfolio and puts the window's open and close dates on your calendar.",
          "You get pinged the day the window opens - then forget about it until then."
        ],
        "pointer": ""
      },
      {
        "title": "Save One, Bell One",
        "lead": "Do both on one you like.",
        "bullets": [
          "Click a row to load an opportunity worth keeping onto the chart.",
          "Tap the + above the chart to save it to your portfolio.",
          "Hit Notify me so the window can't slip past you.",
          "Don't have a favorite yet? Save any solid one to practice."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 7,
    "theme": "The Hundred-Year Window, Then the Hunt",
    "tease": "the hundred-year window - go see it yourself",
    "screens": [
      {
        "title": "The Hundred-Year Window",
        "lead": "Last lesson, and it's my favorite. There is one window on the S&P 500 that has come back, cycle after cycle, for the better part of a century.",
        "bullets": [
          "Wars, crashes, a dozen recessions, more than a dozen presidents - and this one window keeps showing up.",
          "Rare and steady - but still a habit, not a promise. It's had losing years, and you'll see them on the chart yourself."
        ],
        "pointer": ""
      },
      {
        "title": "Now You Can Judge It Yourself",
        "lead": "This is the whole week in one move: find it, read the window, count the reds, check the numbers, save it. You've got all the tools now.",
        "bullets": [
          "% Profitable for how often. Sharpe for how rough the ride. The red years to keep you honest.",
          "And depth above everything - 90% across 20 years beats perfect across 5, almost every time."
        ],
        "pointer": ""
      },
      {
        "title": "Go See It, Then Go Hunt",
        "lead": "Run it yourself, then go find your own.",
        "bullets": [
          "Open the S&P 500 (SPX) index.",
          "Find the long window with the {peLabel} filter on.",
          "Read its red years on the bar chart, then its % Profitable and SR {statsAt}.",
          "Save it, hit Notify me - and then go hunt."
        ],
        "pointer": ""
      }
    ]
  }
];

// ---------------------------------------------------------------------
// TRIAL_CLOSE_SCREEN ("Onboarding Lessons v2") - the closing screen tied to the
// TRIAL clock, not the lesson counter. Appended dynamically by LessonBox to
// whatever lesson day the user is on when getTrialState().onTrial &&
// daysRemaining <= 1 - see the file header + LessonBox.js for the mechanics.
// `cta.action`: 'conversion-card' -> LessonBox dispatches window CustomEvent
// 'tw-open-conversion-card' (App.js opens the existing TrialConversionCard).
// ---------------------------------------------------------------------
export const TRIAL_CLOSE_SCREEN = {
  "title": "Before This Window Closes",
  "lead": "One more honest read, and this time it's about you: your 7 days of full access end today.",
  "bullets": [
    "Explorer stays free forever - the Dow list, 10 years of depth, one saved opportunity, and Tara.",
    "If this week earned a spot in your routine, keep exactly what you used and nothing more. The button below reads your week and names the smallest plan that covers it.",
    "We won't point you at the big plan if your week says you don't need it. Same rule as the charts: the record decides."
  ],
  "pointer": "",
  "cta": { "label": "Show me my week, measured", "action": "conversion-card" }
};

export const TOTAL_LESSON_DAYS = LESSONS.length;
export function getLesson(day) {
  const i = (parseInt(day, 10) || 1) - 1;
  if (i < 0) return LESSONS[0];
  if (i >= LESSONS.length) return LESSONS[LESSONS.length - 1];
  return LESSONS[i];
}
export function getScreens(day) {
  const l = getLesson(day);
  return (l && Array.isArray(l.screens)) ? l.screens : [];
}
