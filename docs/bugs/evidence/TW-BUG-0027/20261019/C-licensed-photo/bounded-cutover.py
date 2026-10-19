"""Approved Oct 19 code-only cutover using the qualified retained primitives.

No model jobs, provider calls, subscriber mail, or public content writes.
The full historical operator is never invoked.
"""
from pathlib import Path
from datetime import datetime, timezone
from contextlib import ExitStack
import fcntl, hashlib, json, os, socket, subprocess, sys, time, types

OLD = '55afe01a5683c6f2471e0d578867ad77390bb739'
NEW = 'a849e8d5178e914621088982202f92db59c5ed65'
BASE = Path('/opt/smn-subscription')
RELEASE = BASE/'releases'/NEW
RECORD = Path('/var/lib/tradewave/release-state/smn-citi-a849e8d5-20261019')
BACKUP = Path('/var/tmp/smn-citi-licensed-20261019-dqdoa1ti/backup')
PLAN = Path('/var/tmp/smn-citi-licensed-20261019-dqdoa1ti/plan/unit-plan.json')
QUALIFIED_OPERATOR = Path('/var/tmp/smn-stabilization-qual-20261019-55afe01a-1mfmn66x/qualification/retained-operator.py')
DAILY = Path('/var/lib/tradewave/smn-daily/subscription-primary')
DAY = DAILY/'2026-10-19'
PUBLIC_RECEIPT = DAY/'chatgpt/production-publication-receipt.json'
MAIL = Path('/home/flask/blog/logs/sent_smn_emails.json')
WEB = Path('/var/www/smn')
SERVICES = ['smn-subscription.service','smn-weekday-newsletter.service'] + ['smn-continuity@'+p+'.service' for p in ['progress','deliver','reconcile']]
TIMERS = [s.replace('.service','.timer') for s in SERVICES]

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def require(value, message):
    if not value: raise ValueError(message)
def command(*args): return subprocess.check_output(args,text=True).strip()
def unit(name, fields):
    return dict(line.split('=',1) for line in command('systemctl','show',name,*['-p'+f for f in fields]).splitlines() if '=' in line)
def timers(): return {name:unit(name,['ActiveState','UnitFileState']) for name in TIMERS}
def services(): return {name:unit(name,['MainPID','ActiveState','ExecStart','WorkingDirectory','FragmentPath','DropInPaths']) for name in SERVICES}
def idle():
    return all(info['MainPID']=='0' and info['ActiveState'] not in {'active','activating','deactivating'} for info in services().values())

require(socket.gethostname().split('.')[0]=='seasonalmarketnews','Wrong host')
require('209.182.216.112' in command('hostname','-I').split(),'Wrong host IP')
now=datetime.now(timezone.utc)
require(now.date().isoformat()=='2026-10-19','Backup attestation expired')
require(sha(QUALIFIED_OPERATOR)=='4a4a020f19cce49bffb59de2bd4922b03eea6a6e53ee7ed9cb1a4ac04b474e2f','Qualified primitive source changed')
op=types.ModuleType('qualified_primitives');op.__file__=str(QUALIFIED_OPERATOR)
exec(compile(QUALIFIED_OPERATOR.read_bytes(),str(QUALIFIED_OPERATOR),'exec'),op.__dict__)
op.NEW=NEW;op.OLD=OLD;op.RELEASE=RELEASE;op.OLD_RELEASE=BASE/'releases'/OLD;op.RECORD=RECORD
op.DATE='2026-10-19';op.DAY=DAY;op.DAILY=DAILY
require(not RECORD.exists(),'Release record already exists; reconcile before any repeat')
require(os.readlink(BASE/'current')==str(op.OLD_RELEASE),'Baseline pointer changed')
require(op.git(RELEASE,'rev-parse','HEAD')==NEW and not op.git(RELEASE,'status','--porcelain','--untracked-files=no'),'Staged source not exact and clean')
require(sha(BACKUP/'backup-manifest.json')=='343f776d8198d38b6d9e02d2ab9fc2267c17409f8cbcff533346f11959971336','Restore-verified backup manifest changed')
backup=read(BACKUP/'backup-manifest.json');plan=read(PLAN)
require(plan['candidate']==NEW and len(plan['planned_files'])==3,'Unexpected live-file plan')
files=backup['files']
for item in files:
    require(op.metadata(item['source_path'])==item['before'],'Live managed file drift: '+item['source_path'])
    require(sha(item['backup_file'])==item['before']['sha256'],'Backup preimage drift')
