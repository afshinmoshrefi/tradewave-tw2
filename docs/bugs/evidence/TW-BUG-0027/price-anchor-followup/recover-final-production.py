"""Continue the held October 5 edition after a separately approved matcher fix.

This wrapper is deliberately pinned to the retained October 5 recovery roots. It
does not install code, grant approval, or publish a partial edition.
"""
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


DATE = '2026-10-05'
SHA = '2d1de1a9c9f200fa29a2db7f9660f3527727b660'
BASE = Path('/var/lib/tradewave/smn-daily/subscription-primary')
ORIGINAL = BASE/DATE/'chatgpt'
PRIOR = BASE/DATE/'chatgpt-citation-recovery-2cc3167'
CURRENT = Path('/opt/smn-subscription/current')
ACTIVATION = Path('/etc/SMN/subscription-primary.json')
PUBLICATION_FILES = {'publication-package', 'production-stage.json',
    'production-publication-receipt.json', 'primary-stage.json',
    'primary-activation.json', 'primary-activation-attempt.json',
    'dev-stage.json', 'dev-activation.json', 'dev-publication-receipt.json',
    'live-verification.json', 'live-landing-visual-checks.json',
    'live-landing-visual-failed.json', 'committed-source',
    'committed-source.tar', 'publication-package.tar'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def immutable_copy(source, target):
    raw = source.read_bytes()
    if target.exists():
        require(target.read_bytes() == raw, 'Existing canonical evidence differs: '+str(target))
    else:
        with target.open('xb') as output:
            output.write(raw)


def original_matches(saved, hasher, finalizing=False):
    current = hasher(ORIGINAL)
    if any(current.get(name) != digest for name, digest in saved.items()):
        return False
    additions = set(current)-set(saved)
    allowed = {'primary/SI.txt', 'primary/SI.receipt.json',
               'recovery-resolution.json', 'production-publication-receipt.json'}
    return not additions if not finalizing else additions <= allowed


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: recover-final-production.py APPROVAL.json RELEASE.json')
    approval_path, manifest_path = map(Path, sys.argv[1:])
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    sha = manifest.get('source_commit')
    require(sha == SHA, 'Final matcher release manifest differs from exact approved candidate')
    require(approval.get('date') == datetime.now(timezone.utc).date().isoformat() and
            approval.get('source_commit') == sha and approval.get('approved_by') and
            approval.get('execute_production_repair') is True and
            approval.get('production_web_snapshot') is True and
            approval.get('production_app_snapshot') is True,
            'Current exact release approval and TODAY web/app snapshots required')
    maximum = approval.get('max_cumulative_jobs')
    require(type(maximum) is int and maximum >= 49,
            'Separate approval for at least 49 cumulative jobs required')
    repo = Path('/opt/smn-subscription/releases')/sha
    require(CURRENT.resolve() == repo.resolve() and repo.is_dir(), 'Active code pointer differs')
    require(json.loads(ACTIVATION.read_text(encoding='utf-8'))['source_commit'] == sha,
            'Activation source commit differs')
    sys.path.insert(0, str(repo/'blog'))
    from smn_daily import Day, now
    from smn_subscription_daily import lock
    from smn_held_recovery import hashes
    from smn_subscription_publish import publish_edition
    from subscription_publication import read, write, selected_lineup
    from operational_schedule import verified_reader_urls
    from install_smn_primary_edition import configure_production, guard
    from editorial_gate import verify_complete, verify_review

    configure_production()
    guard()
    target = BASE/DATE/('chatgpt-final-recovery-'+sha[:7])
    canonical = ORIGINAL/'production-publication-receipt.json'
    require(PRIOR.is_dir() and ORIGINAL.is_dir(), 'Retained edition evidence missing')
    with lock(BASE):
        prior_ledger = read(PRIOR/'citation-recovery.json')
        require(prior_ledger.get('status') == 'held' and
                set(prior_ledger.get('result', {}).get('held', [])) == {'SI'},
                'Prior citation recovery must be held on SI alone')
        saved_receipt_path = target/'production-publication-receipt.json'
        saved = read(saved_receipt_path) if saved_receipt_path.exists() else {}
        finalizing = saved.get('status') == 'live_verified'
        require(prior_ledger['source_root'] == str(BASE/DATE/'chatgpt-recovery-08f8714') and
                prior_ledger['source_commit'] == '2cc3167a435065843bb2b8834a750e7213fb75ec' and
                prior_ledger['max_jobs'] == 49 and
                original_matches(prior_ledger['original_files'], hashes, finalizing),
                'Original evidence or citation recovery ledger changed')
        require(hashes(Path(prior_ledger['source_root'])) == prior_ledger['prior_files'],
                'Earlier retained recovery evidence changed')
        state = read(PRIOR/'smn-daily-state.json')
        symbols = selected_lineup(PRIOR, DATE, required=True)
        require(len(symbols) == 6 and {'SI', 'NVDA'} <= set(symbols), 'Selected lineup differs')
        probe = Day(PRIOR, DATE, profile=state['profile'], roles=state['roles'],
                    max_jobs=maximum, publication_origin=state.get('publication_origin'))
        require(probe.jobs_used() == 46, 'Expected 46 retained job attempts')
        require(probe.jobs_used()+3 <= maximum, 'Insufficient cumulative job budget')
        approved = dict(prior_ledger['approved_articles'])
        require(set(approved) == set(symbols)-{'SI', 'NVDA'}, 'Original four snapshots missing')
        nvda = state['articles']['NVDA']
        require(nvda.get('finalized') is True and not nvda.get('held'), 'NVDA is not finalized')
        approved['NVDA'] = probe._approved_snapshot('NVDA')
        require(set(approved) == set(symbols)-{'SI'}, 'Five approved snapshots missing')
        require(all(probe._approved_snapshot(sym) == snapshot for sym, snapshot in approved.items()),
                'Approved article evidence changed')
        for sym in approved:
            verify_complete(PRIOR/'results'/sym)
        si = state['articles']['SI']
        require(si.get('held') and si.get('finalized') is False and
                si.get('editorially_finalized') is False and
                si.get('draft') == 'write' and
                si.get('mechanical_ok') is True and
                si.get('review_stage') == 'reinspect-review', 'SI saved state differs')
        si_review = PRIOR/'jobs'/('SI-'+DATE.replace('-', '')+'-reinspect-review')/'output.json'
        require(si_review.is_file(), 'SI saved independent review missing')
        verify_review(PRIOR/'results'/'SI', si_review)
        prior_files = hashes(PRIOR)
        request = {'source_commit': sha, 'date': DATE, 'source_root': str(PRIOR),
                   'original_root': str(ORIGINAL), 'max_jobs': maximum,
                   'retry': {'SI': 'saved-passing-reinspection-only'},
                   'prior_files': prior_files, 'original_files': prior_ledger['original_files'],
                   'approved_articles': approved, 'expected_symbols': symbols}
        ledger_path = target/'final-recovery.json'
        if target.exists():
            require(ledger_path.is_file(), 'Unrecorded final recovery; preserve and inspect it')
            ledger = read(ledger_path)
            require(all(ledger.get(k) == v for k, v in request.items()),
                    'Recovery request or saved source hashes changed')
        else:
            shutil.copytree(PRIOR, target, ignore=lambda folder, names:
                            list(set(names) & PUBLICATION_FILES) if Path(folder) == PRIOR else [])
            ledger = {**request, 'utc': now(), 'status': 'prepared'}
            write(ledger_path, ledger)
        day = Day(target, DATE, profile=state['profile'], roles=state['roles'],
                  max_jobs=maximum, publication_origin=state.get('publication_origin'))
        require(day.jobs_used() == 46 or ledger['status'] != 'prepared',
                'Copied job ledger lost attempts')
        if ledger['status'] == 'prepared':
            row = day.state['articles']['SI']
            row.pop('held', None)
            row['finalized'] = False
            day.save()
            ledger['status'] = 'running'
            write(ledger_path, ledger)
        require(ledger['status'] in {'running', 'held', 'ready_for_publication', 'live_verified'},
                'Unexpected recovery status')
        if ledger['status'] != 'live_verified' and saved.get('status') != 'live_verified':
            try:
                day.symbols = ['SI']
                day.articles()
                day.visual()
                day.symbols = symbols
                result = day.check()
                ledger.update(status='ready_for_publication' if result['passed'] else 'held',
                              result=result, jobs_used_after=day.jobs_used())
                write(ledger_path, ledger)
                require(result['passed'] is True, 'Recovery held; no publication')
            except BaseException as exc:
                ledger.update(status='held', failure=str(exc)[:500], jobs_used_after=day.jobs_used())
                write(ledger_path, ledger)
                write(target/'final-recovery-failure.json', {'utc': now(), 'status': 'held',
                                                       'reason': str(exc)[:500]})
                raise
        else:
            result = ledger['result']
            require(result['passed'] is True, 'Saved recovery result is held')
        require(day.jobs_used() <= maximum, 'Cumulative job cap exceeded')
        require(all(day._approved_snapshot(sym) == snapshot for sym, snapshot in approved.items()),
                'Approved article changed')
        require(hashes(PRIOR) == prior_files and
                hashes(Path(prior_ledger['source_root'])) == prior_ledger['prior_files'] and
                original_matches(prior_ledger['original_files'], hashes, finalizing),
                'Prior or original evidence changed')
        if ledger['status'] == 'live_verified':
            require(saved.get('status') == 'live_verified' and
                    read(canonical) == ledger['publication'] and
                    verified_reader_urls(BASE, DATE),
                    'Completed recovery receipt or live proof changed')
            print(json.dumps({'status': 'live_verified', 'date': DATE,
                              'urls': saved['urls'], 'recovery_root': str(target)}))
            return
        try:
            receipt = saved if saved.get('status') == 'live_verified' else publish_edition(target, DATE, max_jobs=maximum)
            require(receipt['status'] == 'live_verified' and len(receipt['urls']) == 6,
                    'Publication not verified for six URLs')
            with tempfile.TemporaryDirectory(prefix='smn-oct5-final-verify-') as staging:
                check = Path(staging)/DATE
                (check/'inputs').mkdir(parents=True)
                shutil.copy2(BASE/DATE/'inputs/input-selection.json', check/'inputs/input-selection.json')
                shutil.copy2(BASE/DATE/'schedule-settings.json', check/'schedule-settings.json')
                shutil.copytree(target/'primary', check/'chatgpt/primary')
                write(check/'chatgpt/production-publication-receipt.json', receipt)
                require(verified_reader_urls(Path(staging), DATE), 'Live selected article/source proof failed')
            for name in ('SI.txt', 'SI.receipt.json'):
                immutable_copy(target/'primary'/name, ORIGINAL/'primary'/name)
            receipt = {**receipt, 'recovery_root': str(target), 'recovery_source_commit': sha}
            resolution = {'status': 'live_verified', 'date': DATE, 'recovery_root': str(target),
                          'source_commit': sha, 'jobs_used': day.jobs_used(),
                          'original_files': prior_ledger['original_files'], 'publication': receipt}
            if canonical.exists():
                require(read(canonical) == receipt, 'Existing canonical receipt differs')
            if (BASE/'last-run.json').exists() and not (target/'original-controller-last-run.json').exists():
                immutable_copy(BASE/'last-run.json', target/'original-controller-last-run.json')
            resolution_path = ORIGINAL/'recovery-resolution.json'
            if resolution_path.exists():
                require(read(resolution_path) == resolution, 'Existing recovery resolution differs')
            else:
                write(resolution_path, resolution)
            if not canonical.exists():
                write(canonical, receipt)
            require(verified_reader_urls(BASE, DATE), 'Canonical live proof failed')
            previous = read(target/'original-controller-last-run.json') if (target/'original-controller-last-run.json').exists() else {}
            write(BASE/'last-run.json', {**previous, 'utc': datetime.now(timezone.utc).isoformat(),
                'date': DATE, 'status': 'completed', 'exit_code': 0, 'target': 'production',
                'reader_publication_status': 'live_verified', 'recovery_root': str(target),
                'previous_run': str(target/'original-controller-last-run.json'),
                'result': {'publication_requested': True,
                           'providers': {'chatgpt': {**result, 'publication': receipt}}}})
            ledger.update(status='live_verified', publication=receipt, jobs_used_after=day.jobs_used())
            write(ledger_path, ledger)
            print(json.dumps({'status': 'live_verified', 'date': DATE,
                              'urls': receipt['urls'], 'recovery_root': str(target)}))
        except BaseException as exc:
            ledger.update(status='held', failure=str(exc)[:500], jobs_used_after=day.jobs_used())
            write(ledger_path, ledger)
            write(target/'final-recovery-failure.json', {'utc': now(), 'status': 'held',
                                                   'reason': str(exc)[:500]})
            raise


if __name__ == '__main__':
    main()
