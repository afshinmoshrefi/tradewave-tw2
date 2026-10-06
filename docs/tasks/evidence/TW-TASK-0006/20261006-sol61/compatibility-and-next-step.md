# SMN 6.1-Sol compatibility diagnosis and isolated qualification plan

Observed October 6, 2026. Review `SMN-SOL61-20261006`; requested by Dorothy
(`01a0f25f-c964-7675-91ca-caa44db7c0c4`). Status: diagnosis complete,
installation and further generation not performed. This extends the existing
draft experiment; it does not claim another owner's release scope.

## What the evidence establishes

The one explicitly approved XLK/medium subscription attempt returned HTTP 400
at `2026-10-06T12:28:24.796889Z`. One qualification CLI start occurred, with
zero completed model turns and no output or response model identity. The
allowance is consumed. The [native result](single-native-attempt.json) remains
unchanged. The failed job is sealed; its real dispatcher refuses it before
account probing or dispatch. [Terminal proof](terminal-seal-proof.json)
preserves the nonce and attempt receipt SHA-256
`df879009af8ffc70daa727477d615fb4cbc65f22204d504bc019156656c7c1e7`.

Read-only inspection of Dev's installed package and executable confirms
`@openai/codex` **0.155.0-alpha.16**, at
`/opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex`.
[Installed metadata](installed-cli-metadata.json) contains the actual version
result and captured invocation. The prior documented `model/list` request,
including hidden models with no remaining cursor, returned nine entries and
no 6.1-Sol. [Catalog](catalog.json). No generation occurred during these reads.
The wrapper package's lack of separate model JSON files says nothing about
model data embedded in its platform binary.

Official documentation names **`gpt-6.1-sol`**, including a non-interactive
`codex exec` example. It includes Pro in the launch rollout for the desktop
Codex client and CLI, while making availability conditional on rollout,
client, sign-in method and workspace. It does not support a general claim that
Pro excludes this model. [Models](https://learn.chatgpt.com/docs/models).
ChatGPT sign-in supplies subscription access; API-key sign-in is a separate
billed route. The saved ChatGPT route already passed allowance checks, so
changing credentials or using an API key is not indicated or authorized.
[Authentication](https://learn.chatgpt.com/docs/auth).

Official CLI **0.159.1**, released September 29, added 6.1-Sol to its bundled
catalog. Dev's installed alpha predates that catalog change.
[0.159.1 release](https://github.com/openai/codex/releases/tag/rust-v0.159.1).
The current stable release observed on October 6 is **0.160.1**, released
October 5. [0.160.1 release](https://github.com/openai/codex/releases/tag/rust-v0.160.1).

**Confirmed:** the installed client is outdated relative to documented
6.1-Sol support. **Inference:** its older client/catalog is a likely contributor
to the rejection. **Unknown:** whether upgrading alone restores access for
this particular saved account. The single 400 cannot distinguish that from
an account/client rollout restriction. No alternate supported spelling was
found, and no new model request was made to test one.

## Desktop/cloud selection and the SMN runner

Selecting a model for Dorothy's desktop or cloud task does not rewrite SMN's
immutable job manifest. This attempt explicitly passed `--model gpt-6.1-sol`,
`model_reasoning_effort="medium"`, `--ignore-user-config` and forced ChatGPT
authentication to the pinned Dev executable. UI availability, a requested
argument and a catalog entry each differ from a returned backend identity.
The attempt returned no such identity. Parent task model selection is not
evidence that this older headless runner can use the same model.

## Proposed next step, not executed

1. Have the existing owner authorize an **isolated Dev qualification install**
   of exact official `@openai/codex@0.160.1`, in a new task-owned prefix such as
   `/var/tmp/smn-codex-0.160.1-qualification-20261006`. Verify official package
   origin and published integrity, and record the artifact hash. No checksum
   was retrieved during this diagnosis; do not invent one or install a
   floating `latest`. Preserve the old CLI and service/runtime pointers.
2. Use the new executable's absolute path only for metadata: version/help,
   documented account/allowance reads and full hidden-inclusive `model/list`.
   Check that the saved route is ChatGPT and the exact model supports medium.
   Reuse existing native metadata probes after checking protocol compatibility;
   record package/version, catalog pagination and errors. Do not log tokens,
   copy credentials, reauthenticate or submit a fixture in this phase.
3. Stop if 6.1-Sol/medium is absent or the documented protocol fails. Preserve
   the sanitized evidence for the existing owner to investigate client/account
   rollout. Do not manufacture a catalog entry, use a paid API, rename a model
   or make an exploratory completion to work around the result.
4. If metadata succeeds, request a **new explicit one-call budget** for a new
   isolated XLK review job. The previous one-call approval is spent; do not
   reopen its sealed job or reset its nonce. Preserve the same input hashes,
   schema, no-tool rules, subscription route, timeout and single-start guard.
   Collect actual response identity/usage when exposed and score the original
   facts/numbers/instructions and rejection probes. No broad benchmark or
   Astra comparison is included in this plan.
5. A successful review would still leave writing, research, independent-review
   safety and publication recovery unqualified. Keep [SMN draft #4](https://github.com/afshinmoshrefi/SMN/pull/4)
   unmerged and unactivated. A permanent runner change, model migration or
   production deployment needs its own owner reconciliation and authorization.
   End qualification by leaving the candidate prefix unused; no runtime
   pointer changes are planned, so the old runner remains the rollback path.

## Supported older Sol option and quality limits

The installed catalog lists `gpt-6-sol` with medium effort, and the retained
October 6 XLK review succeeded with it. That is review evidence, not a
medium-effort writer qualification. The existing six-subject writing benchmark
used **xhigh**, with identical prompts and preserved TradeWave evidence:
Sol passed deterministic source/structural gates on **4/6** and its same-model
pipeline on **2/6**. It contained an AZO chronology wording error, MRK
chart/sample-placement ambiguity and AZO/QQQ source-budget failures. Different
reviewer models make those pipeline rates operational outcomes rather than
an unbiased model ranking. [TW-TASK-0007](../../../TW-TASK-0007.md).

Older Sol writing can therefore be offered as a separately scoped candidate
with these known limits and existing independent/source/numeric/visual gates.
It is not an automatic fallback or an approved production migration.

Daily release owner `01a0fcf4-37f1-7d33-bced-ac46999fd9fa` and schedule owner
`01a0fcf2-f893-74f0-b850-4105ab151511` retain their scopes. Dorothy owns weekday
checks and user updates. This diagnosis did not change production, send mail,
install a CLI or start a second model attempt. Existing quotation/budget,
continuity/watchdog and header work remains with its recorded owners.
