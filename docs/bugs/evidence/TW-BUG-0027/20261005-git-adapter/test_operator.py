"""Offline Linux acceptance probes for the owner-provided cutover script.

All systemd/git calls are mocked and all files live in TemporaryDirectory.
Never invokes the real script CLI, network, provider, or production services.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import fcntl
import multiprocessing
import os
from pathlib import Path
import tempfile
import signal
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch


def load(path):
    spec = importlib.util.spec_from_file_location('cutover_under_review', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Fixture:
    def __init__(self, source):
        self.temp = tempfile.TemporaryDirectory(prefix='smn-cutover-independent-')
        root = self.root = Path(self.temp.name)
        c = self.c = load(source)
        c.__file__=str(root/'cutover.py')
        (root/'cutover.py').write_bytes(source.read_bytes())
        (root/'smn-production-freshness-check.py').write_text('Isolated checker process placeholder')
        if c.SHA is None:c.SHA='32bd869c0ffdd6039145bcaee4223dd67fb533ff'
        c.BASE = root/'runtime'
        c.CURRENT = c.BASE/'current'
        c.REPO = c.BASE/'releases'/c.SHA
        c.STATE = root/'release-state'
        c.LOCK = c.STATE/'smn-production-activation.lock'
        c.ACTIVATION = root/'config/subscription-primary.json'
        c.UNITS = root/'units'
        c.DAILY = root/'daily'
        c.MAIL_STATE = root/'mail/journal.json'
        c.MAIL_LEDGERS = root/'schedule-runs'
        c.MAIL_LEDGERS.mkdir()
        c.CODEX=root/'codex-fixture';c.CODEX.write_text('Isolated executable placeholder');c.CODEX.chmod(0o700)
        c.PYTHON=sys.executable
        c.GIT_ADAPTER=root/'bin/git';c.GIT_ADAPTER.parent.mkdir();c.GIT_ADAPTER.write_bytes(c.GIT_ADAPTER_BYTES);c.GIT_ADAPTER.chmod(0o755)
        c.CONTINUITY_PATH=str(c.GIT_ADAPTER.parent)+':/usr/bin:/bin'
        for path in (c.REPO/'blog', c.BASE/'releases'/c.OLD/'blog', c.STATE,
                     c.UNITS, c.DAILY, c.MAIL_STATE.parent):
            path.mkdir(parents=True, exist_ok=True)
        c.CURRENT.symlink_to(c.BASE/'releases'/c.OLD)
        c.save(c.ACTIVATION, {'source_commit':c.OLD})
        c.save(c.MAIL_STATE, {'daily_sent':['previous'], 'campaigns':{}})
        c.save(c.DAILY/'2026-10-05/chatgpt/production-publication-receipt.json',
               {'status':'live_verified','edition_date':'2026-10-05','urls':['https://seasonalmarketnews.com/editions/2026-10-05/'+s+'/article.html' for s in ('XLF','SI','SPY','QQQ','AMZN','NVDA')]})
        for name in c.EXISTING:
            (c.UNITS/(name+'.service')).write_text(str(c.BASE/'releases'/c.OLD/'blog'))
        templates = c.REPO/'ops/smn-continuity-production'
        templates.mkdir(parents=True)
        for name in ('smn-continuity@.service','smn-continuity@.timer'):
            (templates/name).write_text('Isolated service fixture\n')
        self.calls = []
        self.active = {u:False for u in c.SERVICES}
        self.timer_state = {u:{'enabled':u in [x+'.timer' for x in c.EXISTING],
                               'active':u in [x+'.timer' for x in c.EXISTING]} for u in c.TIMERS}
        self.interrupted = []
        self.freshness_passes=True
        c.run = self.run
        c.active = lambda unit:self.active.get(unit, self.timer_state.get(unit,{}).get('active',False))
        c.enabled = lambda unit:self.timer_state.get(unit,{}).get('enabled',False)
        c.loaded = lambda unit:True
        c.unit_info = self.unit_info
        c.git = lambda repo,*args:c.SHA if args == ('rev-parse','HEAD') else ''
        c.verify_archive_equivalence=lambda *args:{'files':0,'mocked_only_for_control_flow_probe':True}
        # The catalog hash is a production snapshot field, never read its absolute path here.
        actual_sha = c.sha
        c.sha = lambda p: 'isolated-catalog' if str(p)=='/var/www/smn/posts.json' else actual_sha(p)
        self.baseline = c.snapshot()
        self.record = c.STATE/'smn-continuity-isolated'
        self.record.mkdir()
        (self.record/'backup').mkdir()
        for text,digest in self.baseline['files'].items():
            if digest:
                (self.record/'backup'/hashlib.sha256(text.encode()).hexdigest()).write_bytes(Path(text).read_bytes())
        self.receipt = {'source_commit':c.SHA,'status':'prepared','baseline':self.baseline,'planned':{}}
        c.save(self.record/'receipt.json', self.receipt)

    def apply_args(self):
        c=self.c
        bundle=self.root/'release.bundle';bundle.write_text('isolated bundle')
        archive=self.root/'source.tar';archive.write_text('isolated archive')
        approval=self.root/'approval.json';manifest=self.root/'manifest.json';baseline=self.root/'baseline.json'
        native=self.root/'native-proof.json';browser=self.root/'browser-proof.json'
        pixel=self.root/'pixel-proof.json';qualification=self.root/'qualification.json'
        screenshot=self.root/'inspected.png';screenshot.write_bytes(b'isolated screenshot identity')
        c.save(baseline,{'captured_utc':datetime.now(timezone.utc).isoformat(),'state':self.baseline})
        c.save(native,{'source_commit':c.SHA,'source_archive_sha256':c.sha(archive),
                       'network_disabled':True,'provider_model_email_calls':0,
                       'revisions':[{'coverage':name,'complete':name=='complete',
                                     'native_prepare_and_temp_activation':True,'rollback_exact':True}
                                    for name in ('notice','partial','complete')]})
        c.save(browser,{'source_commit':c.SHA,'native_proof_sha256':c.sha(native),
                        'offline_fixture':True,'all_requests_fulfilled_from_fixture':True,
                        'public_production_verification':False,'pages':[{'passed':True}]*18})
        c.save(pixel,{'source_commit':c.SHA,'browser_proof_sha256':c.sha(browser),
                      'offline_fixture':True,'public_production_verification':False,
                      'visually_inspected':[{'name':screenshot.name,'sha256':c.sha(screenshot)}],
                      'calls':{'model':0,'email':0,'provider':0}})
        c.save(qualification,{'source_commit':c.SHA,'browser_pages':18,'pixel_inspected':1,
                              'proofs':{p.name:c.sha(p) for p in (native,browser,pixel)}})
        c.save(approval,{'source_commit':c.SHA,'date':datetime.now(timezone.utc).date().isoformat(),
                         'approved_by':'offline-test-only','execute_production_continuity':True,
                         'production_web_snapshot':True,'production_app_snapshot':True,'publication_policy':'continuity-v1',
                         'baseline_sha256':c.sha(baseline),'preserved_campaign_id':'200497784617437041',
                         'operator_script_sha256':c.sha(c.__file__),'approve_existing_git_adapter_dropin':True})
        c.save(manifest,{'source_commit':c.SHA,'bundle_sha256':c.sha(bundle),'source_archive_sha256':c.sha(archive),
                        'freshness_check_sha256':c.sha(self.root/'smn-production-freshness-check.py'),
                        'qualification_manifest_sha256':c.sha(qualification)})
        return SimpleNamespace(approval=approval,manifest=manifest,baseline=baseline,bundle=bundle,
                               source_archive=archive,qualification=qualification,native_proof=native,
                               browser_proof=browser,pixel_proof=pixel)

    def run(self,*args):
        self.calls.append(list(args))
        if len(args)>2 and args[:2]==('systemctl','show') and args[-2:]==('Environment','--value'):
            return 'PATH='+self.c.CONTINUITY_PATH
        if args == ('hostname','-I'):
            return '209.182.216.112'
        if args and args[0]==self.c.PYTHON:
            assert args[1]==str(self.root/'smn-production-freshness-check.py')
            return json.dumps({'complete_edition_verified':self.freshness_passes,
                               'receipt_sha256':self.baseline['oct5_receipt_sha256'],
                               'active_release':str(self.c.REPO),'articles':[{}]*6})
        if args[:2] == ('systemctl','stop'):
            unit=args[2]
            if unit.endswith('.service') and self.active.get(unit):self.interrupted.append(unit)
            self.active[unit]=False
            if unit in self.timer_state:self.timer_state[unit]['active']=False
        elif args[:2] == ('systemctl','start'):
            self.active[args[2]]=True
        return ''

    def unit_info(self, unit):
        if unit in [name+'.service' for name in self.c.CONTINUITY]:
            return {'WorkingDirectory':str(self.c.CURRENT/'blog'),'User':'root'}
        path=self.c.UNITS/unit
        return {'FragmentPath':str(path),'DropInPaths':'','WorkingDirectory':path.read_text(), 'User':'root'}

    def close(self):
        self.temp.cleanup()


def changed_journal_holds_legacy_mail(f):
    c=f.c
    c.save(c.MAIL_STATE, {'daily_sent':['previous'],'campaigns':{'new':{'campaign_id':'fixture-provider-id','status':'scheduled'}}})
    expected=c.MAIL_STATE.read_bytes()
    c.restore(f.record,f.receipt)
    assert c.MAIL_STATE.read_bytes()==expected, 'Rollback overwrote campaign journal'
    restarted=[call[2] for call in f.calls if call[:2]==['systemctl','start'] and call[2] in ['smn-subscription.timer','smn-weekday-newsletter.timer']]
    assert not restarted, 'Rollback restarted legacy mail-capable timers: '+repr(restarted)
    return {'journal_preserved':True,'legacy_mail_paths_held':True}


def peer_file_change_is_preserved(f):
    c=f.c
    c.ACTIVATION.write_text('peer-owned edit')
    try:c.restore(f.record,f.receipt)
    except ValueError as error:
        assert 'Peer changed' in str(error),str(error)
    else:raise AssertionError('Rollback accepted a peer-owned file change')
    assert c.ACTIVATION.read_text()=='peer-owned edit'
    assert not any(call[:2]==['systemctl','stop'] for call in f.calls)
    return {'refused_peer_drift_without_stopping_services':True}


def live_peer_lock_is_preserved(f):
    c=f.c;c.LOCK.mkdir()
    c.save(c.LOCK/'owner.json',{'source_commit':c.SHA,'pid':os.getpid(),'task':'live-peer','record':str(f.record)})
    before=(c.LOCK/'owner.json').read_bytes()
    try:c.rollback(SimpleNamespace(record=f.record, recover=False))
    except (ValueError,FileExistsError,RuntimeError):pass
    else:raise AssertionError('Rollback took a live peer lock')
    assert (c.LOCK/'owner.json').read_bytes()==before
    assert not any(call[:2]==['systemctl','stop'] for call in f.calls)
    return {'live_peer_preserved':True}


def report_dead_owner_recovery(f):
    c=f.c;c.LOCK.mkdir()
    c.save(c.LOCK/'owner.json',{'source_commit':c.SHA,'pid':99999999,'task':'TW-BUG-0027-production-continuity','record':str(f.record)})
    f.receipt.update(status='rollback_required',rollback_error='Isolated process interruption')
    c.save(f.record/'receipt.json',f.receipt)
    c.rollback(SimpleNamespace(record=f.record, recover=True))
    assert not c.LOCK.exists(), 'Recovered transaction retained its lock'
    assert c.read(f.record/'receipt.json')['status'].startswith('rolled_back')
    return {'dead_owner_recovered':True}


def no_interrupt_between_check_and_timer_stop(f):
    c=f.c
    args=f.apply_args()
    real_copy=c.shutil.copy2
    def copy_then_timer_starts(*args,**kwargs):
        result=real_copy(*args,**kwargs)
        f.active['smn-weekday-newsletter.service']=True
        return result
    outcome=None
    with patch.object(c.shutil,'copy2',side_effect=copy_then_timer_starts):
        try:c.apply(args)
        except Exception as error:outcome=type(error).__name__+': '+str(error)
    assert not f.interrupted,'Cutover interrupted a mail-capable service started after activity check: '+repr(f.interrupted)
    assert outcome is not None,'Concurrent mail did not cause a safe refusal'
    return {'active_send_not_interrupted':True,'refusal':outcome}


def legacy_ledger_change_holds_both_mail_paths(f):
    c=f.c
    original=c.sha(c.MAIL_STATE)
    c.save(c.MAIL_LEDGERS/'production-sunday_summary-2026-10-04.json',{'status':'running','uncertain_provider_outcome':True})
    c.restore(f.record,f.receipt)
    assert c.sha(c.MAIL_STATE)==original
    restarted=[call[2] for call in f.calls if call[:2]==['systemctl','start'] and call[2] in ['smn-subscription.timer','smn-weekday-newsletter.timer']]
    assert not restarted,repr(restarted)
    assert f.receipt['manual_provider_reconciliation_required'] is True
    return {'ledger_only_uncertainty_holds_both_entrypoints':True}


def held_scheduler_locks_block_cutover(f):
    c=f.c;args=f.apply_args();checked=[]
    for name in ('scheduler.lock','newsletter.lock'):
        with (c.MAIL_LEDGERS/name).open('a') as peer:
            fcntl.flock(peer,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try:c.apply(args)
            except BlockingIOError:pass
            else:raise AssertionError('Cutover ignored existing '+name)
        assert not c.LOCK.exists()
        assert not any(call[:2]==['systemctl','stop'] for call in f.calls)
        assert all(c.metadata(path)==value for path,value in f.baseline['files'].items())
        checked.append(name)
    return {'real_linux_flock_contention_refused':checked}


def killed_process_recovers_exact_transaction(f):
    c=f.c
    def interrupted_child():
        c.claim_lock(f.record,'TW-BUG-0027-production-continuity')
        data=json.dumps({'source_commit':c.SHA,'publication_policy':'continuity-v1'}).encode()
        prior=f.receipt['baseline']['files'][str(c.ACTIVATION)]
        f.receipt['planned'][str(c.ACTIVATION)]={**prior,'sha256':hashlib.sha256(data).hexdigest()}
        c.save(f.record/'receipt.json',f.receipt)
        c.atomic(c.ACTIVATION,data)
        c.point(c.REPO)
        os.kill(os.getpid(),signal.SIGKILL)
    child=multiprocessing.get_context('fork').Process(target=interrupted_child)
    child.start();child.join(5)
    if child.is_alive():child.terminate();child.join();raise AssertionError('Isolated crash fixture did not terminate')
    assert child.exitcode==-signal.SIGKILL,child.exitcode
    assert c.CURRENT.resolve()==c.REPO
    c.rollback(SimpleNamespace(record=f.record,recover=True))
    assert not c.LOCK.exists() and c.CURRENT.resolve()==c.BASE/'releases'/c.OLD
    assert all(c.metadata(path)==value for path,value in f.baseline['files'].items())
    return {'sigkill_exit_code':child.exitcode,'exact_files_metadata_pointer_restored':True,'dead_lock_recovered':True}


def pointer_failure_rolls_back(f):
    c=f.c;args=f.apply_args();original_run=c.run;injected=False
    def fail_after_pointer(*command):
        nonlocal injected
        if command==('systemctl','daemon-reload') and not injected:
            injected=True;raise RuntimeError('Isolated daemon reload failure after pointer move')
        return original_run(*command)
    c.run=fail_after_pointer
    try:c.apply(args)
    except RuntimeError as error:assert 'Isolated daemon reload failure' in str(error)
    else:raise AssertionError('Fault not reached')
    assert injected
    assert not c.LOCK.exists() and c.CURRENT.resolve()==c.BASE/'releases'/c.OLD
    assert all(c.metadata(path)==value for path,value in f.baseline['files'].items())
    assert c.sha(c.MAIL_STATE)==f.baseline['mail_state_sha256']
    return {'post_pointer_failure_restored_exact_baseline':True,'journal_preserved':True}


def changed_proof_is_rejected(f):
    c=f.c;args=f.apply_args()
    browser=c.read(args.browser_proof);browser['source_commit']='0'*40;c.save(args.browser_proof,browser)
    try:c.approve(c.read(args.approval),c.read(args.manifest),args.bundle,args.source_archive,
                  args.baseline,args.qualification,args.native_proof,args.browser_proof,args.pixel_proof)
    except ValueError:pass
    else:raise AssertionError('Changed browser proof accepted')
    assert not any(call and call[0]=='systemctl' for call in f.calls)
    return {'changed_qualification_refused_before_mutation':True}


def final_content_failure_rolls_back_before_new_timers(f):
    c=f.c;args=f.apply_args();c.apply(args)
    record=c.STATE/('smn-continuity-'+c.SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat())
    assert c.read(record/'receipt.json')['status']=='source_activated_timers_held'
    assert not any(call[:2] in (['systemctl','start'],['systemctl','enable']) for call in f.calls)
    f.freshness_passes=False
    try:c.finalize(SimpleNamespace(record=record))
    except ValueError as error:assert 'content/links failed' in str(error),str(error)
    else:raise AssertionError('Failed content check accepted')
    assert c.read(record/'receipt.json')['status']=='rolled_back'
    assert c.CURRENT.resolve()==c.BASE/'releases'/c.OLD and not c.LOCK.exists()
    assert not any(call[:2] in (['systemctl','start'],['systemctl','enable']) and call[2].startswith('smn-continuity@') for call in f.calls)
    assert all(c.metadata(path)==value for path,value in f.baseline['files'].items())
    return {'failed_content_rolls_back':True,'no_new_timer_enabled_or_started':True}


def final_content_success_precedes_new_timers(f):
    c=f.c;args=f.apply_args();c.apply(args)
    record=c.STATE/('smn-continuity-'+c.SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat())
    assert not any(call[:2] in (['systemctl','start'],['systemctl','enable']) for call in f.calls)
    c.finalize(SimpleNamespace(record=record))
    final=c.read(record/'receipt.json')
    assert final['status']=='active_verified' and final['live_postcheck']['complete_edition_verified']
    check_index=next(i for i,call in enumerate(f.calls) if call and call[0]==c.PYTHON)
    new_starts=[i for i,call in enumerate(f.calls) if call[:2]==['systemctl','start'] and call[2].startswith('smn-continuity@')]
    assert len(new_starts)==3 and all(i>check_index for i in new_starts)
    assert not c.LOCK.exists()
    return {'new_timers_start_only_after_bound_content_pass':True,'content_result_recorded':True,
            'note':'Checker process response mocked; the checker itself has eight separate false-success tests.'}


def changed_git_adapter_is_refused_before_mutation(f):
    c=f.c;args=f.apply_args()
    c.GIT_ADAPTER.chmod(0o777)
    try:c.apply(args)
    except ValueError as error:assert 'Git adapter' in str(error)
    else:raise AssertionError('Writable adapter accepted')
    c.GIT_ADAPTER.chmod(0o755);c.GIT_ADAPTER.write_bytes(b'changed helper')
    try:c.apply(args)
    except ValueError as error:assert 'Git adapter' in str(error)
    else:raise AssertionError('Changed helper accepted')
    assert not c.LOCK.exists() and not any(call[:2]==['systemctl','stop'] for call in f.calls)
    return {'writable_and_changed_adapter_refused_before_mutation':True}


def missing_service_adapter_rolls_back_before_timers(f):
    c=f.c;args=f.apply_args();c.apply(args)
    record=c.STATE/('smn-continuity-'+c.SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat())
    original=c.run
    def wrong_path(*args):
        if len(args)>2 and args[:2]==('systemctl','show') and args[-2:]==('Environment','--value'):
            return 'PATH=/usr/bin:/bin'
        return original(*args)
    c.run=wrong_path
    try:c.finalize(SimpleNamespace(record=record))
    except ValueError as error:assert 'Git adapter' in str(error)
    else:raise AssertionError('Wrong effective service PATH accepted')
    assert c.read(record/'receipt.json')['status']=='rolled_back'
    assert not c.continuity_git_dropin().exists()
    assert c.CURRENT.resolve()==c.BASE/'releases'/c.OLD and not c.LOCK.exists()
    assert not any(call[:2] in (['systemctl','start'],['systemctl','enable']) and call[2].startswith('smn-continuity@') for call in f.calls)
    return {'bad_effective_path_rolls_back_before_enabling_continuity':True}


def new_git_dropin_is_managed_and_rolled_back(f):
    c=f.c;args=f.apply_args();c.apply(args)
    record=c.STATE/('smn-continuity-'+c.SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat())
    receipt=c.read(record/'receipt.json');path=c.continuity_git_dropin()
    assert receipt['baseline']['files'][str(path)] is None and c.metadata(path)==receipt['planned'][str(path)]
    assert path.read_text()=='[Service]\nEnvironment=PATH='+c.CONTINUITY_PATH+'\n'
    c.rollback(SimpleNamespace(record=record))
    assert not path.exists() and c.CURRENT.resolve()==c.BASE/'releases'/c.OLD
    assert all(c.metadata(path)==value for path,value in f.baseline['files'].items())
    return {'added_git_dropin_owned_by_transaction_and_removed_on_rollback':True}


def peer_git_dropin_change_is_preserved(f):
    c=f.c;args=f.apply_args();c.apply(args)
    record=c.STATE/('smn-continuity-'+c.SHA[:12]+'-'+datetime.now(timezone.utc).date().isoformat())
    path=c.continuity_git_dropin();path.write_text('peer-owned new setting')
    try:c.rollback(SimpleNamespace(record=record))
    except ValueError as error:assert 'Peer changed' in str(error)
    else:raise AssertionError('Peer adapter drop-in overwritten')
    assert path.read_text()=='peer-owned new setting'
    assert c.read(record/'receipt.json')['status']=='rollback_required' and c.LOCK.exists()
    return {'peer_git_dropin_preserved_and_explicit_rollback_required':True}


def original_approval_cannot_authorize_amended_operator(f):
    c=f.c;args=f.apply_args();approval=c.read(args.approval)
    approval.pop('operator_script_sha256');approval.pop('approve_existing_git_adapter_dropin')
    c.save(args.approval,approval)
    try:c.apply(args)
    except ValueError as error:assert 'authorization' in str(error)
    else:raise AssertionError('Original approval silently authorized amended operator')
    assert not c.LOCK.exists() and not any(call[:2]==['systemctl','stop'] for call in f.calls)
    return {'original_approval_refused_before_mutation':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);args=parser.parse_args()
    checks=[]
    for check in (changed_journal_holds_legacy_mail,peer_file_change_is_preserved,
                  live_peer_lock_is_preserved,report_dead_owner_recovery,no_interrupt_between_check_and_timer_stop,
                  legacy_ledger_change_holds_both_mail_paths,held_scheduler_locks_block_cutover,
                  killed_process_recovers_exact_transaction,pointer_failure_rolls_back,changed_proof_is_rejected,
                  final_content_failure_rolls_back_before_new_timers,final_content_success_precedes_new_timers,
                  changed_git_adapter_is_refused_before_mutation,missing_service_adapter_rolls_back_before_timers,
                  new_git_dropin_is_managed_and_rolled_back,peer_git_dropin_change_is_preserved,
                  original_approval_cannot_authorize_amended_operator):
        f=Fixture(args.source)
        try:
            with contextlib.redirect_stdout(io.StringIO()):details=check(f)
            checks.append({'name':check.__name__,'passed':True,'details':details})
        except Exception as error:checks.append({'name':check.__name__,'passed':False,'error':type(error).__name__+': '+str(error)})
        finally:f.close()
    print(json.dumps({'captured_at_utc':datetime.now(timezone.utc).isoformat(),
                      'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
                      'isolated_linux_files':True,'all_external_calls_mocked':True,
                      'production_actions':False,'checks':checks,'passed':all(x['passed'] for x in checks)},indent=2))


if __name__=='__main__':main()
