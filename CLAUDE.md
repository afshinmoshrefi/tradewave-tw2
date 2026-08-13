# TradeWave - Codebase Instructions for Agents

## READ FIRST
**Before planning or doing ANY TradeWave task, read `docs/TRADEWAVE_ECOSYSTEM.md`.**
It is the single, code-verified map of the whole TW1 + TW2 ecosystem (architecture,
data flows, deploy, auth/billing, the TW1<->TW2 mapping, invariants, open gaps). It
exists so we stop guessing and re-deriving the system. If a memory note disagrees
with that doc, the doc wins. Deploy detail: `ops/OPERATIONS.md`. Cutover:
`ops/PROD_CUTOVER.md`.

**For ANY code edit, Git operation, multi-session handoff, integration, cleanup, release,
or deployment, also read FIRST:**
`.claude/skills/tw-git-release-workflow/SKILL.md` - every task uses a separate branch and
worktree; handoffs name pushed commit SHAs; releases promote tested commits, not dev files.

**For ANY deploy, promotion, release, rollback, environment-parity check, deployment
handoff, or deployment-readiness request, also read FIRST without waiting to be asked:**
`.claude/skills/tradewave-deployment-manager/SKILL.md` and `docs/RELEASE_PROCESS.md` - one
manager owns the release; approved dev behavior must be reproduced by a clean commit and
immutable artifact; staging and production receive that exact artifact; effective systemd
drop-ins, live process paths, contract checks, and rendered browser behavior are mandatory.

**For product / methodology / copy / onboarding / Tara work, also read FIRST:**
`docs/TRADEWAVE_METHODOLOGY_AND_FEATURES_KB.md` - what a "pattern" is, the MFE/MAE/TWA/TWR
metrics, the PE/100-Year cycle, the SCAN -> VALIDATE -> ORGANIZE -> ACT loop, and the two
personas. It is the product-knowledge SSOT (the ecosystem doc is the implementation SSOT);
do not re-derive the methodology from code each time.

**Keep it current (ENFORCED via the `tw-knowledge` skill):** at the END of any substantive
TradeWave/SMN task, run the `tw-knowledge` skill WITHOUT being asked. It captures + IMPROVES
the knowledge base so nothing is re-derived: implementation truth (architecture / a data flow /
a deploy step / an invariant / a path) updates `docs/TRADEWAVE_ECOSYSTEM.md` in the SAME commit;
working knowledge (decisions + why, project state, owner preferences, gotchas) updates the
correct EXISTING memory file in place (search first, never duplicate, delete stale). Re-deriving
a fact you could have recalled is a defect - fix it by writing it down.

## The 30-second mental model
The **appserver** is the data engine - the only component with the market data +
seasonal-pattern computation. Everything else (the React wave-viewer, the web tier,
every content generator, the SMN pipeline) is a CLIENT that queries it over HTTP and
must authenticate first. Content is generated to static HTML and served by nginx.
TW2 is the WordPress-removal rebuild of TW1: WorkOS + Stripe + Postgres + Flask
replace WP/UMP, keeping the React app and the appserver `/login` handshake.

## Hard rules (full list + reasons in the ecosystem doc §11)
- RELEASES ARE COMMITS: before any code/Git/handoff/integration/release/deploy work, follow
  `.claude/skills/tw-git-release-workflow/SKILL.md`. Use a dedicated branch + worktree per
  task, commit + push before handoff, and integrate in a clean release worktree. Never treat
  the arbitrary contents of `/home/flask` as the version to promote.
- ONE RELEASE MANAGER: on any deploy/release/parity request, automatically follow
  `.claude/skills/tradewave-deployment-manager/SKILL.md` and `docs/RELEASE_PROCESS.md`.
  Only that manager integrates, builds, activates dev, or authors promotion/rollback commands.
  Afshin or his designated human operator executes staging and production writes. A staging
  request never authorizes production. A verifier saying CLEAN never overrides active-runtime
  or browser evidence.
- SELF-MAINTAINING KNOWLEDGE: at the end of any substantive task, run the `tw-knowledge`
  skill unprompted (see "Keep it current" above) - capture + improve the ecosystem doc +
  memory, update existing files in place, never duplicate, never re-derive twice.
- NEVER touch live/staging/prod (or TW1 `.151`) directly with write commands -
  author commands; the operator runs them. Read-only inspection of `.151` is OK.
- Deploy is dev -> staging -> verify -> prod via `bash ops/deploy.sh {staging|prod}`.
  Staging is the prod gate; never dev->prod direct; never skip/drop staging.
- No em-dashes in TradeWave/SMN content (use ` - `); date-range labels use the
  en-dash via `tw_dateformat.py`.
- No secrets in chat - box-to-box only; diagnostics return classification, not values.
- `config.py` is env-agnostic (per-env values via `secrets.env`). Never hardcode;
  never `git checkout origin/main -- config.py` (causes box drift). Run box git as
  `sudo -u flask` (root-owned `.git` breaks the next pull).
- Billing/data invariants: Stripe webhook must ACK 200 for foreign customers;
  FREEZE legacy Stripe price cleanup; resource keys `'0'..'16'` are permanent IDs;
  reverse-trial gate (owner decision 2026-06-10): new signups get 7d full
  Strategist access (`users.reverse_trial_ends_at` + `effective_tier()` at
  token mint, tier never mutated), then level `'1'` Explorer = DJ30 only;
  roles live ONLY in `web/models.py:ROLES`.
- All TW2 hosts are Cloudflare tunnels - never convert prod to an A record.
- gunicorn does not auto-reload (restart after Python edits); deploy must
  `pip install -r requirements.txt`. React = one env-agnostic bundle, symlink-swap deploy.
  Build React ONLY via `npm run build` (it carries PUBLIC_URL=/app/) - never raw
  `react-scripts build` (2026-06-12: a raw build emitted root-relative asset paths
  and blanked the app; .env.production now pins PUBLIC_URL as a backstop).
- Appserver port is PER-ENV: `:5000` on dev ONLY, `:80` on staging/prod (CAP_NET_BIND_SERVICE).
  NEVER assume 5000 off dev. Local checks on staging/prod hit `http://127.0.0.1/...` (port 80).
  When unsure, read the live port off the box (`ss -tlnp`, the unit's `--bind`) - don't recall it.
