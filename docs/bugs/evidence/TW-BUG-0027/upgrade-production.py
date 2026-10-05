"""Operator-only October 5 repair upgrade. Requires explicit release/snapshot approval."""
import fcntl,hashlib,json,os,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
OLD='d6e2b6fd59b15e2a601248df00073c078db24df4'
SHA='08f871493a639a504b49794d78315d223b87a870'
BASE=Path('/opt/smn-subscription');CURRENT=BASE/'current';REPO=BASE/'releases'/SHA
STATE=Path('/var/lib/tradewave/release-state')
LOCK=STATE/'smn-production-activation.lock'
ACTIVATION=Path('/etc/SMN/subscription-primary.json')
FILES=[ACTIVATION,*[Path('/etc/systemd/system')/(n+'.service') for n in ('smn-subscription','smn-weekday-newsletter')]]
TIMERS=['smn-subscription.timer','smn-weekday-newsletter.timer']
PYTHON='/home/flask/venv/bin/python'
def run(*args):return subprocess.check_output(args,text=True).strip()
def git(repo,*args):return run('sudo','-u','flask','git','-C',str(repo),*args)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,data):
    tmp=p.with_name(p.name+'.oct5-new');tmp.write_text(data)
    if p.exists():
        st=p.stat();os.chown(tmp,st.st_uid,st.st_gid);shutil.copystat(p,tmp)
    os.replace(tmp,p)
def pointer(target):
    tmp=CURRENT.with_name('current.oct5-new');tmp.symlink_to(target);os.replace(tmp,CURRENT)
def guard_restore(record,r):
    for i,p in enumerate(FILES):
        path=str(p)
        if digest(record/str(i))!=r['before'][path]:raise ValueError('Backup changed '+path+'; inspect before rollback')
        if digest(p)!=r['after'].get(path,r['before'][path]):raise ValueError('Peer changed '+path+'; inspect before rollback')
    if CURRENT.resolve()!=REPO and os.readlink(CURRENT)!=r['previous_pointer']:
        raise ValueError('Current pointer changed; inspect before rollback')
def restore(record,r):
    guard_restore(record,r)
    for i,p in enumerate(FILES):shutil.copy2(record/str(i),p)
    pointer(r['previous_pointer'])
    run('systemctl','daemon-reload')
    for p,expected in r['before'].items():assert digest(p)==expected
    r['status']='rolled_back';write(record/'receipt.json',json.dumps(r,indent=2))
    for t in r['active_timers']:run('systemctl','start',t)
