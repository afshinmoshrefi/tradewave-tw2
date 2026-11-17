#!/usr/bin/env python3
"""EVAL-ONLY overlay 'style': replace the 2-sentence cap with a complete-but-short answer rule."""
import sys
from pathlib import Path
p = Path(sys.argv[1]) / "appserver" / "appserver" / "chatbot.py"
t = p.read_text(encoding="utf-8")
old = ("A simple fact, definition, or view command is at most 2 sentences; a list is at most 5 one-liners.")
new = ("A view command is one short line. A fact, definition, how-to or troubleshooting answer is 2 to 5 "
       "short lines: the direct answer first, then EVERY fact in the matching knowledge-base section that "
       "bears on the question (where it is, the limit or plan, the caveat, how to undo it, what it is "
       "read alongside), each as one short line, then one next step. Completeness beats brevity for "
       "these: leaving out a relevant knowledge-base fact is a worse error than one extra line. A list "
       "is at most 5 one-liners unless the user asked for more.")
assert old in t
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("style patched")
