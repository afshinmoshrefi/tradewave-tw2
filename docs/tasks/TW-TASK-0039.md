# TW-TASK-0039: Affiliate program - close every gap with commercial tools, plus a partner help assistant

- Status: in-progress
- Priority: P2
- First observed / last updated: 2026-11-24
- Executor/session/claim time: Claude Code (cloud session), 2026-11-24
- Authorization: Afshin, 2026-11-24 (project thread "Add affiliate promotions and renewal commissions"): "I don't want any gaps - let's do everything that's necessary" plus the chatbot request below. Builds on TW-TASK-0038 (branch claude/affiliate-v2-20261124, PR #19). Staging and production excluded.

## Goal

Match or beat Rewardful / FirstPromoter / PartnerStack on running the program, and add a help assistant only a logged-in partner can see.

## Scope (three work packages)

### A. Help assistant + growing knowledge base
1. Chat panel inside the partner portal (every page, logged-in active/paused/unsigned affiliates only; never public; never for non-affiliates).
2. Answers ONLY from: the partner guide, the agreement (v2 body + that partner's Exhibit A terms), an admin-curated FAQ/knowledge base, and that partner's own numbers (read-only, via existing dashboard/service functions). Never another partner's data, never customer identities (portal rule: counts only).
3. Uses the Anthropic API from the web tier (`config.anthropic_token`; model configurable, default `claude-sonnet-5-5`). Grounded answers; it must say "I don't know" rather than guess, especially on money, tax and legal questions.
4. When it can't answer: tells the partner it has asked the TradeWave team, creates an escalation record, and emails the owner (config `AFFILIATE_SUPPORT_EMAIL`, default help@tradewave.ai) with the question, partner code, chat context and a one-click signed link to an admin answer page.
5. Owner answers either on the admin page OR by replying to the email (Resend inbound webhook; token in the reply-to address so the reply maps to the escalation; verify the webhook signature; strip quoted text). Inbound is optional: if not configured, the link path works alone.
6. On answer: the partner sees the answer in the chat (and gets an email), and the answer becomes a knowledge-base entry (question, answer, source=escalation) that future answers use. Admin can edit, generalise (remove partner-specific details) or retire entries; an entry from an escalation starts as "partner-specific" until the admin marks it general, OR the model proposes a generalised version the admin approves in one click.
7. Rate limits per partner, conversation log retention, prompt-injection safety (KB and partner text are data), no secrets in prompts, no em-dashes in replies.

### B. Partner lifecycle + communication
1. Public partner application page (`/partners/apply`, linked from /join and the site footer): name, email, website/channels, audience size, how they will promote, country, agree to program policies. Spam protection (honeypot + rate limit). Applicant gets a confirmation email; owner gets a notification.
2. Admin Applications view: approve (creates the affiliate with default v2 terms, picks/edits a code, emails the signing link in one click) or reject (optional reason email). Duplicate detection by email.
3. Messaging: admin composes a message to one partner or a group (all, active, paused, unsigned, by terms version, inactive for N days, has customers / none). Preview recipient count, send via Resend, log every send, show messages in a portal "Messages" inbox (unread badge).
4. Automatic emails (each toggleable by the partner in Settings, except legally required ones): signed/welcome, first click, new paying customer (no customer identity), monthly statement ready, payout sent, activity warnings at 60/30/7 days before renewal commissions stop, renewals lapsed, renewals resumed, new company sale started (with their tracked link), discount change confirmed. Daily cron job, idempotent (one send per event per partner), logged.
5. Unsubscribe / preferences link in every non-required email.

### C. Operations + growth tools
1. Secure tax-form upload in the portal (W-9 / W-8BEN / W-8BEN-E PDF): size/type checks, encrypted at rest (Fernet key from secrets.env `TW2_TAX_FORM_KEY`, refuse upload if unset), admin-only download with audit log, partner sees status (received / accepted / rejected with reason). Admin marks accepted, which satisfies the existing "tax form on file" gate.
2. Per-link stats: partners create named sub-links (`?code=ANNE&sub=youtube`); clicks / signups / paid / earned per sub-link and per campaign on the Links page. Attribution stores the sub id; never changes who earns.
3. Bulk payouts: from the Payout Ledger, export a PayPal Payouts CSV and a Wise batch CSV for selected payable rows (no automatic money movement); after the owner pays, import/paste the batch result or mark rows paid in bulk with references.
4. Creative library: admin uploads banners, logos, email/social copy (per campaign or evergreen); partners copy or download from Promote, with their tracked link filled in.
5. AI operations summary: a monthly job (after month close) that previews what is owed, flags anomalies (big refunds, held lines, missing tax forms, below-minimum carries, partners close to the activity deadline), and emails the owner one summary with links. It never marks anything paid.

## Out of scope
- Listing the program on third-party marketplaces (owner action, not code).
- Automatic money movement.

## Owner actions needed later
- Resend inbound email set up (DNS) for reply-by-email; the answer link works without it.
- `TW2_TAX_FORM_KEY` and `AFFILIATE_SUPPORT_EMAIL` in secrets.env.

## Evidence
Filled in at integration.

### Package A (help assistant) - built 2026-11-24, branch claude/affiliate-help-assistant-20261124
- Code: `web/affiliate_help.py`, `web/affiliate_help_models.py`, `web/affiliate_help_admin.py`, `web/affiliate_portal/help_routes.py`, `web/affiliate_portal/templates/aff_help_widget.html`; migration `a9c1e5f7b3d2_affiliate_help_assistant.py` (down_revision b4d7e1f2a3c5; needs a merge revision with packages B and C).
- Tests: `tests/test_affiliate_help.py` (70); affiliate + promo suite 489 passed, 1 skipped. Anthropic client mocked; no live model call was made.
- Screenshots: project files `affiliate/gap-closure/` (`help-*` and `admin-*`, desktop and phone).
- Not done: dev activation, live model check, Resend inbound DNS.
