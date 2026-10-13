"""Optional volume export after the existing authoritative EOD success proof."""
from datetime import datetime,timezone
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
from data_updater.eod_readiness import (validate_success_marker,
    latest_completed_us_equity_session)
from appserver.appserver import highest_volume_stocks as engine
from appserver.appserver.volume_feed_protocol import (FILES,COMMIT,SHA,canonical,digest,
    build_bundle,validate_bundle,timestamp,atomic,delivery_lock,NY)


def completion_proof(path, *, now):
    raw=Path(path).read_bytes();marker=json.loads(raw)
    if not validate_success_marker(marker,
        expected_completed_session=latest_completed_us_equity_session(now).isoformat()):
        raise ValueError('Engine EOD completion is not currently verified')
    completed_at=timestamp(marker['completed_at'])
    if not 0 <= (now-completed_at).total_seconds() <= 96*3600:
        raise ValueError('Engine completion clock is future or stale')
    if marker['completed_session']>=now.astimezone(NY).date().isoformat():
        raise ValueError('Date-only volume export requires a prior completed session')
    return {'ok':True,'marker_sha256':digest(raw),
        'generation_fingerprint':marker['generation_fingerprint'],
        'completed_session':marker['completed_session'],
        'completed_at':marker['completed_at']}


def prepare_attempt(marker_path,state_directory,source_commit,*,now,calculate=None):
    proof=completion_proof(marker_path,now=now)
    if not COMMIT.fullmatch(source_commit):
        raise ValueError('Immutable source revision required')
    state=Path(state_directory)
    if state.is_symlink():
        raise ValueError('Unsafe exporter state directory')
    state.mkdir(parents=True,exist_ok=True)
    key=digest(canonical({'completion_proof':proof,'source_commit':source_commit,
                         'export_market_date':now.astimezone(NY).date().isoformat()}))
    with delivery_lock(state):
        attempt=state/key
        if attempt.is_symlink():
            raise ValueError('Unsafe exporter attempt')
        attempt.mkdir(exist_ok=True)
        cached=attempt/'bundle.json'
        if cached.exists():
            if cached.is_symlink():
                raise ValueError('Unsafe exporter bundle')
            bundle=json.loads(cached.read_text());validate_bundle(bundle,now=now)
            for item in bundle['files'].values():
                if item['provenance']['completion_proof']!=proof or item['provenance']['source_commit']!=source_commit:
                    raise ValueError('Cached source/session binding differs')
            return bundle,attempt
        observations={}
        (calculate or engine.get_highest_volume_US_stocks)(observations=observations)
        # Preserve the exact CSV bytes emitted by the existing engine, including
        # its supplied rounding/ranks. No financial values are recalculated here.
        directory=Path(engine.config.csv_folder)/'US'
        raw_files={name:(directory/name).read_bytes() for name in FILES}
        bundle=build_bundle(raw_files,observations,proof,source_commit,now=now)
        atomic(cached,canonical(bundle))
        return bundle,attempt


def acknowledgement_target(source_peer,receiver_module_sha256):
    if not isinstance(source_peer,str) or str(ipaddress.ip_address(source_peer))!=source_peer:
        raise ValueError('Exact intended producer peer IP required')
    if not isinstance(receiver_module_sha256,str) or not SHA.fullmatch(receiver_module_sha256):
        raise ValueError('Exact intended receiver module hash required')


def validate_acknowledgement(receipt,bundle,*,now,source_peer,receiver_module_sha256):
    acknowledgement_target(source_peer,receiver_module_sha256)
    if not isinstance(receipt,dict):
        raise ValueError('Receiver acknowledgement must be an object')
    expected={name:item['provenance']['csv_sha256'] for name,item in bundle['files'].items()}
    counts={name:len(item['provenance']['observations']) for name,item in bundle['files'].items()}
    if receipt.get('status')!='verified' or receipt.get('delivery_id')!=bundle['delivery_id'] or receipt.get('csv_sha256')!=expected:
        raise ValueError('Receiver acknowledgement does not bind this payload')
    received_counts=receipt.get('row_counts')
    if not isinstance(received_counts,dict) or received_counts!=counts or any(type(value) is not int for value in received_counts.values()):
        raise ValueError('Receiver acknowledgement row counts differ')
    accepted=timestamp(receipt['received_at'])
    if accepted>now:
        raise ValueError('Receiver acknowledgement has a future clock')
    # Validate the immutable payload at its actual acceptance time. A saved
    # completion remains completed after the export expires; a fresh dispatch
    # below still requires validation against the current clock.
    validate_bundle(bundle,now=accepted)
    attribution=receipt.get('attribution')
    if not isinstance(attribution,dict) or attribution.get('source_peer_ip')!=source_peer or attribution.get('receiver_module_sha256')!=receiver_module_sha256:
        raise ValueError('Receiver acknowledgement attribution differs from intended target')
    return receipt


def send_bundle(bundle,url,*,post,attempt_directory,now,max_attempts=3,
                expected_source_peer=None,expected_receiver_module_sha256=None,clock=None):
    directory=Path(attempt_directory)
    with delivery_lock(directory):
        return _send_bundle_locked(bundle,url,post=post,attempt_directory=directory,
                                   now=now,max_attempts=max_attempts,
                                   expected_source_peer=expected_source_peer,
                                   expected_receiver_module_sha256=expected_receiver_module_sha256,
                                   clock=clock or (lambda:datetime.now(timezone.utc)))