for item in plan['planned_files']:
    require(sha(item['prepared_file'])==item['planned_sha256'],'Prepared bytes changed')
runtime_hashes = {'blog/newsletter_reader_snapshot.py': '6d53bc69afd54f655b75fd0eba4d25b24fd6ed6865ee6d6c1b48dbf2fa5f9f4b', 'blog/send_smn_emails.py': '737154f86b74fdb0ff6a5ddf0238fd3515f1b004bd714b0f0cd58d585bcdea8c', 'blog/home_quote_contract.py': 'e8ef2e61a4487c51f758f4d1dde92816861255a1f3cac94578b5d65ac997ffc9', 'blog/public_delivery_contract.cjs': 'c55e4aaabbb60b77cbe21ef70f3a117c12c26e5171ee4491a1e900171a084913', 'blog/subscription_inputs.py': '172b65bcaf06bce18e99c63993a3fa582624196f489569655a886982e8cb0228', 'blog/decorative_hero_reuse.py': '3a3e3aca5e470f7984dbc6f47307fd96814213b7d6fe3efbecd3b817df82733a', 'blog/presentation_fallback.py': '769f61ba3aa7c908e0c05a971a6cf52904a10221a7dafaf32c8654e0118abf07'}
for rel,digest in runtime_hashes.items():require(sha(RELEASE/rel)==digest,'Candidate source drift: '+rel)
invariants = {'/home/flask/blog/logs/sent_smn_emails.json': 'b5c28d85552e1c289024896a5d5b55bec2bfee161e84a045a04acedaf332f240', '/var/lib/tradewave/smn-daily/subscription-primary/2026-10-19/chatgpt/production-publication-receipt.json': 'f55168493347a1585632be39abfa4713153dcd71dbd3b3c43b94d1d743997034', '/var/lib/tradewave/smn-daily/subscription-primary/2026-10-16/chatgpt/production-publication-receipt.json': '86c901a7497d218ccfd569f7cc1d04b3dbad70d5dd04416196dc7ca31c75c3ab'}
def preserve():
    for name,digest in invariants.items():require(sha(name)==digest,'Protected receipt/mail advanced; preserve actual state: '+name)
preserve()
baseline={'utc':now.isoformat(),'pointer':os.readlink(BASE/'current'),'services':services(),'timers':timers(),
          'files':{item['source_path']:item['before'] for item in files},'invariants':invariants}
baseline_sha=op.digest(baseline);operator_sha=sha(__file__)
approval={'approved':True,'approved_by':'Afshin','approval_reference':'Sentinel_f05c2281100081919261646317141516',
 'scope':'Approved Citigroup photo and necessary source-bound licensed derivative support; no mail or spending','source_commit':NEW,'operator_sha256':operator_sha,'baseline_sha256':baseline_sha,
 'artifact_sha256':'ed3552fc85f1079f57f6a472537b1f4de4158903031aebc6a450c55afcb85205',
 'approve_smn_single_host_snapshot_scope':True,'snapshot_scope_approval_reference':'Sentinel_f0bc366526dc81918d8e15bb29117d7e',
 'production_snapshot':{'scope':'smn-single-host-v1','target_hostname':'seasonalmarketnews','target_ip':'209.182.216.112',
  'status':'completed','evidence_kind':'human-confirmed-current-day','confirmed_by':'Afshin',
  'confirmed_at_utc':'2026-10-19T16:24:02Z','completed_date_utc':'2026-10-19','provider':None,'snapshot_reference':None,'completed_at_utc':None,
  'evidence_reference':'Parent-reported direct human reply to explicit October 19 actual-SMN full-server backup completion question: yes do it',
  'confirmation_reference':'Sentinel_f0bc366526dc81918d8e15bb29117d7e'}}
