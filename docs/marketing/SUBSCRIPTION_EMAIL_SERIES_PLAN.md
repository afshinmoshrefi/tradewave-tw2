# Post-Subscription Email Series - Plan (not yet built)

Status: DESIGNED, PAUSED (2026-06-28). Awaiting the in-app 7-day lesson rework before
building MailerLite automations. Produced by 3 expert agents (lifecycle / product+methodology
/ retention) -> synthesis -> adversarial QA (caught + fixed 2 capability errors).

## Design principle
The in-app **LessonBox is the teacher** (generic methodology, 7 days, 3 screens/day on a
generic ticker). The **email is the nudge** that does what the app can't: pull users back on
days they don't log in, make them FEEL the one capability THEIR tier just unlocked over the
tier below (the value-realization "aha" that justifies the price), and carry the historical
PROOF that makes opening the app worth it. Every email names ONE action a lower tier literally
cannot click, rides alongside a specific in-app day (a P.S. names that day so they reinforce,
never compete), and never re-teaches a screen the LessonBox owns. Email count SCALES with how
much new surface the tier bought.

Cadence: send_day = days after landing on the new level. Day 0 within the first hour, then +2
days (0/2/4/6/8), one send/day max, morning window so the email opens the loop and the in-app
lesson closes it the same day.

## The series, by tier

### Explorer (free) - 2 emails (lightest touch; over-mailing a $0 user churns the cheapest growth asset)
| Day | Subject | One action |
|--|--|--|
| 0 | Welcome to TradeWave - Your Free Dow 30 Seat Is Live | Open the Dow 30 table, click the top row, read its year-by-year record. (Trend Score only - NOT AI scoring, NOT custom start date; those are Navigator) |
| 2 | The Same Hunt, on NASDAQ and the S&P 500 | Open the public scorecard, find a recent win on a NASDAQ/S&P name the free Dow table can't reach (honest Navigator itch) |

### Trial (7-day reverse trial) - 3 emails (conversion arc; all end BEFORE the in-app Day-7 conversion card so they never double-pitch)
| Day | Subject | One action |
|--|--|--|
| 0 | Your 7 Days of Full Access Are On - Score Your First Stock | Type a stock you own, score it vs ~98 years, read the verdict |
| 2 | Try a Market You Won't Have on Free | Load a non-Dow stock, toggle PE+2 to watch it re-slice for 2026 |
| 4 | Save the One You'd Want to Keep | Save your best setup + reminder (persists even if you drop to free); tier decision handed to the in-app D7 card |

### Navigator ($19/mo, $14/mo yearly) - 3 emails (entry-paid catch rung + conversion target)
| Day | Subject | One action |
|--|--|--|
| 0 | Welcome to Navigator - Three Markets, AI-Scored | Switch the table to NASDAQ 100 / S&P 500, load the top window, read its AI score |
| 2 | Filter the Table to the Cycle We're In | Turn on the election-cycle FILTER on the table; watch it re-sort to the cycle year |
| 4 | Build Your Three-Market Watchlist | Add best finds across 3 markets to your watchlist (25), save the strongest with a reminder (soft Analyst pointer + annual) |

### Analyst ($47/mo, $33/mo yearly) - 4 emails (full US universe + research/human layer)
| Day | Subject | One action |
|--|--|--|
| 0 | Welcome to Analyst - The Whole Market Is Open | Type any stock/ETF NOT in Dow/NASDAQ/S&P, load it with a custom start date |
| 2 | Read Win Rate With Sharpe, on Your Own Names | Compare % Profitable vs Sharpe vs TWR on your ticker; ask Tara what's signal vs small sample |
| 4 | Your Seat at This Week's Live Q&A Is Open | Calendar the weekly Q&A, read one SMN article (activates the human/content layer = churn/refund killer) |
| 6 | Set Up Your Pattern Library | Organize saved patterns into themed portfolios + reminders (annual + ONE honest, info-only Strategist note) |

### Strategist ($129/mo, $99/mo yearly) - 5 emails (pure value-realization/retention; NEVER dangles a higher tier - there isn't one)
| Day | Subject | One action |
|--|--|--|
| 0 | Welcome to Strategist - All Fifteen Markets, Open | Open a previously-locked class (future/forex/bond/crypto), load its top setup |
| 2 | Spot the Four-Year Cycle on Any Pattern You Own | Re-slice any pattern to its 4-year-cycle years; see if the edge sharpens or disappears |
| 4 | Hunt Where the Calendar Cycles Are Cleanest | Run a scan in futures/commodities, load the cleanest cycle window |
| 6 | Bring Your Hardest Setup to the Strategy Zoom | Calendar the weekly strategy Zoom, bring one real cross-asset / 4-year-cycle setup |
| 8 | Build a Portfolio That Works in Any Market | Build one diversified book (2+ asset classes, 2+ timeframes), saved with reminders (quiet annual save) |

## Branching / suppression (for the build)
- **Upgrade** (not fresh signup): do NOT run the full new-tier series - fire only a single
  "What's New in [Tier]" reframed email 1, then drop into that tier's later emails. Never re-onboard basics.
- **Trial -> convert**: exit Trial, enter the bought tier's series at email 2 (skip the redundant welcome).
- **Trial -> non-convert**: drop into the Explorer series gracefully (saved work intact), never a guilt sequence.
- **Downgrade/cancel**: exit the paid series immediately.
- **Activation-bridge / Tara-entry users** (report->signup): already have a "My Stocks" watchlist + the
  ACTIVATION_BRIDGE loss-frame automation; tag them so email 1 says "your stocks are already loaded - open them";
  if they enter a PAID tier, do NOT also run the trial/report loss-frame (the paid series replaces it).
- **CTA suppression**: skip an email's CTA if the user already did that action in-app (MailerLite condition on
  tracked events e.g. has_saved_a_pattern / has_used_pe_filter / has_scored); jump to the next unsent step.

## Hard rules honored
- Capabilities verified against the home page + config.py TIER_FEATURES (2026-06-28). Explorer has Trend Score
  but NO AI/ML scoring and NO custom start date (both are Navigator's headline unlocks). If the designed
  ML-on-DJ30 flip ships (see FREE_PAID_STRATEGY_RESEARCH.md), update grounding + confirm live BEFORE any
  Explorer email claims AI.
- Prices quoted ONLY from live Stripe numbers above (never the stale config/home fallbacks).
- Voice: AP Title Case subjects, no terminal period, no em-dash (use ' - '); past-tense historical frequency
  stated confidently as fact, never a forecast; never "buy this" (score it / validate it / save it / watch it);
  no third-party / competitor name-drops.

## Build prerequisites (open)
- Sender from-name + a real monitored reply-to (Analyst/Strategist include email/premium support, so it must be real).
- Per-tier MailerLite group + the wiring that adds a subscriber to the right group on subscription
  (trigger = subscriber_joins_group). The 3 existing enabled automations (Top 10 Welcome / New Pro /
  New Institutional) already use join-group; confirm how membership is set today and SUPPRESS the legacy
  generic welcome for anyone entering a tier automation (group-membership exclusion).
- Scope decision pending: build all 5 series, paid 3 only, or paid 3 + trial.

Full source: workflow run wf_c102388a-343.