def _send_bundle_locked(bundle,url,*,post,attempt_directory,now,max_attempts,
                        expected_source_peer,expected_receiver_module_sha256,clock):
    if type(max_attempts) is not int or not 1<=max_attempts<=3:
        raise ValueError('Upload retries must be one to three')
    acknowledgement_target(expected_source_peer,expected_receiver_module_sha256)
    directory=Path(attempt_directory)
    journal_path=directory/'delivery-attempts.json'
    if journal_path.is_symlink():
        raise ValueError('Unsafe upload journal')
    journal=json.loads(journal_path.read_text()) if journal_path.exists() else {'delivery_id':bundle['delivery_id'],'events':[]}
    if journal['delivery_id']!=bundle['delivery_id'] or not isinstance(journal.get('events'),list):
        raise ValueError('Upload journal differs from frozen payload')
    for index,event in enumerate(journal['events'],1):
        if not isinstance(event,dict) or type(event.get('number')) is not int or event['number']!=index or event.get('status') not in {'reserved','failed','acknowledged'}:
            raise ValueError('Malformed upload reservation history')
    receipt_path=directory/'receipt.json'
    if receipt_path.is_symlink():
        raise ValueError('Unsafe saved upload receipt')
    if receipt_path.exists():
        receipt=validate_acknowledgement(json.loads(receipt_path.read_text()),bundle,
            now=now,source_peer=expected_source_peer,
            receiver_module_sha256=expected_receiver_module_sha256)
        # Receipt is saved before journal completion. Recover that local crash
        # boundary using validated evidence, without reserving or dispatching.
        if journal['events'] and journal['events'][-1]['status']=='reserved':
            journal['events'][-1].update(status='acknowledged',http_status=200)
        if journal.get('status')!='acknowledged':
            journal['status']='acknowledged';atomic(journal_path,canonical(journal))
        return receipt
    validate_bundle(bundle,now=now)
    # The frozen payload is retained before dispatch. Receipt loss retries this
    # same identity, never a fresh export or a misleading success flag.
    for number in range(1,max_attempts+1):
        if len(journal['events'])>=9:
            raise RuntimeError('Daily frozen-export allowance of nine HTTP attempts exhausted')
        event={'number':len(journal['events'])+1,'status':'reserved'}
        journal['events'].append(event);journal['status']='in_progress';journal['attempts']=len(journal['events'])
        atomic(journal_path,canonical(journal))
        status=None
        try:
            response=post(url,json=bundle,timeout=(5,15),allow_redirects=False)
            status=response.status_code
            if response.status_code!=200:
                raise ValueError('Unexpected upload HTTP status')
            receipt=response.json()
            # Compare the receiver clock after HTTP completes, not against the
            # earlier invocation clock. Real delivery takes time.
            validate_acknowledgement(receipt,bundle,now=clock(),
                source_peer=expected_source_peer,receiver_module_sha256=expected_receiver_module_sha256)
            atomic(receipt_path,canonical(receipt))
            event.update(status='acknowledged',http_status=status)
            journal['status']='acknowledged';atomic(journal_path,canonical(journal))
            return receipt
        except Exception as error:
            event.update(status='failed',failure_type=type(error).__name__,http_status=status)
            journal['status']='failed';atomic(journal_path,canonical(journal))
    raise RuntimeError('Bounded optional-volume upload failed; retained frozen attempt')


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true',help='Read authoritative EOD proof only')
    parser.add_argument('--send',action='store_true',help='Enable intended internal upload')
    parser.add_argument('--marker',default=os.environ.get('TW2_EOD_UPDATE_STATUS_FILE','/var/lib/tradewave/eod/update_status.json'))
    parser.add_argument('--state-directory',default='/var/lib/tradewave/volume-export')
    args=parser.parse_args(argv);now=datetime.now(timezone.utc)
    if args.check:
        print(json.dumps(completion_proof(args.marker,now=now)));return 0
    if not args.send:
        parser.error('Use --check for read-only inspection or --send after release approval')
    source_peer=os.environ.get('TW2_VOLUME_SOURCE_PEER_IP')
    receiver_hash=os.environ.get('TW2_VOLUME_RECEIVER_MODULE_SHA256')
    acknowledgement_target(source_peer,receiver_hash)
    source=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain','--untracked-files=no'],text=True).strip():
        raise RuntimeError('Producer release has tracked changes')
    bundle,attempt=prepare_attempt(args.marker,args.state_directory,source,now=now)
    import requests
    url=engine.config.blog_queue_server.rstrip('/')+'/update_volume_lists'
    if not url.startswith(('http://','https://')):
        raise ValueError('Configured internal receiver is unavailable')
    receipt=send_bundle(bundle,url,post=requests.post,attempt_directory=attempt,now=now,
        expected_source_peer=source_peer,expected_receiver_module_sha256=receiver_hash)
    print(json.dumps({'status':receipt['status'],'delivery_id':receipt['delivery_id']}))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
