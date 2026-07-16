"""Extract UX-relevant text signals + button states from a rendered console page."""
import sys, re
from html.parser import HTMLParser

class T(HTMLParser):
    def __init__(self): super().__init__(); self.p=[]; self.sk=0
    def handle_starttag(self,t,a):
        if t in ("script","style"): self.sk+=1
    def handle_endtag(self,t):
        if t in ("script","style") and self.sk: self.sk-=1
    def handle_data(self,d):
        if not self.sk and d.strip(): self.p.append(d.strip())

KW=["plan","tier","trial","includ","subscribe","current","free","upgrade","cancel",
    "activat","navigator","strategist","analyst","download","banner","reach","limit",
    "manage","portal","switch","default","coming soon","key","found"]

def main(path):
    html=open(path,encoding="utf-8",errors="replace").read()
    p=T(); p.feed(html)
    print("=== "+path.split('/')[-1]+" ===")
    seen=set()
    for t in p.p:
        low=t.lower()
        if any(k in low for k in KW) and len(t)>3 and t not in seen:
            seen.add(t); print("  |",t[:220])
    btns=re.findall(r'<button([^>]*)>(.*?)</button>', html, re.S)
    for attrs,inner in btns:
        txt=re.sub(r'<[^>]+>','',inner).strip()
        dis=" [DISABLED]" if "disabled" in attrs else ""
        print("  BTN:",repr(txt)+dis)
    # em-dash check on visible text
    vis="\n".join(p.p)
    if "—" in vis: print("  !! EM-DASH present in visible copy")
    print()

for a in sys.argv[1:]: main(a)
