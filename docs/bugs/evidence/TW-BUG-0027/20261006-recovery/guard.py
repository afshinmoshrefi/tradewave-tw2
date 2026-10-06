"""One-run guard for the proposed Oct 6 recovery. Importing this module does nothing.

Wrap the installed smn_models.run and Day.run_job only in the approved recovery
process. The installed subscription dispatcher and validators remain authoritative.
The six-attempt bound counts subscription job dispatches, not hidden HTTP retries
inside the provider's CLI. No recovery runner or deployment action lives here.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os

DATE = '2026-10-06'
SOURCE_SHA = '2d1de1a9c9f200fa29a2db7f9660f3527727b660'
MAX_ATTEMPTS = 6
BASELINE_COMPLETED = 40
PHASE_JOBS = {
    'cost': {
        'COST-20261006-hero-check': ('hero-check', 'gpt-6-luna', 'low'),
        'COST-20261006-visual': ('visual', 'gpt-6-luna', 'low'),
    },
    'xlk': {
        'XLK-20261006-reinspect-review': ('reinspect-review', 'gpt-6-sol', 'medium'),
        'XLK-20261006-hero-check': ('hero-check', 'gpt-6-luna', 'low'),
        'XLK-20261006-visual': ('visual', 'gpt-6-luna', 'low'),
        'EDITION-20261006-landing-visual': ('landing-visual', 'gpt-6-luna', 'low'),
    },
}


class GuardStop(BaseException):
    """Escape installed except-Exception retry loops; publisher still rolls back."""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def utc():
    return datetime.now(timezone.utc).isoformat()


def sync_directory(path):
    if os.name == 'posix':
        fd = os.open(str(path), os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def exclusive_json(path, value):
    path = Path(path)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    sync_directory(path.parent)


class SixAttemptGuard:
    def __init__(self, ledger, contract, dispatch, validate):
        self.ledger = Path(ledger).resolve()
        self.contract = contract
        self.dispatch = dispatch
        self.validate = validate
        if contract.get('date') != DATE or contract.get('source_sha') != SOURCE_SHA:
            raise GuardStop('Wrong date or installed release')
        if contract.get('max_attempts') != MAX_ATTEMPTS or contract.get('cumulative_ceiling') != 46:
            raise GuardStop('Wrong recovery ceiling')
        if len(contract.get('baseline_receipts', {})) != BASELINE_COMPLETED:
            raise GuardStop('Exactly 40 frozen completed receipts required')
        self.roots = {k: Path(v).resolve() for k, v in contract['roots'].items()}
        if set(self.roots) != {'original', 'cost', 'xlk'} or len(set(self.roots.values())) != 3:
            raise GuardStop('Three distinct retained roots required')
        if len({v.parent for v in self.roots.values()}) != 1 or self.roots['original'].name != 'chatgpt':
            raise GuardStop('Recovery roots must be retained siblings of chatgpt')
        if self.ledger in self.roots.values() or any(v in self.ledger.parents for v in self.roots.values()):
            raise GuardStop('Attempt ledger must remain outside copied edition roots')
        self.allowed = {}
        for phase, jobs in PHASE_JOBS.items():
            for name, spec in jobs.items():
                self.allowed[name] = (self.roots[phase], spec)
        self._verify_source()
        if self.ledger.exists():
            if self.ledger.is_symlink() or read(self.ledger/'contract.json') != contract:
                raise GuardStop('Existing guard contract differs; preserve it')
        else:
            self.ledger.mkdir()
            exclusive_json(self.ledger/'contract.json', contract)
        self.assert_open()

    def _verify_source(self):
        pins = self.contract.get('source_files', {})
        if not pins:
            raise GuardStop('Installed dispatch source pins required')
        for name, expected in pins.items():
            path = Path(name)
            if path.is_symlink() or not path.is_file() or sha(path) != expected:
                raise GuardStop('Installed dispatch source changed')

    def _records(self):
        return [read(p) for p in sorted(self.ledger.glob('attempt-*.json'))]

    def assert_open(self):
        if (self.ledger/'STOP.json').exists():
            raise GuardStop('A prior attempt or validation failed; approval/reconciliation required')
        if (self.ledger/'lease').exists():
            raise GuardStop('Guard lease exists; preserve live or interrupted owner')
        for row in self._records():
            completion = self.ledger/('complete-'+row['job_id']+'.json')
            if not completion.is_file():
                raise GuardStop('A reserved attempt is unresolved; never repeat it automatically')
        self._verify_source()

    def _stop(self, reason):
        try:
            exclusive_json(self.ledger/'STOP.json', {'utc': utc(), 'reason': reason})
        except FileExistsError:
            pass
        raise GuardStop(reason)

    @contextmanager
    def lease(self):
        self.assert_open()
        path = self.ledger/'lease'
        try:
            path.mkdir()
        except FileExistsError:
            raise GuardStop('Another guard owns the dispatch lease')
        try:
            # A second process could have passed assert_open before this lease.
            if (self.ledger/'STOP.json').exists():
                raise GuardStop('Guard stopped before lease acquisition')
            for row in self._records():
                if not (self.ledger/('complete-'+row['job_id']+'.json')).is_file():
                    raise GuardStop('Unresolved attempt after lease acquisition')
            yield
        finally:
            path.rmdir()
            sync_directory(self.ledger)

    def _job(self, job):
        raw = Path(job)
        if raw.is_symlink() or raw.parent.is_symlink() or raw.parent.parent.is_symlink():
            self._stop('Symlinked job path refused')
        path = raw.resolve()
        if path.parent.name != 'jobs' or path.parent.parent not in {self.roots['cost'], self.roots['xlk']}:
            self._stop('Job is outside approved recovery copies')
        return path

    def _cached_receipt(self, job):
        receipt_path = job/'receipt.json'
        if receipt_path.is_symlink():
            self._stop('Symlinked receipt refused')
        expected = self.contract['baseline_receipts'].get(job.name)
        completion = self.ledger/('complete-'+job.name+'.json')
        if completion.is_file():
            expected = read(completion)['receipt_sha256']
        if not expected or sha(receipt_path) != expected:
            self._stop('Cached receipt differs from original or guarded completion')

    def wrap_day_run_job(self, original):
        guard = self
        def guarded(day, job):
            guard.assert_open()
            path = guard._job(job)
            phase = 'cost' if path.parent.parent == guard.roots['cost'] else 'xlk'
            if Path(day.root).resolve() != path.parent.parent or day.date != DATE:
                guard._stop('Day or job scope differs')
            if day.max_jobs != (42 if phase == 'cost' else 46):
                guard._stop('Phase cumulative ceiling differs')
            if (path/'receipt.json').exists():
                guard._cached_receipt(path)
            try:
                return original(day, path)
            except GuardStop:
                raise
            except BaseException:
                guard._stop('Installed day dispatch failed; no retry authorized')
        return guarded

    def __call__(self, job, clis):
        try:
            with self.lease():
                path = self._job(job)
                expected = self.allowed.get(path.name)
                if not expected or path.parent.parent != expected[0]:
                    self._stop('Unapproved job or phase')
                if len(self._records()) >= MAX_ATTEMPTS:
                    self._stop('Six-attempt allowance exhausted')
                reservation = self.ledger/('attempt-'+path.name+'.json')
                if reservation.exists() or (path/'receipt.json').exists():
                    self._stop('Duplicate dispatch refused; preserve existing evidence')
                if (path/'job.json').is_symlink():
                    self._stop('Symlinked job manifest refused')
                manifest = read(path/'job.json')
                stage, model, effort = expected[1]
                checks = {'job_id':path.name,'stage':stage,'model':model,'effort':effort,
                          'provider':'openai','publish':False,'web_search':False}
                if any(manifest.get(k) != v for k,v in checks.items()):
                    self._stop('Job provider, model, effort or permissions differ')
                exclusive_json(reservation, {'job_id':path.name,'job_root':str(path),
                    'utc':utc(),'job_sha256':sha(path/'job.json'),'status':'attempt_reserved'})
                try:
                    receipt = self.dispatch(path, clis)
                    actual = read(path/'receipt.json')
                    if receipt != actual:
                        raise ValueError('Returned receipt differs from persisted receipt')
                    for key,value in {'job_id':path.name,'stage':stage,'model_requested':model,
                                      'effort_requested':effort,'billing_source':'subscription',
                                      'api_fallback':False,'new_external_provider_calls':0}.items():
                        if actual.get(key) != value:
                            raise ValueError('Receipt scope or billing mismatch')
                    if (actual.get('input_hashes') != manifest.get('input_hashes') or
                            actual.get('evidence_sha256') != manifest.get('evidence_sha256') or
                            actual.get('output_sha256') != sha(path/'output.json')):
                        raise ValueError('Receipt is not bound to this output and evidence')
                    self.validate(path, manifest, actual)
                    exclusive_json(self.ledger/('complete-'+path.name+'.json'),
                        {'job_id':path.name,'utc':utc(),'receipt_sha256':sha(path/'receipt.json'),
                         'output_sha256':actual['output_sha256'],'status':'validated_dispatch'})
                    return receipt
                except BaseException:
                    self._stop('Dispatched attempt or hard validation failed; no retry authorized')
        except GuardStop:
            raise
        except BaseException:
            self._stop('Guard failed closed before or after dispatch')


def installed_validator(job, manifest, receipt):
    """Use real immutable-job checks; never invent content or visual approval."""
    from editorial_gate import completed_job, verify_review
    output = completed_job(job)
    stage = manifest['stage']
    if stage == 'reinspect-review':
        verify_review(job.parent.parent/'results/XLK', job/'output.json')
    elif stage in {'visual','landing-visual'}:
        if output.get('passed') is not True or any(
                row.get('severity') in {'major','blocker'} for row in output.get('defects',[])):
            raise ValueError('Independent visual review did not pass')
    elif stage != 'hero-check':
        raise ValueError('Unexpected validation stage')
    # Hero wording remains report-only under the installed owner policy.
