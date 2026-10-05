"""Run the separately approved retained October 5 recovery, then normal publication."""
import json,sys,shutil,tempfile
from pathlib import Path
from datetime import datetime,timezone
SHA='08f871493a639a504b49794d78315d223b87a870'
repo=Path('/opt/smn-subscription/releases')/SHA
sys.path.insert(0,str(repo/'blog'))
from smn_held_recovery import recover,hashes
from smn_subscription_daily import lock
from smn_subscription_publish import publish_edition
from subscription_publication import read,write,digest_bytes
from operational_schedule import verified_reader_urls
from install_smn_primary_edition import configure_production,guard

def immutable_copy(source,target):
    raw=source.read_bytes()
    if target.exists():
        if target.read_bytes()!=raw:raise ValueError('Existing canonical evidence differs: '+str(target))
    else:
        with target.open('xb') as out:out.write(raw)

def main():
    approval=read(Path(sys.argv[1]))
    if (approval.get('date')!=datetime.now(timezone.utc).date().isoformat() or approval.get('source_commit')!=SHA or
        approval.get('execute_production_repair') is not True or not approval.get('approved_by')):
        raise ValueError('Current exact release approval required')
    maximum=approval.get('max_cumulative_jobs',40)
    if type(maximum) is not int or maximum<46:raise ValueError('Explicit cumulative job cap of at least 46 required')
    configure_production();guard()
    base=Path('/var/lib/tradewave/smn-daily/subscription-primary');date='2026-10-05'
    original=base/date/'chatgpt';target=base/date/'chatgpt-recovery-08f8714'
    canonical=original/'production-publication-receipt.json'
    saved=read(target/'production-publication-receipt.json') if (target/'production-publication-receipt.json').exists() else {}
    # Resume finalization after a crash without repeating generation or publication.
    result=read(target/'held-recovery.json')['result'] if saved.get('status')=='live_verified' else recover(original,target,['SI'],['NVDA'],maximum)
    if result['passed'] is not True:raise ValueError('Recovery held; inspect retained daily-check and jobs; no publication')
    with lock(base):
        ledger=read(target/'held-recovery.json')
        if ledger['max_jobs']!=maximum:raise ValueError('Recovery allowance changed')
        current=hashes(original)
        assert all(current.get(k)==v for k,v in ledger['original_files'].items()),'Original evidence changed'
        assert set(current)-set(ledger['original_files']) <= {'primary/SI.txt','primary/SI.receipt.json','recovery-resolution.json','production-publication-receipt.json'},'Unexpected canonical additions'
        receipt=saved if saved.get('status')=='live_verified' else publish_edition(target,date,max_jobs=maximum)
        assert receipt['status']=='live_verified' and len(receipt['urls'])==6
        # Prove the newsletter contract before exposing its canonical ready receipt.
        with tempfile.TemporaryDirectory(prefix='smn-oct5-verify-') as staging:
            check=Path(staging)/date
            (check/'inputs').mkdir(parents=True)
            shutil.copy2(base/date/'inputs/input-selection.json',check/'inputs/input-selection.json')
            shutil.copy2(base/date/'schedule-settings.json',check/'schedule-settings.json')
            shutil.copytree(target/'primary',check/'chatgpt/primary')
            write(check/'chatgpt/production-publication-receipt.json',receipt)
            assert verified_reader_urls(Path(staging),date),'Live selected article/source proof failed'
        # Append the missing SI capture only; never replace original failed jobs or four approved articles.
        for name in ('SI.txt','SI.receipt.json'):
            immutable_copy(target/'primary'/name,original/'primary'/name)
        receipt={**receipt,'recovery_root':str(target),'recovery_source_commit':SHA}
        resolution={'status':'live_verified','date':date,'recovery_root':str(target),
                    'source_commit':SHA,'jobs_used':sum(p.is_dir() for p in (target/'jobs').iterdir())+sum(1 for p in (target/'jobs').glob('*/failed-attempt-*')),
                    'original_files':ledger['original_files'],'publication':receipt}
        if (base/'last-run.json').exists() and not (target/'original-controller-last-run.json').exists():
            immutable_copy(base/'last-run.json',target/'original-controller-last-run.json')
        write(original/'recovery-resolution.json',resolution)
        write(canonical,receipt)
        assert verified_reader_urls(base,date),'Live selected article/source proof failed'
        previous=read(target/'original-controller-last-run.json') if (target/'original-controller-last-run.json').exists() else {}
        write(base/'last-run.json',{**previous,'utc':datetime.now(timezone.utc).isoformat(),'date':date,
            'status':'completed','exit_code':0,'target':'production','reader_publication_status':'live_verified',
            'recovery_root':str(target),'previous_run':str(target/'original-controller-last-run.json'),
            'result':{'publication_requested':True,'providers':{'chatgpt':{**result,'publication':receipt}}}})
        print(json.dumps({'status':'live_verified','date':date,'urls':receipt['urls'],'recovery_root':str(target)}))
if __name__=='__main__':main()
