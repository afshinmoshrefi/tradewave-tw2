# Proposed SMN Operator Amendment: Existing Git Adapter

Application candidate remains `32bd869c0ffdd6039145bcaee4223dd67fb533ff`. This is a proposed amendment to the deployment operator, not an application change and not production deployed. The frozen approved package under the original owner's `operator-policy` directory is untouched.

Production read-only checks on October 5 at 21:02-21:11UTC show no activation lock or active publishing service; controller, scheduler and newsletter locks are free. Dorothy's attempt to resume original owner `01a0fcf4-37f1-7d33-bced-ac46999fd9fa` returned `CloudThreadNotFoundError`. Dorothy then authorized evaluating a guarded takeover of the same action. Current verifier `01a10c07-0aa8-767f-84e3-04f9184b50da` can execute after the concrete operator amendment below is authorized; an old-owner acknowledgement is not the remaining blocker.

## Reproduced Blocker

The original operator invokes plain root Git in its archive verifier. On production, the releases are owned by `flask`; plain root Git exits 128 for dubious ownership. Existing production services avoid this through `/opt/smn-subscription/bin/git`, a root-owned 0755 adapter whose complete behavior is `exec /usr/bin/sudo -u flask /usr/bin/git "$@"`. Reading the installed release through that adapter succeeds. The approved continuity service template omits the adapter directory from its `PATH`, so the new scheduled phases would encounter the same failure. The secret file supplies no overriding Git configuration.

This exposed a gap in the previous offline qualification: it did not reproduce a Flask-owned repository under the actual root service path. This amendment exercises that case without changing global Git trust, credentials, permission policy, application source, or the existing adapter.

## Exact Amendment and Validation

New operator SHA256: **`56eb12dd53e6b5f7e1df1a9491b41ee30f6f8c67e0974f32aa367f44ebbe6fc3`**. Original operator: `35d1f7a4e478ea58e2d56087494c6784e5040ce55d1da741465b016f4e976329`.

1. Run both raw archive Git reads as `flask`, preserving all existing byte and CRLF-only equivalence checks.
2. Add exactly `/etc/systemd/system/smn-continuity@.service.d/10-release-git.conf` to managed snapshots, planned-file hashes, drift refusal and automatic rollback. Its sole setting prepends `/opt/smn-subscription/bin` to the existing service PATH.
3. Verify the existing adapter's exact bytes, root ownership, executable mode and absence of group/world write access at preflight; bind its metadata and recheck at finalize. Verify each new service's effective PATH before enabling timers. Preserve changed peer files and never modify the adapter.
4. Bind approval to this operator hash plus `approve_existing_git_adapter_dropin: true`. The original approval cannot silently authorize this amendment.

All **17 isolated Linux operator guard/failure tests pass**, including the original 12 cases and five new amendment cases. Real Flask-owned Git fixture reproduces the original root refusal, passes the amended archive check including non-UTF8 CRLF text, and rejects a changed application blob. These checks are self-verification by the takeover investigator, not a new independent reviewer. No systemd mutation, provider/model call, or email occurred in these tests. `qualification.json` binds the exact tested operator. `production-preflight.json` passes read-only and records nine managed files, including the currently absent new drop-in, plus unchanged publication/campaign state.

## Required Decision and Execution

Required authorization: use the exact amended operator above to deploy already-approved application 32bd869, including the single named managed drop-in and the same automatic rollback. Existing same-day snapshots and application approval remain valid; no new generation, newsletter resend, header patch, credentials or security changes are requested. The deployment-manager skill's exact-artifact rule prevents transferring the frozen operator's approval without this explicit amendment.

After approval, the current executor can copy the unchanged original package into a new root-owned operator directory, substitute only this qualified operator, refresh preflight, and populate `approval.template.json` with the same human authority plus the amendment fields. Use the original package's guarded `apply` and held-timer `finalize` command sequence with this operator. The application bundle/archive/proofs/screenshots/freshness checker remain the original qualified bytes. Recheck actual content, all effective service paths, successful real continuity ticks without new model work, preserved campaign/ledgers, and lock release.

Operational alerts still require the separate secure missing-credential handoff, observer configuration/installation and actual test delivery. Tomorrow's October 6 07:00 Eastern / 11:00 UTC genuine scheduled run remains pending. Header repair remains TW-BUG-0028 and is excluded. Shared updates use draft PR #14 only; the rejected direct-main write has not been retried.
