# Bug Memory

This is the shared, provider-neutral bug register. Read [how work is managed](../WORK_MANAGEMENT.md) before starting or handing off work. Use [the template](TEMPLATE.md) for new records.

As recorded September 15, 2026: **5 open bug groups, 4 fixes verified on dev.** Claude Code fixed TW-BUG-0001 and TW-BUG-0002 on dev (main `99bce08d`). Codex independently verified both fixes and Afshin confirmed they worked; evidence is linked in each record. The five open records have no implementation owner; all are P2. Recording these bugs does not authorize their repair.

| ID | Priority | Status | User-visible issue |
|---|---|---|---|
| [TW-BUG-0001](TW-BUG-0001.md) | P1 | verified on dev | Mobile Rotation Can Crash the Viewer |
| [TW-BUG-0002](TW-BUG-0002.md) | P1 | verified on dev | The Right Resize Edge Can Change the Duration Without a Drag |
| [TW-BUG-0003](TW-BUG-0003.md) | P2 | open | Starting on the Chart's Last Date Puts the Highlight on the Left |
| [TW-BUG-0004](TW-BUG-0004.md) | P2 | open | Jan-Dec Highlights the Whole Year for Some PE Selections |
| [TW-BUG-0005](TW-BUG-0005.md) | P2 | open | February 29 Breaks the Date and Data Display |
| [TW-BUG-0006](TW-BUG-0006.md) | P2 | open | Invalid Typed Dates Can Blank the Chart |
| [TW-BUG-0007](TW-BUG-0007.md) | P2 | open | A Failed Trend Request Leaves an Empty Placeholder |
| [TW-BUG-0008](TW-BUG-0008.md) | P1 | verified on dev | Retained category labels garble a replaced trend curve |
| [TW-BUG-0009](TW-BUG-0009.md) | P2 | verified on dev | In-range start changes recenter the rolling chart |
| [TW-BUG-0010](TW-BUG-0010.md) | P2 | verified on dev | SMN daily edition counts an unfinished engine observation; publication held |

| [TW-BUG-0011](TW-BUG-0011.md) | P2 | verified | SMN review homepage hides retained earlier articles |

| [TW-BUG-0012](TW-BUG-0012.md) | P3 | verified on dev | AI future-entry message incorrectly blames time length |

| [TW-BUG-0013](TW-BUG-0013.md) | P2 | open | LRCX 60-day AI checkpoint fails profile validation |

Status belongs in each record and this index; update both together. Preserve resolved records and reopen recurrences. Verification is environment-specific. See the evidence setup for limitations; the audit was not an exhaustive guarantee and production was not tested.

| [TW-BUG-0014](TW-BUG-0014.md) | P2 | fixed; Dev pending | SMN comparison disclosure assumes twenty observed years |