for key in ['source_commit','operator_sha256','baseline_sha256','artifact_sha256']:approval['production_snapshot'][key]=approval[key]
op.snapshot_attestation(approval,now)
RECORD.mkdir(mode=0o700)
op.save(RECORD/'baseline.json',baseline);op.save(RECORD/'approval.json',approval)
(RECORD/'bounded-cutover.py').write_bytes(Path(__file__).read_bytes())
receipt={'utc':now.isoformat(),'status':'preflight_passed','source_commit':NEW,'baseline_source_commit':OLD,
 'operator_sha256':operator_sha,'qualified_primitives_sha256':sha(QUALIFIED_OPERATOR),'baseline_sha256':baseline_sha,
 'artifact_sha256':approval['artifact_sha256'],'targeted_backup':str(BACKUP),'full_backup_human_confirmed':True,
 'subscriber_sends':0,'provider_calls':0,'model_jobs':0,'public_content_writes':0}
op.save(RECORD/'receipt.json',receipt)
paused=[];mutated=False;restoration_errors=[]
def effective(expected):
    observed=services()
    for name,info in observed.items():
        original=baseline['services'][name]
        expected_path=str(BASE/'releases'/expected)
        for field in ['FragmentPath','DropInPaths']:
            require(info[field]==original[field],'Unexpected effective '+field+' for '+name)
        old_exec=op.execstart_projection(original['ExecStart'])['configuration']
        new_exec=op.execstart_projection(info['ExecStart'])['configuration']
        normalized={k:v.replace(str(op.OLD_RELEASE),expected_path) if isinstance(v,str) else v for k,v in old_exec.items()}
        require(new_exec==normalized,'Wrong effective command: '+name)
        require(info['WorkingDirectory']==original['WorkingDirectory'].replace(str(op.OLD_RELEASE),expected_path),'Wrong effective cwd: '+name)
    return observed
def managed_expected(after):
    for item in plan['planned_files']:
        before=baseline['files'][item['live_path']]
        target={**before,'sha256':item['planned_sha256']} if after else before
        require(op.metadata(item['live_path'])==target,'Managed bytes/metadata mismatch: '+item['live_path'])
    for item in files:
        if not item['managed_change_target']:require(op.metadata(item['source_path'])==item['before'],'Preserved drop-in drift')
def rollback():
    with ExitStack() as leases:
        leases.enter_context(op.coordination_locks())
        controller=leases.enter_context((DAILY/'controller.lock').open('rb'))
        fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
        restore_owned_files()
def restore_owned_files():
    require(idle(),'Service became busy; preserve and report rollback required')
    preserve()
    require(os.readlink(BASE/'current') in {str(op.OLD_RELEASE),str(RELEASE)},'Peer pointer drift; cannot restore')
    for item in plan['planned_files']:
        before=baseline['files'][item['live_path']]
        op.rollback_admissible(op.metadata(item['live_path']),before,{**before,'sha256':item['planned_sha256']})
        image=BACKUP/'preimages'/hashlib.sha256(item['live_path'].encode()).hexdigest()
        require(sha(image)==before['sha256'],'Restore preimage changed')
    for item in plan['planned_files']:
        image=BACKUP/'preimages'/hashlib.sha256(item['live_path'].encode()).hexdigest()
        op.atomic(item['live_path'],image.read_bytes())
    op.point(str(op.OLD_RELEASE));command('systemctl','daemon-reload')
    managed_expected(False);effective(OLD);preserve()
    receipt.update(status='rolled_back',rollback_verified_utc=op.utc())

