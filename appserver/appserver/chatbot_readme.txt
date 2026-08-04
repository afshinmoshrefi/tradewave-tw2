================================================================================
 TRADEWAVE CHATBOT - README
================================================================================
Last updated: August 4, 2026

--------------------------------------------------------------------------------
 OVERVIEW
--------------------------------------------------------------------------------
The TradeWave chatbot is a context-aware AI assistant embedded in the desktop
UI. It knows about the currently loaded wave pattern, the opportunity table,
and the TradeWave interface. Verified questions are answered by a deterministic
planner. Every other turn starts on GPT-5.6 Luna in dev, staging, and production.
Haiku 4.5 is a runtime fallback only after a classified OpenAI failure.

Files involved:
  appserver:  chatbot.py - Flask blueprint, route, prompt builder
              tara_prompt_context.py - KB/topic and row-context segmentation
              tara_answer_planner.py - verified screen/bar/pattern-analysis answers
              AI_tools_appserver.py - Anthropic system-block cache handling
              openai_tools_appserver.py - OpenAI Responses API + cache translation
              tara_model_router.py - release-owned primary provider selection
              tara_runtime_policy.py - tracked primary and fallback model policy
              tara_release_fingerprint.py - nonsecret release parity fingerprint
              tara_gateway.py - shared gateway tools + provider-specific loops
              chatbot_knowledge.txt - editable knowledge base (no code change needed)
              chatbot_readme.txt - this file
  UI:         src/components/Chatbot.js - React chatbot component
              src/components/DesktopLayout.js - mounts chatbot, resizable panel

--------------------------------------------------------------------------------
 MODEL CONFIGURATION
--------------------------------------------------------------------------------
  CHATBOT_MODEL - which Claude model to use:
    CLAUDE_HAIKU_45   = claude-haiku-4-5-20251001   cheap + fast   ~$1/MTok in
    CLAUDE_HAIKU_35   = claude-3-5-haiku-20241022   (NOT available on this key)
    CLAUDE_SONNET_46  = claude-sonnet-4-6            stronger       ~$3/MTok in
    CLAUDE_OPUS_46    = claude-opus-4-6              most capable   ~$15/MTok in

  CACHE_TTL - Anthropic prompt caching tier:
    '5m' - $1.25/MTok to write. Cache resets on every hit. Good for active chat.
            This is the currently working option.
    '1h' - $2.00/MTok to write. Cache survives 1hr of inactivity. Better for
            sporadic use. Supported by AI_tools_appserver.py, but not the default.

  OPENAI_CHATBOT_MODEL = gpt-5.6-luna. The Responses request fixes:
    reasoning.effort=low, text.verbosity=low, store=false, max output=2,048.

  The tracked Tara policy is identical in every environment:
    primary:  OpenAI gpt-5.6-luna
    fallback: Anthropic claude-haiku-4-5-20251001
    TARA_OPENAI_CANARY_PERCENT is retired. There are no percentage buckets,
    user buckets, or environment-specific primary defaults. Missing OPENAI_KEY
    is a deployment/configuration failure and does not silently force Haiku.

After changing a tracked model or cache setting:
  sudo systemctl restart tradewave-appserver

The tracked API-gateway unit is PartOf the appserver unit, so this restart also
reloads the gateway's in-memory SERVICE_API_KEY and cached service JWT. Its
ExecStartPost login canary fails activation if gateway -> appserver authentication
is broken. Do not treat the gateway's shallow /healthz response alone as proof that
live Tara reads work.

--------------------------------------------------------------------------------
 COST BREAKDOWN (re-check provider pages before budgeting)
