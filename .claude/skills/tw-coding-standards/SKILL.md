---
name: tw-coding-standards
description: TradeWave code and design conventions, plus design-decision discipline. Use when writing, designing, or reviewing TradeWave/SMN code, especially anything touching persistent state (redis keys, Postgres schema, file or serialization formats, identifiers) or naming - choices that are expensive to change once data exists. Operational hard rules live in /home/flask/CLAUDE.md and docs/TRADEWAVE_ECOSYSTEM.md; this complements them.
---

# TradeWave coding standards

A living list of code/design conventions and the lessons behind them. Add an entry
whenever a non-obvious decision turns out to matter. Format: the **rule**, then a one-line
**Why** naming the real incident.

## 1. Surface non-obvious design decisions before baking them in
When a task leaves a design choice unspecified - a storage-key scheme, a DB column or
type, a serialization format, an identifier, a naming convention, an API or return shape -
do NOT silently pick one and implement it when it is expensive to reverse (persistent
data, shared schemas, anything migrations or other components depend on). Either state the
choice and its trade-off in a sentence and confirm, or pick the conventional option and
call it out explicitly so it can be corrected. The user usually will not know to
pre-specify these; the burden is on us to raise them.

**Why:** the watchlist feature silently embedded the user-typed watchlist *name* into the
redis key (`user_watchlist_items_<id>_MY FAVORITE STOCKS`). It worked, so nobody chose it
on purpose - and it left lasting fragility (see #2). Flagging it at design time costs one
sentence; finding it later costs a migration of live data.

## 2. Storage keys are stable IDs, never free text
Never put user-controlled or free-text values (names, titles, anything containing spaces,
`_`, `*`, `?`, `[`, or unicode) INTO a storage key - a redis key, a filename, a path
segment. Key by a stable id (numeric, uuid, or a slug you generate and control), and keep
the human-readable name in the VALUE.

**Why:** free text in keys causes (1) shell/redis-cli quoting pain, (2) glob hazards
(`* ? [` are wildcards in redis `SCAN`/`KEYS`), (3) brittle parsing to recover id-vs-name
out of one string, (4) collision/injection against other key patterns. Redis keys are
binary-safe, so it "works" and stays hidden until it bites (e.g. migration tooling that
must regex the id back out).

## 3. Never raise ValidationError from flask-admin on_model_change without the _AdminAuth shim
flask-admin 2.1.0 has a bug: in `contrib/sqla/view.py` update_model/create_model/
delete_model, `session` is assigned AFTER `on_model_change`/`on_model_delete` runs, so the
library's own documented pattern (raising wtforms `ValidationError` from those hooks) crashes
the except-path `session.rollback()` with UnboundLocalError -> a 500 instead of the flashed
form error. `web/app.py:_AdminAuth` now shims all three methods (catch UnboundLocalError,
rollback, return False) - every admin view MUST keep inheriting `_AdminAuth`, and any guard
that should allow edits on legacy rows must check the sqlalchemy attribute HISTORY (fire on
the TRANSITION, not the resulting state).

**Why:** 2026-07-07 - editing just the NAME of an affiliate 500'd: the row was legacy
active-without-signature, the activation gate fired on state (not transition), and the
flask-admin bug turned the intended red form message into UnboundLocalError. Two bugs
stacked; both invisible until an operator touched a legacy row.