try:
    with op.activation_lease():
        try:
            for name in TIMERS:
                if baseline['timers'][name]['ActiveState']=='active':
                    paused.append(name);command('systemctl','stop',name)
            until=time.monotonic()+20
            while not idle() and time.monotonic()<until:time.sleep(.25)
            require(idle(),'Existing service still busy; no job will be stopped')
            with ExitStack() as leases:
                leases.enter_context(op.coordination_locks())
                controller=leases.enter_context((DAILY/'controller.lock').open('rb'))
                fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
                require('FLOCK' in Path('/proc/self/fdinfo/'+str(controller.fileno())).read_text(),'Own controller flock missing')
                preserve();managed_expected(False)
                require(os.readlink(BASE/'current')==baseline['pointer'],'Pointer changed before writes')
                sys.path.insert(0,str(RELEASE/'blog'))
                import home_quote_contract as quotes
                home_before=quotes.contract((WEB/'index.html').read_bytes())
                mutated=True
                for item in plan['planned_files']:op.atomic(item['live_path'],Path(item['prepared_file']).read_bytes())
                op.point(str(RELEASE));command('systemctl','daemon-reload')
                managed_expected(True)
                receipt['effective_units']=effective(NEW)
                require((BASE/'current').resolve()==RELEASE,'Active pointer mismatch')
                os.environ.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=str(RELEASE))
                import install_smn_primary_edition as installer
                installer.configure_production();installer.guard()
                import production_continuity as continuity
                native=read(PUBLIC_RECEIPT)
                continuity.verify_public_receipt(native,'2026-10-19',native['published_symbols'])
                import newsletter_reader_snapshot as snapshot
                frozen=snapshot.capture(DAILY,'2026-10-19',WEB,current=datetime.now(timezone.utc))
                def prove_only(binding):
                    op.save(RECORD/'non_sending_reservation_probe.json',{'binding_sha256':op.digest(binding),'articles':len(frozen.articles),'campaign_created':False})
                    return True
                require(snapshot.reserve(frozen,frozen.articles,prove_only,current=datetime.now(timezone.utc)),'Reservation probe failed')
                require(quotes.matches(home_before,quotes.contract((WEB/'index.html').read_bytes())),'Home changed beyond current quote values')
                preserve()
                for rel,digest in runtime_hashes.items():require(sha(RELEASE/rel)==digest,'Active runtime drift')
                receipt.update(status='active_verified',verified_utc=op.utc(),reader_articles_verified=len(frozen.articles),
                               native_edition_files_verified=sum(1 for p in native['files'] if p.startswith('editions/2026-10-19/')),
                               non_sending_capture_and_reservation_passed=True,current_pointer=str((BASE/'current').resolve()))
                op.save(RECORD/'receipt.json',receipt)
        except BaseException as error:
            receipt.update(status='activation_failed',error_type=type(error).__name__,error=str(error),failed_utc=op.utc())
            if mutated:
                try:rollback()
                except BaseException as rollback_error:receipt.update(status='rollback_required',rollback_error=str(rollback_error))
            op.save(RECORD/'receipt.json',receipt)
            raise
        finally:
            for name in reversed(paused):
                try:command('systemctl','start',name)
                except BaseException as error:restoration_errors.append(name+': '+str(error))
            actual=timers()
            if actual!=baseline['timers']:restoration_errors.append('Timer states differ from baseline')
            op.save(RECORD/'timer-restoration.json',{'utc':op.utc(),'before':baseline['timers'],'after':actual,'errors':restoration_errors})
            receipt['timers_restored']=not restoration_errors
            if restoration_errors:receipt.update(status='rollback_required',timer_restoration_errors=restoration_errors)
            op.save(RECORD/'receipt.json',receipt)
            require(not restoration_errors,'Timer restoration failed')
except BaseException:
    print(json.dumps(receipt));raise
print(json.dumps(receipt))
