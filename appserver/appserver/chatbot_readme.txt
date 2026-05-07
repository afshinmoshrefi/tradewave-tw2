================================================================================
 TRADEWAVE CHATBOT — README
================================================================================
Last updated: Feb 2026

--------------------------------------------------------------------------------
 OVERVIEW
--------------------------------------------------------------------------------
The TradeWave chatbot is a context-aware AI assistant embedded in the desktop
UI. It knows about the currently loaded wave pattern, the opportunity table,
and the TradeWave interface. It uses Anthropic Claude via the Anthropic API.

Files involved:
  appserver:  chatbot.py              — Flask blueprint, route, prompt builder
              chatbot_knowledge.txt   — editable knowledge base (no code change needed)
              chatbot_readme.txt      — this file
  UI:         src/components/Chatbot.js       — React chatbot component
              src/components/DesktopLayout.js — mounts chatbot, resizable panel

--------------------------------------------------------------------------------
 CONFIGURATION (top of chatbot.py)
--------------------------------------------------------------------------------
  CHATBOT_MODEL — which Claude model to use:
    CLAUDE_HAIKU_45   = claude-haiku-4-5-20251001   cheap + fast   ~$1/MTok in
    CLAUDE_HAIKU_35   = claude-3-5-haiku-20241022   (NOT available on this key)
    CLAUDE_SONNET_46  = claude-sonnet-4-6            stronger       ~$3/MTok in
    CLAUDE_OPUS_46    = claude-opus-4-6              most capable   ~$15/MTok in

  CACHE_TTL — Anthropic prompt caching tier:
    '5m'  — $1.25/MTok to write. Cache resets on every hit. Good for active chat.
            This is the currently working option.
    '1h'  — $2.00/MTok to write. Cache survives 1hr of inactivity. Better for
            sporadic use. NOT YET ENABLED — the correct beta header string needs
            to be verified at docs.claude.com before implementing.

After changing either variable: sudo systemctl restart appserver

--------------------------------------------------------------------------------
 COST BREAKDOWN (Claude Haiku 4.5 pricing)
--------------------------------------------------------------------------------
  Base input tokens:      $1.00 / MTok
  5m cache write:         $1.25 / MTok  (first message of a session)
  1h cache write:         $2.00 / MTok  (first message of a session)
  Cache hits:             $0.10 / MTok  (every subsequent message — 10x cheaper)
  Output tokens:          $5.00 / MTok  (the bot's reply — keep answers short!)

  Example per message (knowledge base ~1,500 tokens, currently):
    First message (cache write):  ~0.2 cents
    Each subsequent message:      ~0.015 cents + output cost

  If knowledge base grows to 27,000 tokens (20,000 words):
    First message (1h write):     ~5.4 cents
    Each subsequent message:      ~0.27 cents + output cost

  Key insight: output tokens cost 5x more than input. The bullet-point
  response style instruction in the system prompt saves significant money.

--------------------------------------------------------------------------------
 HOW THE SYSTEM PROMPT WORKS
--------------------------------------------------------------------------------
Every message to the LLM includes:
  1. Static system prompt (CACHED):
     - Bot persona + response style rules
     - TradeWave UI layout description
     - Full content of chatbot_knowledge.txt
  2. Dynamic context (NOT cached, changes per message):
     - Currently loaded pattern: symbol, dates, direction, stats
     - Opportunity table: top 50 rows (date, symbol, days, direction, SR, AP)
  3. Conversation history: last 20 turns (user + assistant)
  4. Current user message

  NOTE: For caching to be maximally effective, the static portion must come
  FIRST in the prompt and be identical across all requests. Dynamic content
  comes after and is not cached. This is already implemented correctly.

  Future optimization: split into TWO cached blocks — one for the knowledge
  base (never changes) and one for the wave viewer stats (changes per pattern
  but stays constant within a session). Anthropic supports up to 4 cache blocks.

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
Keep it focused — the AI already knows general trading and finance concepts.
Target: under 3,000 words to keep token cost manageable.

--------------------------------------------------------------------------------
 FUTURE WORK — RATE LIMITING & QUOTAS
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
    Prevent abuse — e.g. max 5 messages per minute per user.
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