--------------------------------------------------------------------------------
  Base input tokens:      $1.00 / MTok
  5m cache write:         $1.25 / MTok  (first message of a session)
  1h cache write:         $2.00 / MTok  (first message of a session)
  Cache hits:             $0.10 / MTok  (every subsequent message - 10x cheaper)
  Output tokens:          $5.00 / MTok  (the bot's reply - keep answers short!)

  GPT-5.6 Luna primary (August 1, 2026 published pricing):
  Base input tokens:      $0.20 / MTok
  Explicit cache write:   $0.25 / MTok  (1.25x base input)
  Cache hits:             $0.02 / MTok
  Output tokens:          $1.20 / MTok

  Prompt-size regression measurement (July 31, 2026; characters, not tokens):
    Old representative prompt:                 117K-121K chars
    Segmented representative prompt:            31K-34K chars
    Reduction:                                  approximately 72%-74%

  Luna is materially cheaper per token, but model policy remains a product and
  quality decision. Review real Tara replies, fallback rate, latency, tool
  accuracy, and cache usage before changing the tracked release policy.

--------------------------------------------------------------------------------
 HOW THE SYSTEM PROMPT WORKS
--------------------------------------------------------------------------------
Every message to the LLM includes:
  1. Stable system prefix (CACHED at its own breakpoint):
     - Bot persona + response style rules
     - TradeWave UI layout description
     - Live-tool behavior contract
  2. Topic-selected product knowledge (NOT cached; changes by question):
     - chatbot_knowledge.txt is parsed by its ## headings at startup
     - At most 3 relevant complete sections / 16,000 characters are selected
     - The full knowledge base is never appended to every request
  3. Dynamic context (NOT cached, changes per message):
     - Loaded pattern identity + allowlisted derived statistics
     - Selected/full-history normalized curves reduced client-side to direction-only
       labels over the loaded window (supports/against/flat/unknown); curves stay local
     - Year-by-year rows only for specific-year/bar/outlier/MFE/MAE questions
     - Opportunity rows only for table/list/ranking/screening questions, max 12
     - React sends only allowlisted derived stats; the server rechecks the same boundary
     - Raw prices, price levels, volumes, and nested earnings history are excluded
  4. Conversation history: last 20 turns (user + assistant)
  5. Current user message

  The cache breakpoint is at the END of the stable prefix. Anthropic uses its
  cache_control block; OpenAI uses an explicit Responses cache breakpoint plus
  one of four stable routing keys. A symbol, screen, or selected KB topic can
  change without invalidating the large stable prefix.
  Each provider response logs input/cache-create/cache-read/output token counts
  server-side so cache effectiveness can be checked without logging prompt text.
  Live dev verification showed an 8,854-token stable-prefix cache creation on the
  first request and an 8,854-token cache read with zero creation on the next.

  High-confidence screen overview, bar semantics, direction rationale, exact-year,
  per-year MFE/MAE (including contextual "max/min" plain language), table-rank,
  advice-safe, and loaded-pattern analysis requests bypass the provider.
  Direct show/hide MFE/MAE commands also bypass the provider and return validated
  show_mfe/show_mae set_view actions; the React client toggles the chart overlays
  without opening the MFE/MAE education popup.
  The planner matches depth to intent: broad analysis explains driver, robustness,
  recency, failure profile, trend/TWR/event context, and curve agreement; focused
  follow-ups return only their relevant diagnostics. PE-cycle samples are labeled as
  cycle observations, not consecutive years. Advice wording gets evidence plus the
  disclaimer, never a trade verdict.

  Both provider tool loops call the same _execute_tara_tool implementation. Tool
  result trimming, OppList4 screen matching, ViewSpec validation, and reply truth
  guards therefore stay provider-independent. Any Luna failure retries the turn
  through Haiku before a user-visible error is returned. chatbot_questions.log
  records the actual provider/fallback label for canary review.

--------------------------------------------------------------------------------
 UPDATING THE KNOWLEDGE BASE
--------------------------------------------------------------------------------
Edit: /home/flask/appserver/appserver/chatbot_knowledge.txt
  - Lines starting with # are comments (ignored)
  - ## Section headings for organization
  - Plain text, no special formatting needed
  - Restart appserver after editing: sudo systemctl restart appserver

The knowledge base teaches the bot TradeWave-specific things the AI doesn't
know (UI layout, terminology, what makes a good pattern, user workflow, etc.).
Keep it focused - the AI already knows general trading and finance concepts.
Target: under 3,000 words to keep token cost manageable.

--------------------------------------------------------------------------------
 FUTURE WORK - RATE LIMITING & QUOTAS
--------------------------------------------------------------------------------
This needs to be implemented before opening the chatbot to all users.

[ ] PER-USER DAILY QUOTA
    Track messages per user per day in a database table:
      chatbot_usage (user_id, date, message_count, input_tokens, output_tokens)
    Enforce a daily cap (e.g. 20 messages/day for free users, 100 for paid).
    Return a friendly error when quota is exceeded.

[ ] PER-USER MONTHLY QUOTA
    Same table, aggregate by month. Useful for billing.
    Monthly cap could be: free=50, basic=500, premium=unlimited.

[ ] TOKEN-BASED QUOTA (more accurate than message count)
    Message count is a rough proxy. Token count is the real cost driver.
    Log input_tokens + output_tokens from the Anthropic API response headers:
      response.json()['usage']['input_tokens']
      response.json()['usage']['output_tokens']
      response.json()['usage'].get('cache_read_input_tokens', 0)
      response.json()['usage'].get('cache_creation_input_tokens', 0)
    Cap users at a monthly token budget (e.g. 500,000 tokens/month).

[ ] RATE LIMITING (per minute/hour)
    Prevent abuse - e.g. max 5 messages per minute per user.
    Can use Redis with a sliding window counter, or a simple DB timestamp check.

[ ] USER LEVEL GATING
    The token is already passed to the chatbot route. Decode it to get user_id
    and user_level, then apply different quotas:
      Level 0 (not logged in): no access
      Level 1 (free):          10 messages/day
      Level 2 (basic):         50 messages/day
      Level 3+ (premium):      unlimited or very high cap

[ ] CHARGING FOR CHATBOT SEPARATELY
    Option A: include chatbot in a higher subscription tier
    Option B: usage-based add-on (e.g. $2/month for 500 messages)
    Option C: credits system (user buys a pack of N messages)
    The token usage data collected above feeds directly into billing.

[ ] UI FEEDBACK
    Show the user their remaining quota in the chatbot panel.
    Show a soft warning at 80% usage ("You have 4 messages remaining today").
    Show a hard stop with upgrade prompt when quota is hit.

--------------------------------------------------------------------------------
 ARCHITECTURE NOTES
--------------------------------------------------------------------------------
- The chatbot is desktop-only (no mobile support currently).
- showChatbotIcon in Common.js controls whether the toggle icon appears.
  Set to true to show, false to hide from all users.
- The chatbot panel is resizable via a drag handle between the opp table and
  the chatbot. Default split: 70% opp table / 30% chatbot.
- Conversation history is stored in React state (lost on page refresh).
  Future: persist history in localStorage or server-side per session.
- The 'clear' command typed in the input clears the chat history.

================================================================================
