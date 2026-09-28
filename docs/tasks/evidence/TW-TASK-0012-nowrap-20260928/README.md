# Desktop single-row toolbar verification

The PNGs and JSON receipts use final artifact 79fcba0b / main.7fb35429.js and
real dev HLT data. toolbar-40.png is the narrowest desktop splitter position;
toolbar-24.726.png reproduces approximately the original failing width.
Root independently checked the original native-110% Chrome session; the task
record contains its exact measurements and temporary viewport setup.

On the dev box, run as flask:

    LIVE=1 node docs/tasks/evidence/TW-TASK-0012-nowrap-20260928/verify-toolbar.js

This uses the documented dev-only capture shell and live nginx/API/assets. It
changes only the isolated browser's local settings and chart controls. Without
LIVE it uses the immutable recorded artifact for comparison. No tokens or shell
HTML are written to evidence. The script outputs captures under
/tmp/toolbar-nowrap-final. Native mobile/off layouts were compared separately.