def main():
    if len(sys.argv)!=4:raise SystemExit('usage: upgrade-production.py activate APPROVAL.json BUNDLE | rollback RECEIPT_DIR unused')
    action=sys.argv[1]
    if '209.182.216.112' not in run('hostname','-I').split():raise ValueError('Production SMN host required')
    if action=='rollback':
        record=Path(sys.argv[2]).resolve()
        if record.parent!=STATE or not record.name.startswith('smn-oct5-repair-'):raise ValueError('Unexpected rollback record')
        controller=Path('/var/lib/tradewave/smn-daily/subscription-primary/controller.lock').open('a')
        locked=False
        try:
            fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
            LOCK.mkdir();locked=True
            (LOCK/'owner.json').write_text(json.dumps({'task':'TW-BUG-0027','pid':os.getpid(),'action':'rollback'}))
            r=json.loads((record/'receipt.json').read_text())
            if r['source_commit']!=SHA:raise ValueError('Wrong rollback release')
            guard_restore(record,r)
            for t in TIMERS:run('systemctl','stop',t)
            for n in ('smn-subscription.service','smn-weekday-newsletter.service'):run('systemctl','stop',n)
            restore(record,r);print(json.dumps(r));return
        finally:
            if locked:
                (LOCK/'owner.json').unlink(missing_ok=True);LOCK.rmdir()
            controller.close()
    if action!='activate':raise ValueError('Unknown action')
    approval=json.loads(Path(sys.argv[2]).read_text());bundle=Path(sys.argv[3]).resolve()
    today=datetime.now(timezone.utc).date().isoformat()
    if (approval.get('date')!=today or approval.get('source_commit')!=SHA or
        approval.get('production_web_snapshot') is not True or approval.get('production_app_snapshot') is not True or
        approval.get('execute_production_repair') is not True or not approval.get('approved_by')):
        raise ValueError('Exact release approval and TODAY web/app snapshots required')
    manifest=json.loads(bundle.with_name('release.json').read_text())
    if manifest['source_commit']!=SHA or manifest['bundle_sha256']!=digest(bundle):raise ValueError('Bundle changed')
    if CURRENT.resolve()!=BASE/'releases'/OLD or json.loads(ACTIVATION.read_text())['source_commit']!=OLD:
        raise ValueError('Production no longer matches inspected baseline')
    for n in ('smn-subscription.service','smn-weekday-newsletter.service'):
        if subprocess.run(['systemctl','is-active','--quiet',n]).returncode==0:raise ValueError('Wait for active '+n)
    for p in FILES[1:]:
        if p.read_text().count(str(BASE/'releases'/OLD))!=2:raise ValueError('Effective unit drift: '+str(p))
    record=STATE/('smn-oct5-repair-'+SHA[:12]+'-'+today)
    if record.exists():raise ValueError('Prior transaction exists; inspect its receipt')
    controller=Path('/var/lib/tradewave/smn-daily/subscription-primary/controller.lock').open('a')
    locked=False;changed=False;r=None
    try:
        fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
        LOCK.mkdir();locked=True
        (LOCK/'owner.json').write_text(json.dumps({'task':'TW-BUG-0027','pid':os.getpid(),'source_commit':SHA}))
        record.mkdir(mode=0o700)
        r={'source_commit':SHA,'status':'prepared','previous_pointer':os.readlink(CURRENT),
           'active_timers':[t for t in TIMERS if subprocess.run(['systemctl','is-active','--quiet',t]).returncode==0],
           'before':{str(p):digest(p) for p in FILES},'after':{},'approval':approval}
        for i,p in enumerate(FILES):shutil.copy2(p,record/str(i))
        write(record/'receipt.json',json.dumps(r,indent=2))
        for t in TIMERS:run('systemctl','stop',t)
        git(CURRENT,'fetch',str(bundle),'codex/smn-oct5-production-repair')
        if not REPO.exists():git(CURRENT,'worktree','add','--detach',str(REPO),SHA)
        assert git(REPO,'rev-parse','HEAD')==SHA and not git(REPO,'status','--porcelain','--untracked-files=no')
        smoke="import sys;sys.path.insert(0,'.');from smn_runtime_assets import preflight;preflight();import publish_article;import article_hero_image;assert '/"+SHA+"/' in article_hero_image.__file__;print('native publisher imports verified')"
        run('systemd-run','--quiet','--wait','--pipe','--collect','--property=Type=exec',
            '--property=EnvironmentFile=/etc/tradewave/secrets.env','--property=WorkingDirectory='+str(REPO/'blog'),
            '--setenv=PYTHONDONTWRITEBYTECODE=1','--setenv=PYTHONPATH=/home/flask',PYTHON,'-c',smoke)
        changed=True;pointer(REPO)
        for p in FILES:
            if p==ACTIVATION:
                config=json.loads(p.read_text());config.update(source_commit=SHA,record=str(record));text=json.dumps(config,indent=2)+'\n'
            else:text=p.read_text().replace(str(BASE/'releases'/OLD),str(REPO))
            write(p,text);r['after'][str(p)]=digest(p);write(record/'receipt.json',json.dumps(r,indent=2))
        run('systemctl','daemon-reload')
        for n in ('smn-subscription.service','smn-weekday-newsletter.service'):
            assert run('systemctl','show',n,'-p','WorkingDirectory','--value')==str(REPO/'blog')
        assert json.loads(ACTIVATION.read_text())['source_commit']==SHA and CURRENT.resolve()==REPO
        r['status']='activated_code_only';write(record/'receipt.json',json.dumps(r,indent=2))
        print(json.dumps(r))
    except BaseException:
        if changed:restore(record,r)
        raise
    finally:
        try:
            if r and (not changed or r['status']=='activated_code_only'):
                for t in r['active_timers']:run('systemctl','start',t)
        finally:
            if locked:
                (LOCK/'owner.json').unlink(missing_ok=True);LOCK.rmdir()
            controller.close()
if __name__=='__main__':main()
