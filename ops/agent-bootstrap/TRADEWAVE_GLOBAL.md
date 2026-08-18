# TradeWave global agent bootstrap

Apply these rules only when the repository remote or workspace identifies TradeWave TW2.

1. Before planning or editing, fetch current `origin/main` using the repository's required Git user.
2. Read `AGENTS.md`, `CLAUDE.md`, `docs/RELEASE_PROCESS.md`, `.claude/skills/tw-git-release-workflow/SKILL.md`, and `.claude/skills/tradewave-deployment-manager/SKILL.md` from current `origin/main`. If an old worktree lacks them, use `git show origin/main:<path>`; do not declare them missing until the current remote ref is checked.
3. Start each task in a separate clean branch/worktree based on current `origin/main`. Never develop in the operational `/home/flask` checkout or an unrelated dirty worktree.
4. A substantive application/runtime change is complete only when its exact combined commit is running and live-verified on dev, freshly fetched `origin/main` equals that SHA, and the artifact is staging-ready. Exceptions require an explicit `local only` or `do not deploy` instruction, or an analysis/documentation-only request.
5. Claude and Codex may develop concurrently in separate worktrees. Only one recorded manager at a time may perform final integration and dev activation. Acquire the dev coordination lock before final integration, incorporate every completed change, and keep the lock through activation, browser/runtime verification, and the final remote-ref identity check.
6. Branches, commits, pushes, worktrees, handoffs, locks, builds, and routine conflict resolution are agent responsibilities. Do not ask Afshin to manage them, and do not say fixed/done/live while work exists only in a private worktree.
7. `Deploy to staging` authorizes the complete gated staging workflow for the exact dev SHA. Production always requires a later explicit request and its snapshot gate.
