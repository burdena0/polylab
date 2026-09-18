"""Download a fresh immutable BTC dataset, pinned to a publisher revision."""
import hashlib, json, time
from pathlib import Path
from urllib.request import urlopen, Request
ROOT=Path(__file__).resolve().parents[1]
REPO='kachoio/polymarket-5-minute-crypto-up-down-markets'

def main():
    with urlopen('https://huggingface.co/api/datasets/'+REPO,timeout=20) as r: revision=json.load(r)['sha']
    dest=ROOT/'data'/'btc';dest.mkdir(exist_ok=True)
    records=[]
    for name in ['README.md','btc_markets.parquet','btc_ticks.parquet']:
        url=f'https://huggingface.co/datasets/{REPO}/resolve/{revision}/{name}'
        path=dest/name
        if not path.exists():
            size=0; start=time.monotonic()
            with urlopen(Request(url,headers={'User-Agent':'PolyLab/1.0'}),timeout=30) as r, path.with_suffix('.partial').open('wb') as f:
                while True:
                    block=r.read(1024*1024)
                    if not block: break
                    size+=len(block)
                    if size>230_000_000 or time.monotonic()-start>240: raise ValueError('Download budget exceeded')
                    f.write(block)
            path.with_suffix('.partial').replace(path)
        digest=hashlib.file_digest(path.open('rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else hashlib.sha256(path.read_bytes()).hexdigest()
        records.append(dict(file=name,url=url,sha256=digest,bytes=path.stat().st_size))
        print(name, path.stat().st_size, flush=True)
    (dest/'receipt.json').write_text(json.dumps(dict(source='https://huggingface.co/datasets/'+REPO,revision=revision,retrieved_at=time.time(),files=records),indent=2))

if __name__=='__main__':main()
