"""Cross-process pacing and cooldown for the one US public gateway."""
import sqlite3,time
from pathlib import Path
from contextlib import contextmanager

class CoolingDown(Exception):
    def __init__(self,seconds):self.seconds=seconds

@contextmanager
def connection(root):
    path=Path(root)/'data/us-transport.sqlite';path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS gate (id INTEGER PRIMARY KEY, next_at REAL NOT NULL, cooldown_until REAL NOT NULL)')
    db.execute('INSERT OR IGNORE INTO gate VALUES (1,0,0)');db.commit()
    try:
        with db:yield db
    finally:db.close()

def reserve(root,now=None):
    now=time.time() if now is None else now
    with connection(root) as db:
        db.execute('BEGIN IMMEDIATE');next_at,cooldown=db.execute('SELECT next_at,cooldown_until FROM gate WHERE id=1').fetchone()
        if cooldown>now:raise CoolingDown(cooldown-now)
        target=max(now,next_at);db.execute('UPDATE gate SET next_at=? WHERE id=1',(target+3,));return target-now

def cooldown(root,seconds,now=None):
    now=time.time() if now is None else now
    with connection(root) as db:
        db.execute('BEGIN IMMEDIATE');db.execute('UPDATE gate SET cooldown_until=MAX(cooldown_until,?) WHERE id=1',(now+seconds,))

def check(root):
    with connection(root) as db:until=db.execute('SELECT cooldown_until FROM gate WHERE id=1').fetchone()[0]
    if until>time.time():raise CoolingDown(until-time.time())
