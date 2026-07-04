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
//   {dateRange}  (Day 3) renders the live date-range label of the loaded pattern.
//   {statsIntro}/{statsOpen}/{statsAt} (Days 3/4/7) render DEVICE-AWARE directions to the
//                Wave Stats table: desktop = the middle carousel dot below the bar chart;
//                mobile portrait = swipe left to the Wave Stats slide. Filled in LessonBox.fill().
//   Voice: human, confident, honest, no advice, no em-dashes (use ' - ').
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
          "Now click the year selector at the top of the Opportunity Table - it shows 10 years.",
          "Select 15 years.",
          "Now you are looking at opportunities based on the last 15 years."
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
        "title": "Read the Date Range Above the Chart",
        "lead": "Load one onto the chart, then glance at the line right above it - that is the actual window, written out as real dates.",
        "bullets": [
          "The Opportunity Table gives you the start day and how many days the pattern runs.",
          "Above the bar chart that becomes a real date range - yours reads '{dateRange}' right now. Make a habit of glancing up to read it.",
          "Each bar is one year: what you'd have made or lost buying at the start of that range and selling at the end."
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
        "title": "Three Years Proves Nothing",
        "lead": "Watch out for the small sample. Up 3 years out of 3 looks flawless, but it's basically a coin flipped three times.",
        "bullets": [
          "Up 18 of 20 has been through far more weather - that's a pattern.",
          "More years tested, more you can trust it.",
          "And even the strong ones owe you an off year now and then."
        ],
        "pointer": ""
      },
      {
        "title": "Stress-Test the Years",
        "lead": "Let's push on one and see if it holds.",
        "bullets": [
          "Find the years buttons in the control bar above the chart - the exact numbers change with each pattern.",
          "It opens on 10.",
          "Click a higher one - now you're asking more of it.",
          "% Profitable still holds up? That one's solid."
        ],
        "pointer": ""
      }
    ]
  },
  {
    "day": 5,
    "theme": "Midterm Years Run Their Own Playbook",
    "tease": "midterm years run their own playbook",
    "screens": [
      {
        "title": "2026 Isn't Just Any Year",
        "lead": "Markets watch the election calendar, and it runs on a four-year clock. 2026 is a midterm year, and some opportunities mostly show their face in years like this.",
        "bullets": [
          "Same rhythm, every cycle.",
          "It's a tendency, not a guarantee - never forget that part."
        ],
        "pointer": ""
      },
      {
        "title": "Let the Filter Find Them",
        "lead": "Flip the {peLabel} checkbox and the table keeps only the midterm-type years, surfacing the names built for a year like this.",
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
          "Watch the list redraw to midterm years only.",
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
        "lead": "When the one on your chart clears your bar - won often, steady, plenty of years behind it - don't let it scroll away. Tap the + above the chart and it's yours.",
        "bullets": [
          "Your saved ones stick around after the trial ends.",
          "Saving isn't me telling you to buy. It's your shortlist, your call."
        ],
        "pointer": ""
      },
      {
        "title": "Don't Miss the Window",
        "lead": "A seasonal opportunity only counts once its window actually opens. So set a reminder on it and let the app watch the calendar for you.",
        "bullets": [
          "Find your saved one in the Opportunities Manager and set its reminder.",
          "It pings you the day the window opens - then forget about it until then."
        ],
        "pointer": ""
      },
      {
        "title": "Save One, Set a Reminder",
        "lead": "Do both on one you like.",
        "bullets": [
          "Click a row to load an opportunity worth keeping onto the chart.",
          "Tap the + above the chart to save it.",
          "Open the Opportunities Manager and set its reminder.",
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
        "title": "The Hundred-Year SPX Window",
        "lead": "Last one, and it's my favorite. There's a single window on the S&P 500 that has gone up in nearly every cycle for the better part of a century.",
        "bullets": [
          "Almost a hundred years of cycles, and this one keeps showing up.",
          "Rare and steady - but still a habit, not a promise. It's had losing years too, and you'll see them."
        ],
        "pointer": ""
      },
      {
        "title": "Now You Can Judge It Yourself",
        "lead": "This is the whole week in one move: find it, read the record, judge it, save it. You've got the tools now.",
        "bullets": [
          "% Profitable for how often. SR and the red years to keep you honest.",
          "Remember - 90% across 17 years beats a perfect 3 out of 3, almost every time."
        ],
        "pointer": ""
      },
      {
        "title": "Go See the SPX Window",
        "lead": "Go run it yourself, then go hunt.",
        "bullets": [
          "Open the S&P 500 (SPX) index.",
          "Find the midterm window with the {peLabel} filter.",
          "Read its red years on the bar chart, then its % Profitable and SR {statsAt}.",
          "Save it, set the bell - and then go find your own."
        ],
        "pointer": ""
      }
    ]
  }
];

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
