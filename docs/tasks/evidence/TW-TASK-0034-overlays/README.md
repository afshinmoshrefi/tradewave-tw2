# TW-TASK-0034 eval-only overlays

These scripts are evidence, not product code. Each one patches a PRIVATE copy of the round-3 tree (`origin/claude/tara-quality-round3-20261117` at `2e6a5a63`) that `tools/tara_eval/private_instance.py --from-tree` then serves on its own port. They were never applied to a tracked source tree.

| script | lever | measured result (see `../TW-TASK-0034-haiku80-plan.md`) |
|---|---|---|
| `patch.py <tree> shapes` | question-type answer shapes, no-retraction rule, language rule | no helpful lift; retraction phrases 14 of 39 to 0 |
| `patch.py <tree> shapes repair` | one self-check call after the tool loop | +3 points inside the noise, +73% cost |
| `patch.py <tree> shapes detrewrite` | a deterministic route's reply becomes an engine draft that Haiku rewrites | 42.7% to 62.4% helpful on 117 route questions |
| `patch2.py <tree>` | replaces the two-sentence cap with a completeness rule | no lift, concise pass down |
| `patch3.py <tree>` | six worked examples in the cached prefix | +5.8 points on tuned questions, not repeated on held-out |

The route-rewrite overlay is a measurement device. A product version needs the tool loop, a number guard and a length rule (plan section 5.3).
