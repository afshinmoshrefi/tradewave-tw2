"""Reviewable operator cutover; preflight is read-only. NEVER run apply without approval."""
import argparse,fcntl,hashlib,json,os,re,shlex,shutil,stat,subprocess,tarfile,tempfile
from datetime import datetime,timezone
from pathlib import Path
SHA=None  # Set only by a required exact --sha argument.
OLD='2d1de1a9c9f200fa29a2db7f9660f3527727b660'
BASE=Path('/opt/smn-subscription');CURRENT=BASE/'current'
STATE=Path('/var/lib/tradewave/release-state');LOCK=STATE/'smn-production-activation.lock'
ACTIVATION=Path('/etc/SMN/subscription-primary.json');UNITS=Path('/etc/systemd/system')
DAILY=Path('/var/lib/tradewave/smn-daily/subscription-primary')
MAIL_STATE=Path('/home/flask/blog/logs/sent_smn_emails.json')
MAIL_LEDGERS=Path('/var/lib/smn-dashboard/schedule-runs')
CODEX=Path('/opt/smn-codex-0.155.0-alpha.16/node_modules/.bin/codex')
EXISTING=['smn-subscription','smn-weekday-newsletter']
CONTINUITY=['smn-continuity@progress','smn-continuity@deliver','smn-continuity@reconcile']
TIMERS=[name+'.timer' for name in EXISTING+CONTINUITY]
SERVICES=[name+'.service' for name in EXISTING+CONTINUITY]
PYTHON='/home/flask/venv/bin/python'
GIT_ADAPTER=Path('/opt/smn-subscription/bin/git')
GIT_ADAPTER_BYTES=b'#!/bin/sh\nexec /usr/bin/sudo -u flask /usr/bin/git \"$@\"\n'
CONTINUITY_PATH='/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
def repo():return BASE/'releases'/SHA
def require_sha(value):
 if not re.fullmatch('[0-9a-f]{40}',str(value)):raise ValueError('Exact 40-character source SHA required')
 return value
def run(*args):return subprocess.check_output(args,text=True).strip()
def git(repo,*args):return run('sudo','-u','flask','git','-C',str(repo),*args)
def git_bytes(checkout,*args):return subprocess.check_output(['sudo','-u','flask','git','-C',str(checkout),*args])
def git_adapter_metadata():
 value=metadata(GIT_ADAPTER)
 if (value is None or value['uid']!=0 or value['mode'] & 0o022 or not os.access(GIT_ADAPTER,os.X_OK) or
     GIT_ADAPTER.read_bytes()!=GIT_ADAPTER_BYTES):
  raise ValueError('Existing root-owned Flask Git adapter is missing or changed')
 return value
