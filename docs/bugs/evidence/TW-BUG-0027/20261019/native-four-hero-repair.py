"""Approved additive image backfill; preserve factual artifacts and all mail state."""
from pathlib import Path
from contextlib import ExitStack
from datetime import datetime,timezone
import fcntl,hashlib,json,os,shutil,subprocess,sys,time

NEW='55afe01a5683c6f2471e0d578867ad77390bb739'
repo=Path('/opt/smn-subscription/current').resolve()
assert repo.name==NEW
sys.path.insert(0,str(repo/'blog'))
os.environ.update(SMN_CAPTURE_LOCAL='1',SMN_BROWSER_CHANNEL='bundled',SMN_PLAYWRIGHT='/opt/smn-playwright/node_modules/playwright',
 GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=str(repo))
os.environ['PATH']='/opt/smn-subscription/bin:/opt/smn-shadow/node/bin:'+os.environ['PATH']
import production_continuity as native
import decorative_hero_reuse as reuse
from subscription_publication import package,validate_staged_reviews
import install_smn_primary_edition as installer
native.require_policy(NEW)
daily=Path('/var/lib/tradewave/smn-daily/subscription-primary')
root=daily/'2026-10-16/chatgpt'
today=daily/'2026-10-19/chatgpt'
prepared=Path('/var/tmp/smn-hero-backfill-20261019-twywv3vf')
record=Path('/var/lib/tradewave/release-state/smn-four-hero-backfill-20261019')
assert not record.exists(),'Existing repair record must be reconciled before repeating'
record.mkdir(mode=0o700)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def save(p,v):native._write(p,v)
def command(*a):return subprocess.check_output(a,text=True).strip()
services=['smn-subscription.service','smn-weekday-newsletter.service']+['smn-continuity@'+p+'.service' for p in ['progress','deliver','reconcile']]
timers=[s.replace('.service','.timer') for s in services]
def timer_states():
 return {t:dict(row.split('=',1) for row in command('systemctl','show',t,'-pActiveState','-pUnitFileState').splitlines() if '=' in row) for t in timers}
def idle():return all(command('systemctl','show',s,'-pMainPID','--value')=='0' for s in services)
prior=read(root/'production-publication-receipt.json')
assert prior['status']=='live_verified' and set(prior['published_symbols'])=={'GS','PGR','C','XLK','MRK'}
assert prior['pending_symbols']==['DPZ']
native.verify_public_receipt(prior,'2026-10-16',prior['published_symbols'])
summary=read(prepared/'preparation-summary.json')
assets=[row for row in summary['articles'] if row['symbol'] in {'GS','PGR','XLK','MRK'}]
assert len(assets)==4
originals={}
for row in assets:
 sym=row['symbol'];source=prepared/'results'/sym;target=root/'results'/sym
 assert sha(source/'decorative-hero-reuse.json')==row['override_sha256']
 override=read(source/'decorative-hero-reuse.json')
 assert reuse.override(source)==override['hero']
 originals[sym]={name:sha(target/name) for name in ['article.json','article.html','hero-asset.json']}
 assert originals[sym]==override['original_files']
 assert all(not (target/name).exists() for name in ['decorative-hero-reuse.json','decorative-hero-source-receipt.json',override['hero']['url']]),'Existing override requires classification'
mail=Path('/home/flask/blog/logs/sent_smn_emails.json');mail_before=sha(mail)
states=timer_states();paused=[]
result={'utc':datetime.now(timezone.utc).isoformat(),'status':'prepared','source_commit':NEW,'original_factual_artifact_hashes':originals,
 'subscriber_sends':0,'provider_calls':0,'new_image_generations':0,'model_jobs':0,'C':'pending_no_existing_qualified_asset','DPZ':'held_unchanged'}
save(record/'repair.json',result)
shutil.copy2(root/'production-publication-receipt.json',record/'oct16-prior-receipt.json')
shutil.copy2(today/'production-publication-receipt.json',record/'oct19-prior-receipt.json')

