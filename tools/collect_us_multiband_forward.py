"""Bounded registered forward paper run with receipts and no order endpoints."""
import json,time,sys,os,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from polylab.research import ROOT
from polylab.us_marketdata import get,normalize_book,RateLimited
from polylab.us_multiband_forward import plan,evaluate

def save(path,obj):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(obj,indent=2),encoding='utf-8');tmp.replace(path)

def read(path):return json.loads(path.read_text())

def once(root):
    cfg=read(root/'registration.json');now=time.time();state=read(root/'state.json') if (root/'state.json').exists() else dict(phase='waiting_signal',created_at=now)
    for name,sha in read(root/'code-freeze.json')['sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen input changed '+name)
    if sum(p.stat().st_size for p in root.rglob('*.json'))>cfg['max_archive_bytes']:raise ValueError('Data cap')
    if state['phase'] in ['complete','expired','interrupted_capture']:return state
    phase=state['phase'];state.update(pid=os.getpid(),checked_at=now);save(root/'state.json',state)
    if phase in ['capturing_signal','capturing_entry']:
        state.update(phase='interrupted_capture',reason='Interrupted phase is not replayed');save(root/'state.json',state);return state
    if now>=cfg['stop_at']:
        state.update(phase='expired',reason='Registered stop; any open basis remains unresolved');save(root/'state.json',state);return state
    def books(slugs,directory,deadline):
        result={};errors=[];directory.mkdir(exist_ok=True)
        for slug in slugs:
            if time.time()>=deadline:errors.append(dict(slug=slug,error='Capture deadline'));break
            try:
                response,receipt=get('/v1/markets/'+slug+'/book');book=normalize_book(response,slug)
                doc=dict(response=response,receipt=receipt,book=book);save(directory/(slug+'.json'),doc);result[slug]=doc
            except Exception as exc:
                errors.append(dict(slug=slug,error=str(exc)[:200]))
                if isinstance(exc,RateLimited):break
        return result,errors
    if phase=='waiting_signal':
        if now<cfg['signal_start']:return state
        if now>=cfg['target']:
            state.update(phase='expired',reason='Missed signal window, no backfilled opportunities');save(root/'state.json',state);return state
        state['phase']='capturing_signal';save(root/'state.json',state)
        slugs=[r['slug'] for g in cfg['groups'] for r in g['rules']]
        _,errors=books(slugs,root/'signal',cfg['target'])
        state.update(phase='waiting_decision',signal_errors=errors);save(root/'state.json',state);return state
    if phase=='waiting_decision':
        if now<cfg['target']:return state
        if now>cfg['target']+30:
            state.update(phase='expired',reason='Decision was not recorded within 30 seconds');save(root/'state.json',state);return state
        signals={p.stem:read(p) for p in (root/'signal').glob('*.json')}
        planned=plan(cfg['groups'],cfg,signals);planned['recorded_at']=time.time();save(root/'plan.json',planned)
        state['phase']='waiting_entry';save(root/'state.json',state);return state
    if phase=='waiting_entry':
        if now<cfg['target']+cfg['entry_delay_seconds']:return state
        if now>=cfg['entry_deadline']:
            state.update(phase='expired',reason='Missed delayed entry window');save(root/'state.json',state);return state
        planned=read(root/'plan.json');state['phase']='capturing_entry';save(root/'state.json',state)
        slugs=sorted({o['slug'] for a in planned['arms'] for o in a['selected']})
        entries,errors=books(slugs,root/'entry',cfg['entry_deadline'])
        result=evaluate(planned,entries,{},cfg);save(root/'entry-result.json',result);save(root/'latest-result.json',result)
        state.update(phase='waiting_settlement' if any(r['positions'] for r in result['results']) else 'complete',entry_errors=errors)
        save(root/'state.json',state);return state
    if phase=='waiting_settlement':
        if now<max(cfg['settlement_not_before'],state.get('next_settlement_check',0)):return state
        planned=read(root/'plan.json');entries={p.stem:read(p) for p in (root/'entry').glob('*.json')};directory=root/'settlement';directory.mkdir(exist_ok=True)
        slugs=sorted({row['slug'] for r in read(root/'entry-result.json')['results'] for row in r['ledger'] if row['kind']=='buy'})
        errors=[]
        for slug in slugs:
            if (directory/(slug+'.json')).exists():continue
            try:
                response,receipt=get('/v1/markets/'+slug+'/settlement')
                if response.get('slug')!=slug:raise ValueError('Settlement identity')
                from polylab.us_accounting import number
                if not 0<=number(response['settlement'])<=1:raise ValueError('Settlement range')
                save(directory/(slug+'.json'),dict(response=response,receipt=receipt))
            except Exception as exc:
                errors.append(dict(slug=slug,error=str(exc)[:200]))
                if isinstance(exc,RateLimited):break
        payouts={p.stem:read(p) for p in directory.glob('*.json')};result=evaluate(planned,entries,payouts,cfg);save(root/'latest-result.json',result)
        state.update(phase='complete' if not any(r['positions'] for r in result['results']) else 'waiting_settlement',next_settlement_check=time.time()+900,settlement_errors=errors);save(root/'state.json',state)
    return state

def main():
    import msvcrt
    root=Path(sys.argv[1]).resolve()
    with (root/'collector.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):lock.write(b'0');lock.flush()
        lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:print('duplicate_noop',flush=True);return
        last=None
        try:
            while True:
                state=once(root)
                if state['phase']!=last:print(json.dumps(state),flush=True);last=state['phase']
                if state['phase'] in ['complete','expired','interrupted_capture']:break
                time.sleep(10)
        except Exception as exc:
            save(root/('failure-'+str(time.time_ns())+'.json'),dict(error=str(exc),at=time.time(),pid=os.getpid()));raise
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':main()