def continuity_git_dropin():return UNITS/'smn-continuity@.service.d/10-release-git.conf'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None
def metadata(path):
 path=Path(path)
 if path.is_symlink():raise ValueError('Managed file is a symlink: '+str(path))
 if not path.exists():return None
 if not path.is_file():raise ValueError('Managed path is not a file: '+str(path))
 st=path.stat();return {'sha256':sha(path),'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
def mail_ledgers():
 if not MAIL_LEDGERS.is_dir():return {}
 return {str(path):sha(path) for phase in ('weekday_newsletter','sunday_summary')
         for path in sorted(MAIL_LEDGERS.glob('production-'+phase+'-*.json'))}
def verify_archive_equivalence(archive,checkout):
 """The qualified Windows tar may have CRLF; every deployed Git blob must match after only CRLF folding."""
 names=git_bytes(checkout,'ls-tree','-r','-z','--name-only',SHA)
 committed=set(names.decode('utf-8').strip('\0').split('\0'))
 normalized=0
 with tarfile.open(archive,'r:') as bundle:
  members={item.name:item for item in bundle if item.isfile()}
  if set(members)!=committed:raise ValueError('Qualified archive and deployed Git file lists differ')
  for name,item in members.items():
   if item.issym() or item.islnk() or name.startswith('/') or '..' in Path(name).parts:
    raise ValueError('Unsafe qualified source archive member')
   qualified=bundle.extractfile(item).read()
   deployed=git_bytes(checkout,'show',SHA+':'+name)
   if qualified==deployed:continue
   if (Path(name).suffix.lower() not in {'.py','.cjs','.js','.md','.txt','.json','.html','.css','.svg',
                                          '.service','.timer','.conf','.yaml','.yml','.toml','.sh'} and
       Path(name).name not in {'.gitignore','.gitattributes'} or
       b'\x00' in qualified or qualified.replace(b'\r\n',b'\n')!=deployed):
    raise ValueError('Qualified source differs beyond CRLF: '+name)
   normalized+=1
 return {'files':len(committed),'crlf_normalized':normalized}
def read(path):return json.loads(Path(path).read_text())
def atomic(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix=path.name+'.continuity-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as out:out.write(data);out.flush();os.fsync(out.fileno())
  if path.exists():shutil.copystat(path,name);st=path.stat();os.chown(name,st.st_uid,st.st_gid)
  else:os.chmod(name,0o644)
  os.replace(name,path)
 finally:
  if Path(name).exists():Path(name).unlink()
def save(path,value):atomic(path,(json.dumps(value,indent=2)+'\n').encode())
def point(target):
 temporary=CURRENT.with_name('current.continuity-'+str(os.getpid()))
 if temporary.exists() or temporary.is_symlink():raise ValueError('Existing pointer transaction')
 temporary.symlink_to(target);os.replace(temporary,CURRENT)
def unit_info(unit):
 values=run('systemctl','show',unit,'-p','FragmentPath','-p','DropInPaths','-p','WorkingDirectory','-p','User').splitlines()
 return dict(line.split('=',1) for line in values)
def enabled(unit):return subprocess.run(['systemctl','is-enabled','--quiet',unit]).returncode==0
def active(unit):return subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0
def loaded(unit):return run('systemctl','show',unit,'-p','LoadState','--value')!='not-found'
def stop(unit):
 if loaded(unit):run('systemctl','stop',unit)
def files():
 paths={ACTIVATION,UNITS/'smn-continuity@.service',UNITS/'smn-continuity@.timer',continuity_git_dropin()}
 for name in EXISTING:
  info=unit_info(name+'.service')
  for text in [info.get('FragmentPath',''),*info.get('DropInPaths','').split()]:
   if text:
    path=Path(text)
    if UNITS not in path.parents or path.is_symlink():raise ValueError('Unexpected managed unit path '+text)
    paths.add(path)
 return sorted(paths)
def snapshot():
 if '209.182.216.112' not in run('hostname','-I').split():raise ValueError('Production host required')
 if not CURRENT.is_symlink():raise ValueError('Current release pointer is not a symlink')
 if CURRENT.resolve()!=BASE/'releases'/OLD or read(ACTIVATION).get('source_commit')!=OLD:raise ValueError('Baseline pointer/config changed')
 if read(ACTIVATION).get('publication_policy')=='continuity-v1':raise ValueError('Continuity policy is already active')
 if not CODEX.is_file() or not os.access(CODEX,os.X_OK) or not Path(PYTHON).is_file():raise ValueError('Pinned Codex or Python runtime missing')
 if LOCK.exists():raise ValueError('Live activation lock: preserve its owner')
 if any(active(unit) for unit in SERVICES):raise ValueError('Wait for running controller/newsletter/continuity services')
 expected_blog=str(BASE/'releases'/OLD/'blog')
 units={name:unit_info(name+'.service') for name in EXISTING}
 if any(info['WorkingDirectory']!=expected_blog for info in units.values()):raise ValueError('Effective source path drift')
 receipt=read(DAILY/'2026-10-05/chatgpt/production-publication-receipt.json')
 if receipt.get('status')!='live_verified' or receipt.get('edition_date')!='2026-10-05' or len(receipt.get('urls',[]))!=6:
  raise ValueError('October 5 complete publication baseline changed')
 return {'source_commit':OLD,'existing_git_adapter':git_adapter_metadata(),'previous_pointer':os.readlink(CURRENT),'files':{str(p):metadata(p) for p in files()},
  'units':units,'timers':{unit:{'enabled':enabled(unit),'active':active(unit)} for unit in TIMERS},
  'catalog_sha256':sha('/var/www/smn/posts.json'),'oct5_receipt_sha256':sha(DAILY/'2026-10-05/chatgpt/production-publication-receipt.json'),
  'mail_state_sha256':sha(MAIL_STATE),'mail_ledgers':mail_ledgers(),
  'preserved_campaign_id':'200497784617437041','publication_policy':read(ACTIVATION).get('publication_policy')}
def claim_lock(record, task, recover=False):
 if LOCK.exists():
  if not recover:raise ValueError('Existing production activation lock')
  owner=read(LOCK/'owner.json')
  if owner.get('source_commit')!=SHA or owner.get('record')!=str(record):
   raise ValueError('Peer activation lock; preserve owner')
  pid=owner.get('pid')
  if not isinstance(pid,int):raise ValueError('Unverifiable activation lock owner')
  try:os.kill(pid,0)
  except ProcessLookupError:pass
  else:raise ValueError('Activation lock owner is still alive')
 else:LOCK.mkdir()
 save(LOCK/'owner.json',{'source_commit':SHA,'record':str(record),'pid':os.getpid(),'task':task})
def release_lock():
 owner=read(LOCK/'owner.json')
 if owner.get('source_commit')!=SHA or owner.get('pid')!=os.getpid():raise ValueError('Activation lock ownership changed')
 (LOCK/'owner.json').unlink();LOCK.rmdir()
def schedule_locks():
 """Serialize with both existing timer entry points before touching mail/code."""
 handles=[]
 try:
  for name in ('scheduler.lock','newsletter.lock'):
   handle=(MAIL_LEDGERS/name).open('a')
   handles.append(handle)
   fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
  return handles
 except BaseException:
  for handle in reversed(handles):handle.close()
  raise
def restore(record,r):
 # Journal/state is NEVER restored from backup; uncertain outcomes require provider reconciliation.
 if (sha('/var/www/smn/posts.json')!=r['baseline']['catalog_sha256'] or
     sha(DAILY/'2026-10-05/chatgpt/production-publication-receipt.json')!=r['baseline']['oct5_receipt_sha256']):
  raise ValueError('Public catalog/receipt changed; targeted publication rollback and peer review required')
 for text,before in r['baseline']['files'].items():
  path=Path(text);current=metadata(path)
  if current!=before and current!=r['planned'].get(text):
   raise ValueError('Peer changed '+text)
  backup=record/'backup'/hashlib.sha256(text.encode()).hexdigest()
  if before is not None and sha(backup)!=before['sha256']:raise ValueError('Backup changed '+text)
 if CURRENT.resolve() not in {repo(),BASE/'releases'/OLD}:raise ValueError('Peer changed runtime pointer')
 for timer in TIMERS:stop(timer)
 if any(active(unit) for unit in SERVICES):raise ValueError('Active production work; do not interrupt for rollback')
 for unit in [name+'.timer' for name in CONTINUITY]:
  if loaded(unit):run('systemctl','disable',unit)
 for text,before in r['baseline']['files'].items():
  path=Path(text);backup=record/'backup'/hashlib.sha256(text.encode()).hexdigest()
  if before is None:
   if path.exists():path.unlink()
  else:
   atomic(path,backup.read_bytes())
   os.chmod(path,before['mode']);os.chown(path,before['uid'],before['gid'])
 point(r['baseline']['previous_pointer']);run('systemctl','daemon-reload')
 mail_held=(sha(MAIL_STATE)!=r['baseline']['mail_state_sha256'] or
            mail_ledgers()!=r['baseline']['mail_ledgers'])
 for unit,state in r['baseline']['timers'].items():
  if not loaded(unit) and not state['enabled'] and not state['active']:continue
  if unit in {'smn-weekday-newsletter.timer','smn-subscription.timer'} and mail_held:
   run('systemctl','disable',unit);continue
  run('systemctl','enable' if state['enabled'] else 'disable',unit)
  if state['active']:run('systemctl','start',unit)
 r.update(status='rolled_back_mail_held' if mail_held else 'rolled_back',manual_provider_reconciliation_required=mail_held)
 if mail_held:r['mail_hold_reason']='Newsletter journal changed; old sender ignores new reservations. Reconcile campaign IDs before enabling old mail timer.'
 save(record/'receipt.json',r)
 for text,expected in r['baseline']['files'].items():
  if metadata(text)!=expected:raise ValueError('Restoration mismatch '+text)
 if CURRENT.resolve()!=BASE/'releases'/OLD:raise ValueError('Rollback pointer mismatch')
def approve(approval,manifest,bundle,source_archive,baseline_path,qualification,native_proof,browser_proof,pixel_proof):
 today=datetime.now(timezone.utc).date().isoformat()
 if (approval.get('source_commit')!=SHA or approval.get('date')!=today or not approval.get('approved_by') or
  approval.get('execute_production_continuity') is not True or approval.get('production_web_snapshot') is not True or
  approval.get('production_app_snapshot') is not True or approval.get('publication_policy')!='continuity-v1' or
  approval.get('baseline_sha256')!=sha(baseline_path) or approval.get('preserved_campaign_id')!='200497784617437041' or
  approval.get('operator_script_sha256')!=sha(__file__) or approval.get('approve_existing_git_adapter_dropin') is not True):
  raise ValueError('Exact release authorization and current-day snapshots required')
 if manifest.get('source_commit')!=SHA or manifest.get('bundle_sha256')!=sha(bundle):raise ValueError('Immutable release bundle mismatch')
 if manifest.get('freshness_check_sha256')!=sha(Path(__file__).with_name('smn-production-freshness-check.py')):
  raise ValueError('Bound postcutover freshness checker differs')
 if (manifest.get('source_archive_sha256')!=sha(source_archive) or
     manifest.get('source_archive_sha256')!=read(native_proof).get('source_archive_sha256')):
  raise ValueError('Native-qualified source archive differs')
 qualified=read(qualification);native=read(native_proof);browser=read(browser_proof);pixel=read(pixel_proof)
 if (manifest.get('qualification_manifest_sha256')!=sha(qualification) or
     any(proof.get('source_commit')!=SHA for proof in (qualified,native,browser,pixel)) or
     qualified.get('proofs')!={native_proof.name:sha(native_proof),browser_proof.name:sha(browser_proof),
                                pixel_proof.name:sha(pixel_proof)}):
  raise ValueError('Exact native/browser/pixel qualification manifest required')
 if (native.get('network_disabled') is not True or native.get('provider_model_email_calls')!=0 or
     len(native.get('revisions',[]))!=3 or
     [(r.get('coverage'),r.get('complete')) for r in native['revisions']]!=
        [('notice',False),('partial',False),('complete',True)] or
     any(r.get('native_prepare_and_temp_activation') is not True or r.get('rollback_exact') is not True
         for r in native['revisions'])):
  raise ValueError('Native qualification does not prove all guarded revisions')
 if (browser.get('native_proof_sha256')!=sha(native_proof) or
     browser.get('offline_fixture') is not True or browser.get('all_requests_fulfilled_from_fixture') is not True or
     browser.get('public_production_verification') is not False or len(browser.get('pages',[]))!=qualified.get('browser_pages')):
  raise ValueError('Final reviewed browser qualification missing')
 if (pixel.get('browser_proof_sha256')!=sha(browser_proof) or pixel.get('offline_fixture') is not True or
     pixel.get('public_production_verification') is not False or
     len(pixel.get('visually_inspected',[]))!=qualified.get('pixel_inspected') or
     any(pixel.get('calls',{}).get(kind)!=0 for kind in ('model','email','provider'))):
  raise ValueError('Independent pixel inspection evidence differs')
 for item in pixel['visually_inspected']:
  path=pixel_proof.parent/item['name']
  if path.name!=item['name'] or sha(path)!=item['sha256']:
   raise ValueError('Inspected screenshot changed: '+item['name'])
def postcheck(r):
 baseline=r['baseline']
 if git_adapter_metadata()!=baseline['existing_git_adapter']:raise ValueError('Existing Git adapter changed after preflight')
 if (CURRENT.resolve()!=repo() or git(repo(),'rev-parse','HEAD')!=SHA or
     git(repo(),'status','--porcelain','--untracked-files=no') or
     not CODEX.is_file() or not os.access(CODEX,os.X_OK)):
  raise ValueError('Candidate runtime or pinned Codex path changed')
 config=read(ACTIVATION)
 if config.get('source_commit')!=SHA or config.get('publication_policy')!='continuity-v1' or config.get('record')!=r['record']:
  raise ValueError('Source-bound continuity policy changed')
 for name in EXISTING:
  if unit_info(name+'.service').get('WorkingDirectory')!=str(repo()/'blog'):
   raise ValueError('Effective existing service path changed')
 for phase in CONTINUITY:
  if not loaded(phase+'.service') or unit_info(phase+'.service').get('WorkingDirectory')!=str(CURRENT/'blog'):
   raise ValueError('Continuity service template is not loaded')
  environment=dict(item.split('=',1) for item in shlex.split(run('systemctl','show',phase+'.service','-p','Environment','--value')) if '=' in item)
  if environment.get('PATH')!=CONTINUITY_PATH:
   raise ValueError('Continuity service does not use the existing Flask Git adapter')
 if (sha('/var/www/smn/posts.json')!=baseline['catalog_sha256'] or
     sha(DAILY/'2026-10-05/chatgpt/production-publication-receipt.json')!=baseline['oct5_receipt_sha256'] or
     sha(MAIL_STATE)!=baseline['mail_state_sha256'] or mail_ledgers()!=baseline['mail_ledgers']):
  raise ValueError('Existing publication or newsletter state changed')
 for text,expected in r['planned'].items():
  if metadata(text)!=expected:raise ValueError('Installed config/unit changed: '+text)
 receipt=read(DAILY/'2026-10-05/chatgpt/production-publication-receipt.json')
 urls=set(receipt.get('urls',[]))
 if len(urls)!=6 or any(not url.startswith('https://seasonalmarketnews.com/editions/2026-10-05/') for url in urls):
  raise ValueError('Preserved six-article edition differs')
 checker=Path(__file__).with_name('smn-production-freshness-check.py')
 if sha(checker)!=r['freshness_check_sha256']:raise ValueError('Bound read-only freshness checker changed')
 fresh=json.loads(run(PYTHON,str(checker),'--date','2026-10-05'))
 if (fresh.get('complete_edition_verified') is not True or
     fresh.get('receipt_sha256')!=baseline['oct5_receipt_sha256'] or
     fresh.get('active_release')!=str(repo()) or
     len(fresh.get('articles',[]))!=6):
  raise ValueError('Exact public October 5 content/links failed read-only freshness check')
 return fresh
def apply(args):
 approval=read(args.approval);manifest=read(args.manifest)
 approve(approval,manifest,args.bundle,args.source_archive,args.baseline,args.qualification,
         args.native_proof,args.browser_proof,args.pixel_proof)
 preflight=read(args.baseline);baseline=preflight.get('state')
 if (datetime.fromisoformat(preflight['captured_utc'].replace('Z','+00:00')).date().isoformat()!=
     datetime.now(timezone.utc).date().isoformat() or snapshot()!=baseline):
  raise ValueError('Current-day baseline drift; inspect and requalify')
 record=STATE/('smn-continuity-'+SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat())
 if record.exists():raise ValueError('Prior transaction: inspect retained receipt')
 handles=schedule_locks();controller=None;locked=False;retain=False;r=None
 try:
  controller=(DAILY/'controller.lock').open('a')
  fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
  claim_lock(record,'TW-BUG-0027-production-continuity');locked=True
  # Refuse a running writer or publisher, rather than interrupting its work.
  if any(active(unit) for unit in SERVICES):raise ValueError('Service started during cutover acquisition')
  record.mkdir(mode=0o700);(record/'backup').mkdir()
  r={'source_commit':SHA,'record':str(record),'status':'prepared','baseline':baseline,'planned':{},
     'freshness_check_sha256':manifest['freshness_check_sha256'],'approval':approval}
  for text,expected in baseline['files'].items():
   if metadata(text)!=expected:raise ValueError('Managed file changed before backup')
   if expected is not None:shutil.copy2(text,record/'backup'/hashlib.sha256(text.encode()).hexdigest())
  save(record/'receipt.json',r)
  # Stop mail before source or journal semantics change. No mail state is overwritten.
  for timer in TIMERS:stop(timer)
  if any(active(unit) for unit in SERVICES):raise ValueError('Active service after timer stop')
  if (sha(MAIL_STATE)!=baseline['mail_state_sha256'] or mail_ledgers()!=baseline['mail_ledgers']):
   raise ValueError('Newsletter state changed during cutover acquisition')
  stop('smn-weekday-newsletter.service')
  git(CURRENT,'fetch',str(args.bundle.resolve()),'codex/smn-continuity-production')
  if not repo().exists():git(CURRENT,'worktree','add','--detach',str(repo()),SHA)
  if git(repo(),'rev-parse','HEAD')!=SHA or git(repo(),'status','--porcelain','--untracked-files=no'):raise ValueError('Candidate checkout changed')
  r['archive_equivalence']=verify_archive_equivalence(args.source_archive,repo())
  save(record/'receipt.json',r)
  if sha(repo()/'ops/smn-continuity-production/smn-continuity@.service') is None:
   raise ValueError('Candidate continuity templates missing')
  for text in baseline['files']:
   path=Path(text)
   if path==ACTIVATION:
    value=read(path);value.update(source_commit=SHA,publication_policy='continuity-v1',record=str(record));data=(json.dumps(value,indent=2)+'\n').encode()
   elif path==continuity_git_dropin():
    if baseline['files'][text] is not None:raise ValueError('Existing continuity Git drop-in requires separate drift classification')
    data=('[Service]\nEnvironment=PATH='+CONTINUITY_PATH+'\n').encode()
   elif path.name in {'smn-continuity@.service','smn-continuity@.timer'}:
    if baseline['files'][text] is not None:raise ValueError('Existing continuity template requires separate drift classification')
    data=(repo()/'ops/smn-continuity-production'/path.name).read_bytes()
   else:data=path.read_bytes().replace(str(BASE/'releases'/OLD).encode(),str(repo()).encode())
   prior=baseline['files'][text]
   r['planned'][text]={'sha256':hashlib.sha256(data).hexdigest(),
      'mode':prior['mode'] if prior else 0o644,'uid':prior['uid'] if prior else os.geteuid(),
      'gid':prior['gid'] if prior else os.getegid()}
   save(record/'receipt.json',r);atomic(path,data)
   if metadata(path)!=r['planned'][text]:raise ValueError('Installed file metadata differs: '+text)
  point(repo());run('systemctl','daemon-reload')
  for name in EXISTING:
   if unit_info(name+'.service')['WorkingDirectory']!=str(repo()/'blog'):raise ValueError('Effective runtime drift')
  if (sha(MAIL_STATE)!=baseline['mail_state_sha256'] or mail_ledgers()!=baseline['mail_ledgers'] or
      sha(DAILY/'2026-10-05/chatgpt/production-publication-receipt.json')!=baseline['oct5_receipt_sha256'] or
      sha('/var/www/smn/posts.json')!=baseline['catalog_sha256']):
   raise ValueError('Existing edition/campaign/catalog state changed during cutover')
  config=read(ACTIVATION)
  if config.get('source_commit')!=SHA or config.get('publication_policy')!='continuity-v1' or CURRENT.resolve()!=repo():
   raise ValueError('Source-bound production policy did not activate')
  r['status']='source_activated_timers_held';save(record/'receipt.json',r)
  print(json.dumps(r))
 except BaseException:
  if r:
   try:restore(record,r)
   except BaseException as failure:
    retain=True;r.update(status='rollback_required',rollback_error=str(failure));save(record/'receipt.json',r)
  raise
 finally:
  if locked and not retain:release_lock()
  if controller:controller.close()
  for handle in reversed(handles):handle.close()
def finalize(args):
 record=args.record.resolve()
 if record.parent!=STATE or record.name!='smn-continuity-'+SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat():
  raise ValueError('Unexpected current-day finalization record')
 r=read(record/'receipt.json')
 if r.get('source_commit')!=SHA or r.get('status')!='source_activated_timers_held':
  raise ValueError('Source activation is not held for verification')
 handles=schedule_locks();controller=None;locked=False;retain=False
 try:
  controller=(DAILY/'controller.lock').open('a');fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
  claim_lock(record,'TW-BUG-0027-finalize');locked=True
  if any(active(unit) for unit in SERVICES):raise ValueError('Service started while cutover timers held')
  r['live_postcheck']=postcheck(r);save(record/'receipt.json',r)
  for timer,state in r['baseline']['timers'].items():
   if timer in [name+'.timer' for name in CONTINUITY]:
    run('systemctl','enable',timer);run('systemctl','start',timer)
   else:
    run('systemctl','enable' if state['enabled'] else 'disable',timer)
    if state['active']:run('systemctl','start',timer)
  r['status']='active_verified';save(record/'receipt.json',r);print(json.dumps(r))
 except BaseException:
  if locked:
   try:restore(record,r)
   except BaseException as failure:
    retain=True;r.update(status='rollback_required',rollback_error=str(failure));save(record/'receipt.json',r)
  raise
 finally:
  if locked and not retain:release_lock()
  if controller:controller.close()
  for handle in reversed(handles):handle.close()
def rollback(args):
 record=args.record.resolve()
 if record.parent!=STATE or not record.name.startswith('smn-continuity-'):raise ValueError('Unexpected rollback record')
 r=read(record/'receipt.json')
 if r.get('source_commit')!=SHA:raise ValueError('Wrong rollback release')
 handles=schedule_locks();controller=None;locked=False;retain=False
 try:
  controller=(DAILY/'controller.lock').open('a')
  fcntl.flock(controller,fcntl.LOCK_EX|fcntl.LOCK_NB)
  claim_lock(record,'TW-BUG-0027-rollback',recover=True);locked=True
  restore(record,r);print(json.dumps(r))
 except BaseException as failure:
  if locked:retain=True;r.update(status='rollback_required',rollback_error=str(failure));save(record/'receipt.json',r)
  raise
 finally:
  if locked and not retain:release_lock()
  if controller:controller.close()
  for handle in reversed(handles):handle.close()
def main():
 global SHA
 parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
 preflight=sub.add_parser('preflight');preflight.add_argument('--sha',required=True)
 apply_parser=sub.add_parser('apply')
 apply_parser.add_argument('--sha',required=True)
 for name in ('approval','manifest','bundle','source-archive','baseline','qualification','native-proof','browser-proof','pixel-proof'):
  apply_parser.add_argument('--'+name,type=Path,required=True)
 finalize_parser=sub.add_parser('finalize');finalize_parser.add_argument('--sha',required=True);finalize_parser.add_argument('--record',type=Path,required=True)
 rollback_parser=sub.add_parser('rollback');rollback_parser.add_argument('--sha',required=True);rollback_parser.add_argument('--record',type=Path,required=True)
 args=parser.parse_args()
 SHA=require_sha(args.sha)
 if args.action=='preflight':print(json.dumps({'captured_utc':datetime.now(timezone.utc).isoformat(),'state':snapshot()},indent=2))
 elif args.action=='apply':apply(args)
 elif args.action=='finalize':finalize(args)
 else:rollback(args)
if __name__=='__main__':main()