def restore_latest_home():
 """Native publication-only repair after the historical transaction changes home."""
 current=read(today/'production-publication-receipt.json')
 assert set(current['published_symbols'])=={'QQQ','SPY','XLF','AMZN','CSX','CCK'} and current['complete'] is True
 native.verify_public_receipt(current,'2026-10-19',current['published_symbols'])
 with native._lock(today):
  stages,hashes=native._eligible(today,'2026-10-19',current['published_symbols'])
  assert set(stages)==set(current['published_symbols'])
  selection=native._sha(today/'input-selection.json')
  identity=native._json_sha({'date':'2026-10-19','selection':selection,'source':NEW,'articles':hashes})
  family=today/'publication-revisions'/identity
  attempt=next((i for i in range(1,4) if not (family/('attempt-'+str(i))).exists()),None)
  assert attempt is not None,'Native publication attempt allowance exhausted'
  tx=family/('attempt-'+str(attempt))
  native._snapshot(today,tx,'2026-10-19',stages,current,selection_frozen=True)
  before={rel:sha(Path('/var/www/smn')/rel) for rel in current['files'] if rel.startswith('editions/2026-10-19/') and '/article.html' in rel}
  transaction=native._json_sha({'content_sha256':identity,'attempt':attempt})
  revision=current.get('revision',0)+1
  save(tx/'publication-only-repair-reason.json',{'actor':'Codex / 01a117d1-cc86-737e-a3f1-28b9a724802e','utc':datetime.now(timezone.utc).isoformat(),
   'reason':'Restore current October 19 homepage coverage after authorized October 16 image backfill; factual content and reviews unchanged',
   'previous_receipt_sha256':sha(today/'production-publication-receipt.json')})
  package(tx,'2026-10-19',NEW,stages,target_origin='https://seasonalmarketnews.com',continuity={'revision':revision,'revision_id':identity,'transaction_id':transaction})
  validate_staged_reviews(tx)
  save(tx/'production-stage.json',installer.prepare(tx/'publication-package'))
  verified=native._resume_or_publish(tx,repo,'/opt/smn-shadow/node/bin/node','/opt/smn-playwright/node_modules/playwright')
  manifest=read(tx/'publication-package/manifest.json')
  assert verified['status']=='live_verified' and verified['transaction_id']==transaction
  assert all(sha(Path('/var/www/smn')/rel)==digest for rel,digest in before.items())
  completed={**verified,'production_written':True,'publication_policy':'continuity-v1','revision':revision,'revision_id':identity,
   'transaction_id':transaction,'content_sha256':identity,'selection_fingerprint':manifest['selection_sha256'],'selection_status':manifest['selection_status'],
   'expected_symbols':manifest['expected_symbols'],'published_symbols':manifest['published_symbols'],'pending_symbols':manifest['pending_symbols'],
   'coverage_status':manifest['coverage_status'],'complete':manifest['complete'],'review_stages':stages,'transaction_root':str(tx),
   'latest_update':datetime.now(timezone.utc).isoformat()}
  save(tx/'coverage-receipt.json',completed);save(today/'production-publication-receipt.json',completed)
  return {'status':completed['status'],'transaction_root':str(tx),'receipt_sha256':sha(today/'production-publication-receipt.json'),'article_bytes_unchanged':True}

try:
 for timer in timers:
  if states[timer]['ActiveState']=='active':paused.append(timer);command('systemctl','stop',timer)
 until=time.monotonic()+20
 while not idle() and time.monotonic()<until:time.sleep(.25)
 assert idle(),'Existing service is running; no job stopped'
 with ExitStack() as held:
  for path in [Path('/var/lib/smn-dashboard/schedule-runs/scheduler.lock'),Path('/var/lib/smn-dashboard/schedule-runs/newsletter.lock'),
               daily/'controller.lock',daily/'2026-10-19/continuity-progress.lock',daily/'2026-10-19/continuity-delivery.lock']:
   assert path.is_file() and not path.is_symlink()
   handle=held.enter_context(path.open('rb'));fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert not Path('/var/lib/tradewave/release-state/smn-production-activation.lock').exists(),'Another publication owns activation'
  for row in assets:
   sym=row['symbol'];source=prepared/'results'/sym;target=root/'results'/sym;override=read(source/'decorative-hero-reuse.json')
   for name in ['decorative-hero-reuse.json','decorative-hero-source-receipt.json',override['hero']['url']]:
    assert not (target/name).exists()
    with (target/name).open('xb') as out:out.write((source/name).read_bytes())
   assert reuse.override(target)==override['hero']
  stages,_=native._eligible(root,'2026-10-16',prior['published_symbols'])
  assert set(stages)==set(prior['published_symbols']),'A previously public article no longer qualifies'
  receipt=native.publish_available(root,'2026-10-16','production',repo=repo,node='/opt/smn-shadow/node/bin/node',playwright='/opt/smn-playwright/node_modules/playwright')
  assert receipt['status']=='live_verified' and set(receipt['published_symbols'])==set(prior['published_symbols']) and receipt['pending_symbols']==prior['pending_symbols']
  result['oct16']={'status':receipt['status'],'transaction_root':receipt['transaction_root'],'receipt_sha256':sha(root/'production-publication-receipt.json')}
  save(record/'repair.json',result)
  result['oct19_home_restoration']=restore_latest_home()
  result['articles']=[]
  for row in assets:
   sym=row['symbol'];post=next(p for p in read(Path('/var/www/smn/posts.json')) if p.get('url')=='https://seasonalmarketnews.com/editions/2026-10-16/'+sym+'/article.html')
   assert post['hero_status']=='available' and row['asset_sha256']==sha(Path('/var/www/smn')/post['hero_image'].split('seasonalmarketnews.com/',1)[1])
   assert originals[sym]=={name:sha(root/'results'/sym/name) for name in originals[sym]}
   result['articles'].append({'symbol':sym,'status':'live_verified','url':post['url'],'hero_image':post['hero_image'],'asset_sha256':row['asset_sha256'],'original_factual_artifacts_unchanged':True,'retained_visual_warnings':row['retained_visual_warnings']})
  assert sha(mail)==mail_before,'Mail journal advanced; retain actual state'
  assert read(Path('/var/www/smn/coverage-status.json'))['edition_date']=='2026-10-19'
  result.update(status='live_verified',verified_utc=datetime.now(timezone.utc).isoformat(),mail_journal_unchanged=True)
except BaseException as error:
 result.update(status='incomplete_requires_reconciliation',error_type=type(error).__name__,error=str(error));raise
finally:
 errors=[]
 for timer in reversed(paused):
  try:command('systemctl','start',timer)
  except BaseException as error:errors.append(timer+': '+str(error))
 actual=timer_states()
 if actual!=states:errors.append('Timer states differ from original')
 result['timers_restored']=not errors
 if errors:result.update(timer_errors=errors,status='incomplete_requires_reconciliation')
 save(record/'timer-restoration.json',{'before':states,'after':actual,'errors':errors})
 save(record/'repair.json',result)
 print(json.dumps(result),flush=True)
