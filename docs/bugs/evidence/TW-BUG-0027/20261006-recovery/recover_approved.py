"""One-time approved content recovery. No application/service deployment or send.

No action without --execute. Original edition is retained byte-for-byte. Real model
dispatches use the separately qualified guard and existing installed validators.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys

from guard import SixAttemptGuard, GuardStop, installed_validator, SOURCE_SHA, DATE, sha, read, exclusive_json

BASE=Path('/var/lib/tradewave/smn-daily/subscription-primary')
DAY=BASE/DATE
ORIGINAL=DAY/'chatgpt'
COST=DAY/'chatgpt-recovery-cost-20261006'
FINAL=DAY/'chatgpt-recovery-six-20261006'
LEDGER=DAY/'bounded-recovery-20261006'
SOURCE=Path('/opt/smn-subscription/releases')/SOURCE_SHA
APPROVAL={'source_thread_id':'01a0f25f-c964-7675-91ca-caa44db7c0c4',
          'approved_utc':'2026-10-06T10:37:00+00:00','user_response':'yes run it',
          'scope':'up to six additional subscription jobs; cumulative 46; reuse existing articles/images; complete six-article production content recovery; no newsletter send, paid fallback, research/writing/hero generation or deployment'}


def emit(stage,**fields):
    print(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'stage':stage,**fields}),flush=True)


def lock(path):
    handle=Path(path).open('r')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:handle.close();raise
    return handle


def tree_hashes(root):
    result={}
    for path in root.rglob('*'):
        if path.is_symlink():raise GuardStop('Symlinked original evidence refused')
        if path.is_file():result[path.relative_to(root).as_posix()]=sha(path)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:raise SystemExit('Explicit approved --execute required; no action performed')
    package=Path(__file__).resolve().parent
    pins=read(package/'production-inputs.json')
    if sha(package/'guard.py')!=pins['guard_sha256']:raise GuardStop('Qualified guard bytes differ')
    if Path('/opt/smn-subscription/current').resolve()!=SOURCE:raise GuardStop('Active application changed')
    for name,digest in pins['source_file_hashes'].items():
        if sha(SOURCE/'blog'/name)!=digest:raise GuardStop('Inspected installed source changed: '+name)
    for key,value in pins['runtime_environment'].items():os.environ[key]=value
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    os.environ['GIT_OPTIONAL_LOCKS']='0'
    os.chdir(SOURCE/'blog');sys.path.insert(0,str(SOURCE/'blog'))
    if subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()!=SOURCE_SHA:
        raise GuardStop('Installed checkout SHA differs')
    if subprocess.check_output(['git','-C',str(SOURCE),'status','--porcelain','--untracked-files=no'],text=True).strip():
        raise GuardStop('Installed tracked source is dirty')
    if any(p.exists() for p in [COST,FINAL,LEDGER,Path('/var/lib/tradewave/release-state/smn-production-activation.lock')]):
        raise GuardStop('Existing recovery or publication ownership must be reconciled')

    handles=[];controller=None;original_files=None;result=None
    try:
        for name in ['scheduler.lock','newsletter.lock']:
            handles.append(lock(Path('/var/lib/smn-dashboard/schedule-runs')/name))
        controller=lock(BASE/'controller.lock')
        last=read(BASE/'last-run.json')
        if last.get('date')!=DATE or last.get('status')=='running':raise GuardStop('Original controller not finished')
        processes=subprocess.check_output(['ps','-eo','args'],text=True)
        if any(any(x in line for x in ['smn_subscription_daily.py','smn_held_recovery.py']) for line in processes.splitlines()):
            raise GuardStop('Another reader/recovery process is active')
        if (ORIGINAL/'production-publication-receipt.json').exists():raise GuardStop('Canonical publication already exists')
        catalog=read('/var/www/smn/posts.json')
        if any(str(p.get('published_date',''))[:10]==DATE for p in catalog):raise GuardStop('Today is already in public catalog')
        if sha(ORIGINAL/'smn-daily-state.json')!=pins['reader_state_sha256'] or sha(ORIGINAL/'HOLD.json')!=pins['reader_hold_sha256']:
            raise GuardStop('Reader state changed since diagnosis')
        original_files=tree_hashes(ORIGINAL)
        baseline_receipts={p.parent.name:sha(p) for p in (ORIGINAL/'jobs').glob('*/receipt.json')}
        if baseline_receipts!=pins['baseline_receipts']:raise GuardStop('Frozen completed receipts differ')
        import smn_models,smn_daily,smn_held_recovery
        from editorial_gate import verify_complete,verify_review
        from subscription_publication import selected_lineup,complete_lineup
        from smn_subscription_publish import publish_edition
        from subscription_writer import save_json
        symbols=selected_lineup(ORIGINAL,DATE,required=True)
        if symbols!=['CPRT','APH','XLK','IBM','MSFT','COST']:raise GuardStop('Selection changed')
        for sym in ['CPRT','APH','IBM','MSFT']:verify_complete(ORIGINAL/'results'/sym)
        verify_review(ORIGINAL/'results/COST',ORIGINAL/'jobs/COST-20261006-rereview/output.json')
        # The original receipt stays absent: newsletter eligibility is not released.
        mail=Path('/home/flask/blog/logs/sent_smn_emails.json')
        mail_before=sha(mail) if mail.exists() else None
        LEDGER.mkdir(mode=0o700)
        exclusive_json(LEDGER/'approval.json',APPROVAL)
        exclusive_json(LEDGER/'original-files.json',original_files)
        exclusive_json(LEDGER/'original-controller-last-run.json',last)
        exclusive_json(LEDGER/'baseline.json',{'mail_sha256':mail_before,'catalog_sha256':sha('/var/www/smn/posts.json'),
                       'source_commit':SOURCE_SHA,'symbols':symbols,'original_jobs':len(baseline_receipts)})
        contract={'date':DATE,'source_sha':SOURCE_SHA,'max_attempts':6,'cumulative_ceiling':46,
                  'roots':{'original':str(ORIGINAL),'cost':str(COST),'xlk':str(FINAL)},
                  'baseline_receipts':baseline_receipts,
                  'source_files':{str(SOURCE/'blog'/n):h for n,h in pins['source_file_hashes'].items()}}
        guard=SixAttemptGuard(LEDGER/'attempts',contract,smn_models.run,installed_validator)
        real_prepare=smn_models.prepare
        def scoped_prepare(roles,role,*a,**kw):
            if kw.get('stage')=='reinspect-review':
                a=list(a)
                a[2]+=('\nIndependent reinspection instruction: in editorial_audit.claims[].source_quote, '
                       'use one continuous verbatim passage from the cited captured primary page. '
                       'Do not join separate excerpts with ellipses. This source-quotation requirement '
                       'is distinct from the coverage ledger\'s article_quote format. Evaluate every '
                       'hard check independently; fail if evidence is insufficient. Do not rewrite '
                       'the article or inherit any earlier verdict.\n')
            return real_prepare(roles,role,*a,**kw)
        smn_models.prepare=scoped_prepare
        smn_models.run=guard
        smn_daily.Day.run_job=guard.wrap_day_run_job(smn_daily.Day.run_job)
        shutil.copytree(ORIGINAL,COST)
        state=read(COST/'smn-daily-state.json')
        day=smn_daily.Day(COST,DATE,profile='chatgpt',roles=state['roles'],max_jobs=42,
                          publication_origin='https://seasonalmarketnews.com')
        before={s:day._approved_snapshot(s) for s in ['CPRT','APH','IBM','MSFT']}
        day.symbols=symbols
        emit('cost_visual_start',completed_attempts=0)
        day.visual()
        verify_complete(COST/'results/COST')
        for sym,expected in before.items():
            if day._approved_snapshot(sym)!=expected:raise GuardStop('Approved article changed: '+sym)
        if tree_hashes(ORIGINAL)!=original_files:raise GuardStop('Original failed edition changed')
        emit('cost_complete',attempts=len(guard._records()))
        controller.close();controller=None
        # Installed helper acquires its own controller flock; scheduler exclusion remains held.
        plan=smn_held_recovery.plan(COST,rereview=['XLK'],max_jobs=46)
        if not plan['budget_sufficient'] or plan['minimum_total_jobs']!=46:raise GuardStop('Recovery plan differs from six-attempt approval')
        emit('xlk_reinspection_start',remaining_minimum=plan['minimum_new_jobs'])
        recovered=smn_held_recovery.recover(COST,FINAL,rereview=['XLK'],max_jobs=46)
        if recovered.get('passed') is not True:raise GuardStop('Reinspection did not complete the six subjects')
        controller=lock(BASE/'controller.lock')
        for sym in symbols:verify_complete(FINAL/'results'/sym)
        complete_lineup(FINAL,DATE,symbols,required=True)
        if len(guard._records())!=5:raise GuardStop('Exactly five prepublication attempts expected')
        if tree_hashes(ORIGINAL)!=original_files:raise GuardStop('Original failed edition changed before publication')
        emit('six_articles_verified',attempts=5)
        receipt=publish_edition(FINAL,DATE,max_jobs=46)
        if receipt.get('status')!='live_verified' or len(guard._records())!=6:raise GuardStop('Publication or attempt count incomplete')
        for sym in symbols:verify_complete(FINAL/'results'/sym)
        if tree_hashes(ORIGINAL)!=original_files:raise GuardStop('Original failed edition changed after publication')
        if (sha(mail) if mail.exists() else None)!=mail_before:raise GuardStop('Mail journal changed during content-only recovery')
        if (ORIGINAL/'production-publication-receipt.json').exists():raise GuardStop('Unexpected canonical newsletter release')
        result={'utc':datetime.now(timezone.utc).isoformat(),'status':'live_verified','edition_date':DATE,
                'source_commit':SOURCE_SHA,'recovery_root':str(FINAL),'original_root':str(ORIGINAL),
                'publication_receipt_sha256':sha(FINAL/'production-publication-receipt.json'),
                'attempts':len(guard._records()),'cumulative_jobs':46,'original_failed_edition_unchanged':True,
                'newsletter_released':False,'mail_journal_unchanged':True,'urls':receipt['urls']}
        exclusive_json(LEDGER/'result.json',result)
        exclusive_json(DAY/'recovery-resolution.json',result)
        # Preserve the authentic scheduled failure above; mark content recovery explicitly.
        save_json(BASE/'last-run.json',{**last,'utc':result['utc'],'status':'recovered',
                  'reader_publication_status':'live_verified','recovery_root':str(FINAL),
                  'newsletter_released':False,'original_last_run':str(LEDGER/'original-controller-last-run.json')})
        emit('recovery_complete',**result)
    except BaseException as exc:
        if LEDGER.exists():
            failure={'utc':datetime.now(timezone.utc).isoformat(),'status':'stopped',
                     'error_type':type(exc).__name__,'reason':str(exc)[:700],
                     'original_unchanged':tree_hashes(ORIGINAL)==original_files if original_files is not None else None}
            if not (LEDGER/'failure.json').exists():exclusive_json(LEDGER/'failure.json',failure)
            emit('recovery_stopped',**failure)
        raise
    finally:
        if controller is not None:controller.close()
        for handle in reversed(handles):handle.close()
    return result


if __name__=='__main__':main()
