"""Read public strategy descriptions as data; never execute downloaded code."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import urlopen, Request
from concurrent.futures import ThreadPoolExecutor
import json, re, time, hashlib

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.polyresearchrobotics.com'

class Page(HTMLParser):
    def __init__(self, raw):
        super().__init__(); self.links=[]; self.text=[]; self.href=None; self.label=[]; self.skip=0
        self.feed(raw)
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip += 1
        if tag == 'a': self.href=dict(attrs).get('href'); self.label=[]
        if tag in ('h1','h2','h3','li','p'): self.text.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag=='a' and self.href:
            self.links.append((self.href, ''.join(self.label).strip())); self.href=None
        if tag in ('h1','h2','h3','li','p'): self.text.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)
            if self.href: self.label.append(data)

def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'PolyLab Research/1.0'}),timeout=20) as r:
        raw=r.read(4_000_001)
    if len(raw)>4_000_000: raise ValueError('Source too large')
    return raw

def main():
    out=ROOT/'data'/'sources'; out.mkdir(parents=True,exist_ok=True)
    raw=fetch(BASE+'/strategies'); (out/'strategies.html').write_bytes(raw)
    page=Page(raw.decode()); links={}
    for href,name in page.links:
        if href.startswith('/strategies/') and href != '/strategies/resources' and name: links.setdefault(href,name)
    def get(item):
        href,name=item; slug=href.rsplit('/',1)[-1]; dest=out/(slug+'.html')
        try:
            raw=dest.read_bytes() if dest.exists() else fetch(BASE+href)
            dest.write_bytes(raw); p=Page(raw.decode()); text='\n'.join(s.strip() for s in ''.join(p.text).splitlines() if s.strip())
            category=next((c for c in ['Arbitrage','Market Making','Signal-Driven','Quantitative','Specialist','Structural'] if c in text[:1200]),'Other')
            description=text.split('What you need to run it')[0].rsplit(name,1)[-1].strip()
            requirements=text.split('What you need to run it')[-1].split('Where this applies')[0].strip().splitlines() if 'What you need to run it' in text else []
            return dict(id=slug,name=name,category=category,url=BASE+href,description=description,requirements=requirements,source_sha256=hashlib.sha256(raw).hexdigest(),retrieved_at=time.time())
        except Exception as exc: return dict(id=slug,name=name,url=BASE+href,error=type(exc).__name__)
    with ThreadPoolExecutor(max_workers=6) as pool: rows=list(pool.map(get,links.items()))
    (ROOT/'data'/'catalog.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    guide=fetch(BASE+'/guide/how-to-build-a-polymarket-trading-bot'); (out/'guide.html').write_bytes(guide)
    (out/'guide.txt').write_text(''.join(Page(guide.decode()).text),encoding='utf-8')
    print(json.dumps({'strategies':len(rows),'errors':sum('error' in r for r in rows)}))

if __name__=='__main__': main()
