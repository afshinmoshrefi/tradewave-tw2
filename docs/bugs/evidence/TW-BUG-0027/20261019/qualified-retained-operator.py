"""Exact b61 -> 678477ab SMN app refresh. Preparation/preflight is read-only.

Apply requires new exact-artifact approval, fresh baseline, independent Linux
source qualification and real Linux operator custody qualification. It changes
only the release pointer, activation source/record and existing legacy service
source paths. Continuity units/bounds, content, model jobs, mail and canonical
reader evidence are preserved. No running service is stopped or killed.
"""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
from contextlib import contextmanager
import argparse, hashlib, json, os, re, shutil, stat, subprocess, sys, tarfile, tempfile, time

NEW = '678477ab7fa1ab75f538dffef5d4dd854d8a11e0'
OLD = 'b61b37f7a6683f0fc173b8aef52bcd5067f6bbe5'
DATE = '2026-10-09'
TARGET_HOST, TARGET_IP = 'seasonalmarketnews', '209.182.216.112'
BASE = Path('/opt/smn-subscription')
CURRENT, RELEASE = BASE / 'current', BASE / 'releases' / NEW
OLD_RELEASE = BASE / 'releases' / OLD
ACTIVATION = Path('/etc/SMN/subscription-primary.json')
UNITS = Path('/etc/systemd/system')
STATE = Path('/var/lib/tradewave/release-state')
ACTIVATION_LOCK = STATE / 'smn-production-activation.lock'
RECORD = STATE / 'smn-app-refresh-678477ab-20261009-v3-r2'
DAILY = Path('/var/lib/tradewave/smn-daily/subscription-primary')
DAY = DAILY / DATE
PARENT_OWNER = DAY / 'chatgpt-formal-recovery-v1-20261009/parent-rpm-source-correction-owner.json'
PARENT_PID = 551935
PUBLIC_READER = DAY / 'chatgpt-three-publication-v1-20261009'
PUBLIC_RECEIPT = PUBLIC_READER / 'production-publication-receipt.json'
PUBLIC_RECEIPT_SHA = '771338548de7e67fb53a5385df8707c438d83b29162ee2e98cc72d1979d3a4d3'
NGINX = Path('/etc/nginx/sites-enabled/smn.conf')
# Exact writes by reconcile_tick_guard.run_tick and smn_recovery
# watch_workers/worker_start/worker_finish while the controller stays held.
OPERATIONAL = ['reconcile-tick-guard.json', 'continuity-supervision.json', 'continuity-workers/reconcile.json']
OPERATIONAL += ['chatgpt/automatic-recovery.json', 'continuity-recovery.json']
OPERATIONAL += ['continuity-workers/progress.json', 'continuity-workers/deliver.json']
HOME_CANDIDATE = STATE / 'smn-oct9-three-publication-v1-20261009/smn-production-2026-10-09-1f095b4d7eca494f/candidate/index.html'
HOME_ORIGINAL_SHA = '61ca773189406ee6ea4a50bcaa5ae3d9218f1e8e709b030fe9c879fccb90fc3e'
# Raw prefix+suffix after deletion of exactly one native span. Root's retained
# b65b comparison uses an explicit marker; the two methods are kept distinct.
HOME_OUTSIDE_SHA = 'c7ecf89fe5348933d5cf3a6ba2e9e090c5251da83193e3855d757d36a7b13762'
QUOTE_UPDATER_SHA = 'f5e7c436ff61ce630364eca5dab3ac75742ec8d50f2adb970526157226f30657'
QUOTE_PATTERN = rb'<div class="market-bar">.*?</div>\s*</div>'
PUBLISHED = ['XLF', 'DJI', 'RPM']
MAIL = Path('/home/flask/blog/logs/sent_smn_emails.json')
SCHEDULE = Path('/var/lib/smn-dashboard/schedule-runs')
RECONCILE_TIMER = 'smn-continuity@reconcile.timer'
LEGACY = ['smn-subscription.service', 'smn-weekday-newsletter.service']
CONTINUITY = ['smn-continuity@' + phase + '.service' for phase in ('progress', 'deliver', 'reconcile')]
SERVICES = LEGACY + CONTINUITY
TIMERS = [unit.replace('.service', '.timer') for unit in SERVICES]
SOURCE_REF = 'refs/heads/codex/smn-essential-advisory-20261009'
EXPECTED_PATCH = {'blog/editorial_gate.py', 'blog/engine_edition_workflow.py', 'blog/subscription_publication.py',
                  'blog/tests/test_essential_advisory_policy.py', 'docs/ESSENTIAL_ADVISORY_REVIEW.md'}
SAFE_TEXT = {'.py', '.cjs', '.js', '.md', '.txt', '.json', '.html', '.css', '.svg', '.service', '.timer', '.conf', '.yaml', '.yml', '.toml', '.sh'}
PROPERTIES = ['FragmentPath', 'DropInPaths', 'WorkingDirectory', 'User', 'LoadState', 'ActiveState', 'SubState',
              'TimeoutStartUSec', 'Restart', 'StartLimitIntervalUSec', 'KillMode', 'ExecStart', 'Environment', 'EnvironmentFiles']


def require(value, message):
    if not value:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def command(*args):
    return subprocess.check_output(list(args), text=True).strip()


def git(checkout, *args, binary=False):
    args = ['/usr/bin/sudo', '-u', 'flask', '/usr/bin/git', '-C', str(checkout), *args]
    return subprocess.check_output(args) if binary else subprocess.check_output(args, text=True).strip()


def metadata(path):
    path = Path(path)
    require(not path.is_symlink(), 'Managed file is a symlink: ' + str(path))
    if not path.exists():
        return None
    require(path.is_file(), 'Managed file is not regular: ' + str(path))
    info = path.stat()
    return {'sha256': sha(path), 'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}


def runtime_metadata(path):
    path = Path(path)
    if path == NGINX and path.is_symlink():
        target = path.resolve(strict=True)
        require(Path('/etc/nginx') in target.parents and not target.is_symlink(), 'Unexpected nginx link target')
        return {'kind': 'read-only-nginx-symlink', 'link_target': os.readlink(path), 'resolved_target': str(target),
                'link_uid': path.lstat().st_uid, 'link_gid': path.lstat().st_gid, 'target': metadata(target)}
    return metadata(path)


def inventory(root, exclude=()):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'Protected root missing/unsafe: ' + str(root))
    values = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Protected symlink requires classification: ' + str(path))
        if path.is_file() and str(path) not in exclude:
            values[path.relative_to(root).as_posix()] = sha(path)
    return values


def execstart_projection(raw, normalize=False):
    """One native systemd command; retain execution evidence outside config.

    Escaped/quoted argv, multiple commands, unexpected fields and alternate
    serializations require a separate reviewed grammar; never guess their intent.
    """
    require(isinstance(raw, str) and not any(char in raw for char in '\r\n\0'), 'Ambiguous ExecStart serialization')
    match = re.fullmatch(r'\{ (.+) \}', raw)
    require(match and '{' not in match[1] and '}' not in match[1], 'Exactly one native ExecStart command required')
    pairs = match[1].split(' ; ')
    fields = {}
    expected = {'path', 'argv[]', 'ignore_errors', 'start_time', 'stop_time', 'pid', 'code', 'status'}
    for pair in pairs:
        require('=' in pair, 'Ambiguous ExecStart field')
        key, value = pair.split('=', 1)
        require(key in expected and key not in fields and value and value == value.strip(), 'Unknown, duplicate or malformed ExecStart field')
        fields[key] = value
    require(set(fields) == expected, 'Incomplete native ExecStart fields')
    require(re.fullmatch(r'/[A-Za-z0-9_./+-]+', fields['path']), 'Unsupported ExecStart path syntax')
    require(re.fullmatch(r'[A-Za-z0-9_./:=+,%@-]+(?: [A-Za-z0-9_./:=+,%@-]+)*', fields['argv[]'])
            and fields['argv[]'].split(' ', 1)[0] == fields['path'], 'Unsupported or ambiguous ExecStart argv syntax')
    require(fields['ignore_errors'] in {'yes', 'no'}, 'Unknown ExecStart ignore_errors value')
    require(all(re.fullmatch(r'\[(?:n/a|[A-Za-z0-9:+./ -]+)\]', fields[key]) for key in ('start_time', 'stop_time')),
            'Unknown ExecStart execution-clock syntax')
    require(re.fullmatch(r'[0-9]+', fields['pid']) and int(fields['pid']) <= 2147483647, 'Unknown ExecStart PID syntax')
    require(fields['code'] in {'(null)', 'exited', 'killed', 'dumped', 'trapped', 'stopped', 'continued'}
            and re.fullmatch(r'[0-9]+(?:/[A-Za-z0-9_-]+)?', fields['status']), 'Unknown ExecStart execution-result syntax')
    config = {key: fields[key] for key in ('path', 'argv[]', 'ignore_errors')}
    if normalize:
        config = {key: value.replace(str(RELEASE), str(OLD_RELEASE)) for key, value in config.items()}
    return {'configuration': config, 'observation': {'raw': raw, 'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'execution': {key: fields[key] for key in ('start_time', 'stop_time', 'pid', 'code', 'status')}}}


def system_properties(unit, normalize=False):
    args = ['systemctl', 'show', unit]
    for key in PROPERTIES:
        args += ['-p', key]
    raw = {}
    for line in command(*args).splitlines():
        require('=' in line, 'Malformed systemctl property record')
        key, value = line.split('=', 1)
        require(key in PROPERTIES and key not in raw, 'Unknown or duplicate systemctl configuration property')
        raw[key] = value
    require(set(raw) == set(PROPERTIES), 'Missing requested systemctl configuration property')
    result = {}
    for key, value in raw.items():
        if key == 'ExecStart':
            projection = execstart_projection(value, normalize)
            result['ExecStart_configuration'] = projection['configuration']
            result['ExecStart_sha256'] = digest(projection['configuration'])
            result['ExecStart_observation'] = projection['observation']
            continue
        if normalize:
            value = value.replace(str(RELEASE), str(OLD_RELEASE))
        if key in {'Environment', 'EnvironmentFiles'}:
            result[key + '_sha256'] = hashlib.sha256(value.encode()).hexdigest()
        else:
            result[key] = value
    return result


def configured_services(services):
    # Timer attempts may clear a stale failed state while the owner holds the
    # controller. Effective configuration is exact; running state is guarded
    # separately and a running service is never interrupted.
    return {unit: {key: value for key, value in properties.items() if key not in {'ActiveState', 'SubState', 'ExecStart_observation'}}
            for unit, properties in services.items()}


def baseline_state(baseline):
    state = {key: value for key, value in baseline.items() if key not in {'captured_utc', 'operational', 'homepage_observation'} }
    state['services'] = configured_services(state['services'])
    return state


def artifact_digest(manifest):
    return digest({key: manifest[key] for key in ('source_commit', 'baseline_source_commit', 'operator_sha256', 'inputs')})


def timer_state(unit):
    return {'active': subprocess.run(['systemctl', 'is-active', '--quiet', unit]).returncode == 0,
            'enabled': subprocess.run(['systemctl', 'is-enabled', '--quiet', unit]).returncode == 0,
            'unit_file_state': command('systemctl', 'show', unit, '-p', 'UnitFileState', '--value')}


def no_running_services():
    for unit in SERVICES:
        info = system_properties(unit)
        require(info['ActiveState'] not in {'active', 'activating', 'deactivating', 'reloading'},
                'Running service retained; do not interrupt: ' + unit)


def flock_record(lines, device_inode):
    for line in lines:
        words = line.split()
        if 'FLOCK' not in words:
            continue
        start = words.index('FLOCK')
        if words[start:start + 3] != ['FLOCK', 'ADVISORY', 'WRITE'] or len(words) < start + 5:
            continue
        major, minor, inode = words[start + 4].split(':')
        if (int(major, 16), int(minor, 16), int(inode)) == device_inode:
            return True
    return False


def live_parent():
    value = read(PARENT_OWNER)
    require(value.get('pid') == PARENT_PID and value.get('status') == 'RPM_source_correction_complete'
            and value.get('exit_code') == 0 and value.get('mail_sends') == 0
            and value.get('baseline_actual_completed_jobs') == 38 and value.get('ceiling') == 40
            and value.get('maximum_new_starts') == 2 and value.get('prior_SPY_hold_retained') is True
            and value.get('script_sha256') == sha(PARENT_OWNER.parent / 'rpm_source_correction.py')
            and value.get('owner') == 'Direct human publication/repair task01a117d1-cc86-737e-a3f1-28b9a724802e',
            'Exact live current owner identity differs')
    os.kill(PARENT_PID, 0)
    require(not Path(value['release_signal']).exists(), 'Current owner release already requested')
    path = DAILY / 'controller.lock'
    require(path.is_file() and not path.is_symlink(), 'Controller lock missing/unsafe')
    info = path.stat()
    key = (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino)
    require(flock_record(Path('/proc/locks').read_text(encoding='utf-8').splitlines(), key), 'Controller flock absent')
    owned = []
    for descriptor in Path('/proc/' + str(PARENT_PID) + '/fd').iterdir():
        try:
            target = descriptor.stat()
            if (target.st_dev, target.st_ino) == (info.st_dev, info.st_ino) and flock_record(
                    Path('/proc/' + str(PARENT_PID) + '/fdinfo/' + descriptor.name).read_text(encoding='utf-8').splitlines(), key):
                owned.append(int(descriptor.name))
        except FileNotFoundError:
            continue
    require(owned, 'Exact live parent has no descriptor owning controller flock')
    return {'path': str(PARENT_OWNER), 'sha256': sha(PARENT_OWNER), 'value': value,
            'lock_device': info.st_dev, 'lock_inode': info.st_ino, 'descriptors': sorted(owned)}


def runtime_files():
    paths = {ACTIVATION, Path('/opt/smn-subscription/bin/git'), NGINX, CURRENT / 'blog/update_news_quotes.py'}
    for unit in SERVICES:
        props = system_properties(unit)
        for text in [props['FragmentPath'], *props['DropInPaths'].split()]:
            if text:
                path = Path(text)
                require(UNITS in path.parents and not path.is_symlink(), 'Unexpected effective unit path: ' + text)
                paths.add(path)
    for unit in TIMERS:
        for key in ('FragmentPath', 'DropInPaths'):
            value = command('systemctl', 'show', unit, '-p', key, '--value')
            for text in value.split():
                path = Path(text)
                require(UNITS in path.parents and not path.is_symlink(), 'Unexpected timer path: ' + text)
                paths.add(path)
    return sorted(paths)


def homepage_partition(raw):
    spans = list(re.finditer(QUOTE_PATTERN, raw, re.DOTALL))
    require(len(spans) == 1, 'Exactly one native homepage quote span required')
    item = spans[0]
    return {'outside_sha256': hashlib.sha256(raw[:item.start()] + raw[item.end():]).hexdigest(),
            'raw_sha256': hashlib.sha256(raw).hexdigest(), 'quote_span': item.group().decode('utf-8'),
            'quote_span_sha256': hashlib.sha256(item.group()).hexdigest()}


def quote_bar_structure(span):
    raw = span.encode('utf-8')
    # The native updater changes quoted numbers, direction classes and the
    # documented futures price marker. Links, labels and all other markup stay.
    raw = re.sub(rb'<span class="market-price"(?: style="color:#818cf8")?>[-+0-9,.]*(?:<sup style=\'font-size:9px;color:#6366f1;margin-left:1px\'>F</sup>)?</span>', b'', raw)
    raw = re.sub(rb"<span class='market-change (?:up|down|flat)'>[-+0-9,.%]*</span>", b'', raw)
    raw = re.sub(rb'class="market-item (?:up|down|flat)"', b'class="market-item DIRECTION"', raw)
    return re.sub(rb'\s+', b'', raw)


def homepage_observation():
    require(sha(HOME_CANDIDATE) == HOME_ORIGINAL_SHA, 'Exact original native homepage candidate changed')
    require(sha(CURRENT / 'blog/update_news_quotes.py') == QUOTE_UPDATER_SHA, 'Native quote injector source changed')
    original = homepage_partition(HOME_CANDIDATE.read_bytes())
    current = homepage_partition(Path('/var/www/smn/index.html').read_bytes())
    require(original['outside_sha256'] == current['outside_sha256'] == HOME_OUTSIDE_SHA,
            'Homepage changed outside the one exact native quote span')
    require(quote_bar_structure(original['quote_span']) == quote_bar_structure(current['quote_span']),
            'Homepage quote span changed links, labels or markup beyond native quote fields')
    return {'native_candidate_path': str(HOME_CANDIDATE), 'original': original, 'current': current,
            'native_quote_updater_sha256': QUOTE_UPDATER_SHA, 'only_native_quote_span_may_differ': True}


def protected_content():
    require(sha(PUBLIC_RECEIPT) == PUBLIC_RECEIPT_SHA, 'Exact live three-article receipt changed')
    receipt = read(PUBLIC_RECEIPT)
    require(receipt.get('status') == 'live_verified' and receipt.get('production_written') is True
            and receipt.get('edition_date') == DATE and set(receipt.get('published_symbols', [])) == set(PUBLISHED),
            'Actual published coverage differs')
    web = Path('/var/www/smn')
    hashes = {}
    for rel, expected in {**receipt.get('retained_articles', {}), **receipt.get('retained_heroes', {}), **receipt['files']}.items():
        path = PurePosixPath(rel)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in rel, 'Unsafe public receipt path')
        target = web / rel
        require(not target.is_symlink() and target.is_file(), 'Retained public file missing/unsafe: ' + rel)
        if rel == 'index.html':
            require(expected == HOME_ORIGINAL_SHA, 'Unexpected original homepage receipt hash')
            home = homepage_observation()
            hashes[rel] = {'native_candidate_sha256': expected, 'outside_native_quote_span_sha256': home['current']['outside_sha256']}
        else:
            require(sha(target) == expected, 'Retained public file drift: ' + rel)
            hashes[rel] = expected
    ledgers = {str(path): sha(path) for pattern in ('production-weekday_newsletter-*.json', 'production-sunday_summary-*.json')
               for path in sorted(SCHEDULE.glob(pattern))}
    return {'public_receipt_sha256': PUBLIC_RECEIPT_SHA, 'public_files': hashes,
            'day_files': inventory(DAY, exclude=(str(PARENT_OWNER), *(str(DAY/name) for name in OPERATIONAL))),
            'last_run_sha256': sha(DAILY / 'last-run.json'), 'mail_state_sha256': sha(MAIL), 'mail_ledgers': ledgers,
            'pins_sha256': sha('/var/lib/smn-dashboard/pins.json')}


def operational_snapshot():
    return {name: {'sha256': sha(DAY/name), 'value': read(DAY/name) if (DAY/name).is_file() else None} for name in OPERATIONAL}


def recovery_without_tick_clocks(value, automatic=False):
    # Exact source-written clocks only. Original hold/source dates are retained.
    value = json.loads(json.dumps(value))
    if automatic:
        for row in value.get('articles', {}).values():
            row.pop('utc', None)
    else:
        for row in value.get('articles', []):
            row.pop('utc', None)
        if isinstance(value.get('supervision'), dict):
            value['supervision'].pop('updated_utc', None)
    return value


def terminal_phase_worker_delta(before, after, phase):
    """Bind the native terminal progress/delivery result; verify outer tick math.

    Only the two observed terminal states are qualified for this exact repair.
    Source worker_start/finish owns PID/clocks/attempts/prior_status/failure count;
    the entire saved result, host, phase, lease and completion semantics stay exact.
    """
    fields = {'date', 'phase', 'status', 'pid', 'host', 'started_utc', 'updated_utc', 'lease_seconds',
              'attempts', 'prior_status', 'consecutive_failures', 'result', 'process_return_is_completion_proof'}
    require(phase in {'progress', 'deliver'}, 'Unknown native terminal phase')
    status, lease = {'progress': ('needs_attention', 1100), 'deliver': ('live_verified', 300)}[phase]
    def stamp(value):
        require(isinstance(value, str), 'Native worker clock missing')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'Native worker clock must be UTC')
        return parsed
    for row in (before, after):
        require(isinstance(row, dict) and set(row) == fields, 'Unknown or missing native terminal worker field')
        require(row['date'] == DATE and row['phase'] == phase and row['host'] == TARGET_HOST
                and row['status'] == status and type(row['lease_seconds']) is int and row['lease_seconds'] == lease
                and row['process_return_is_completion_proof'] is False,
                'Native terminal worker identity/status/lease/completion changed')
        require(all(type(row[key]) is int and row[key] >= (1 if key in {'pid', 'attempts'} else 0)
                    for key in ('pid', 'attempts', 'consecutive_failures')), 'Native worker tick counters invalid')
        require(isinstance(row['result'], dict) and row['result'].get('status') == status, 'Native terminal worker result status changed')
        require(stamp(row['started_utc']) <= stamp(row['updated_utc']), 'Native worker clocks reversed')
    require(digest(before['result']) == digest(after['result']), 'Native terminal worker substantive result changed')
    steps = after['attempts'] - before['attempts']
    require(steps >= 0 and stamp(after['started_utc']) >= stamp(before['started_utc'])
            and stamp(after['updated_utc']) >= stamp(before['updated_utc']), 'Native worker tick provenance regressed')
    if steps == 0:
        require(digest(before) == digest(after), 'Native terminal worker changed without a new tick')
    else:
        require(after['prior_status'] == before['status'], 'Native worker prior_status transition differs')
        expected_failures = before['consecutive_failures'] + steps if status == 'needs_attention' else 0
        require(after['consecutive_failures'] == expected_failures, 'Native worker failure counter transition differs')
    return {'phase': phase, 'verified_tick_attempt_delta': steps, 'result_sha256': digest(before['result']),
            'native_terminal_result_unchanged': True, 'process_return_is_completion_proof': False}


def operational_delta(before, after):
    require(set(before) == set(after) == set(OPERATIONAL), 'Unknown operational exception')
    guard_before, guard_after = before[OPERATIONAL[0]]['value'], after[OPERATIONAL[0]]['value']
    require(guard_after.get('policy') == guard_before.get('policy') == 'failure-only-reconcile-v1'
            and guard_after.get('date') == guard_before.get('date') == DATE
            and guard_after.get('successful_ticks', 0) >= guard_before.get('successful_ticks', 0)
            and not guard_after.get('inflight')
            and all(failure in guard_before.get('failures', []) for failure in guard_after.get('failures', [])),
            'Scheduled guard added a failure, changed policy or retained a running reservation')
    worker = after[OPERATIONAL[2]]['value']; prior = before[OPERATIONAL[2]]['value']
    require(worker.get('date') == DATE and worker.get('phase') == 'reconcile'
            and worker.get('process_return_is_completion_proof') is False
            and worker.get('attempts', 0) >= prior.get('attempts', 0), 'Scheduled worker identity/completion semantics changed')
    clock_fields = {'pid', 'started_utc', 'updated_utc', 'attempts', 'prior_status', 'consecutive_failures'}
    def stable_worker(row):
        stable = {key: value for key, value in row.items() if key not in clock_fields}
        stable['result'] = recovery_without_tick_clocks(stable.get('result', {}))
        return stable
    require(stable_worker(worker) == stable_worker(prior), 'Scheduled worker substantive result changed')
    supervision = after[OPERATIONAL[1]]['value']
    require(supervision.get('date') == DATE and supervision.get('completion_inferred_from_timer') is False,
            'Scheduled supervision date/completion semantics changed')
    require({key: value for key, value in supervision.items() if key != 'updated_utc'} ==
            {key: value for key, value in before[OPERATIONAL[1]]['value'].items() if key != 'updated_utc'},
            'Scheduled supervision substantive conditions changed')
    for name, automatic in ((OPERATIONAL[3], True), (OPERATIONAL[4], False)):
        first, last = before[name]['value'], after[name]['value']
        require((first is None and last is None) or (first is not None and last is not None and
                recovery_without_tick_clocks(first, automatic) == recovery_without_tick_clocks(last, automatic)),
                'Canonical recovery ledger changed beyond exact tick clocks: ' + name)
    evidence = {name: {'before': before[name], 'after': after[name], 'changed': before[name] != after[name]} for name in OPERATIONAL}
    for name, phase in ((OPERATIONAL[5], 'progress'), (OPERATIONAL[6], 'deliver')):
        evidence[name]['verified_native_tick_transition'] = terminal_phase_worker_delta(before[name]['value'], after[name]['value'], phase)
    return evidence


def scheduled_controller_state():
    import fcntl
    if PARENT_OWNER.is_file():
        owner = read(PARENT_OWNER)
        require(owner.get('status') == 'released', 'Live/unreleased manual parent retained')
        try:
            os.kill(owner['pid'], 0)
        except ProcessLookupError:
            pass
        else:
            raise ValueError('Previous manual parent still alive; no competing scheduled custody')
    path = DAILY / 'controller.lock'
    require(path.is_file() and not path.is_symlink(), 'Existing controller lock missing/unsafe')
    with path.open('rb') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        info = os.fstat(handle.fileno())
    return {'mode': 'scheduled-exclusive', 'lock_device': info.st_dev, 'lock_inode': info.st_ino,
            'last_manual_owner_sha256': sha(PARENT_OWNER), 'available_at_read_only_probe': True}


def capture_baseline(operator_sha256, custody_mode='scheduled'):
    require(os.name == 'posix' and sys.flags.optimize == 0 and 'PYTHONOPTIMIZE' not in os.environ,
            'Unoptimized Linux Python with PYTHONOPTIMIZE absent required')
    require(command('hostname', '-s') == TARGET_HOST and TARGET_IP in command('hostname', '-I').split(), 'Exact target mismatch')
    require(CURRENT.is_symlink() and CURRENT.resolve() == OLD_RELEASE and git(CURRENT, 'rev-parse', 'HEAD') == OLD,
            'Live baseline is not exact b61')
    require(not git(CURRENT, 'status', '--porcelain', '--untracked-files=no'), 'Live source has tracked drift')
    require(not ACTIVATION_LOCK.exists(), 'Existing activation owner retained')
    adapter = Path('/opt/smn-subscription/bin/git')
    adapter_info = metadata(adapter)
    require(adapter.read_bytes() == b'#!/bin/sh\nexec /usr/bin/sudo -u flask /usr/bin/git "$@"\n'
            and adapter_info['uid'] == 0 and adapter_info['mode'] & 0o022 == 0
            and adapter_info['mode'] & 0o111 != 0, 'Existing Git-as-flask adapter differs')
    config = read(ACTIVATION)
    require(config.get('source_commit') == OLD and config.get('reader_provider') == 'chatgpt'
            and config.get('publication_policy') == 'continuity-v1', 'Source-bound active continuity config differs')
    no_running_services()
    services = {unit: system_properties(unit) for unit in SERVICES}
    require(all(services[unit]['WorkingDirectory'] == str(OLD_RELEASE / 'blog') for unit in LEGACY), 'Legacy effective source drift')
    require(all(services[unit]['WorkingDirectory'] == str(CURRENT / 'blog') for unit in CONTINUITY), 'Continuity effective source drift')
    require(services['smn-continuity@reconcile.service']['TimeoutStartUSec'] in {'1min 30s', '90s', '90000000'}
            and services['smn-continuity@reconcile.service']['Restart'] == 'no'
            and services['smn-continuity@reconcile.service']['StartLimitIntervalUSec'] == '0'
            and services['smn-continuity@reconcile.service']['KillMode'] == 'control-group', 'Existing supervisor bounds differ')
    timers = {unit: timer_state(unit) for unit in TIMERS}
    if custody_mode == 'parent':
        require(not timers['smn-continuity@progress.timer']['active'] and not timers['smn-continuity@deliver.timer']['active'],
                'Parent mode requires the preserved progress/delivery hold')
    require(custody_mode in {'parent', 'scheduled'}, 'Explicit bound custody mode required')
    parent = live_parent() if custody_mode == 'parent' else None
    controller = parent if parent is not None else scheduled_controller_state()
    return {'captured_utc': utc(), 'operator_sha256': operator_sha256, 'source_commit': OLD, 'candidate_commit': NEW,
            'hostname': TARGET_HOST, 'ip': TARGET_IP, 'pointer': os.readlink(CURRENT), 'parent': parent,
            'custody_mode': custody_mode, 'controller': controller,
            'files': {str(path): runtime_metadata(path) for path in runtime_files()}, 'services': services, 'timers': timers,
            'operational': operational_snapshot(),
            'homepage_observation': homepage_observation(),
            'protected': protected_content(), 'models_called': 0, 'mail_sent': 0, 'production_writes': 0}


def snapshot_attestation(approval, now):
    evidence = approval.get('production_snapshot', {})
    require(approval.get('approve_smn_single_host_snapshot_scope') is True and approval.get('snapshot_scope_approval_reference'),
            'New exact approval must explicitly retain the single-host snapshot scope')
    require(evidence.get('scope') == 'smn-single-host-v1' and evidence.get('target_hostname') == TARGET_HOST
            and evidence.get('target_ip') == TARGET_IP and evidence.get('status') == 'completed'
            and evidence.get('evidence_kind') == 'human-confirmed-current-day'
            and evidence.get('confirmed_by') == approval.get('approved_by') == 'Afshin', 'Current-day human target backup confirmation required')
    confirmed = datetime.fromisoformat(evidence['confirmed_at_utc'].replace('Z', '+00:00'))
    require(confirmed.tzinfo is not None and confirmed.utcoffset().total_seconds() == 0 and confirmed <= now
            and confirmed.date() == now.date() and evidence.get('completed_date_utc') == now.date().isoformat(),
            'Backup confirmation must be current-day UTC')
    require(all(evidence.get(key) is None for key in ('provider', 'snapshot_reference', 'completed_at_utc')),
            'Do not invent unknown provider ID/completion clock')
    require(evidence.get('evidence_reference') and evidence.get('confirmation_reference')
            and all(evidence.get(key) == approval.get(key) for key in ('source_commit', 'operator_sha256', 'baseline_sha256', 'artifact_sha256')),
            'Backup evidence must be explicitly rebound to this newly approved source/operator/baseline/artifact')


def validate_approval(approval, manifest, baseline, input_hashes, operator_sha256, now):
    require(approval.get('approved') is True and approval.get('execute_app_refresh') is True
            and approval.get('source_commit') == NEW and approval.get('baseline_source_commit') == OLD
            and approval.get('date') == now.date().isoformat() and approval.get('approval_reference'), 'New exact app-refresh authorization required')
    require(approval.get('operator_sha256') == operator_sha256 and manifest.get('operator_sha256') == operator_sha256
            and approval.get('baseline_sha256') == input_hashes['baseline'] and baseline['operator_sha256'] == operator_sha256,
            'Exact new operator/baseline approval required')
    require(manifest.get('source_commit') == NEW and manifest.get('baseline_source_commit') == OLD
            and manifest.get('artifact_sha256') == approval.get('artifact_sha256')
            and manifest.get('artifact_sha256') == artifact_digest(manifest)
            and manifest.get('inputs') == {key: value for key, value in input_hashes.items() if key != 'baseline'}, 'Exact new artifact mismatch')
    require(datetime.fromisoformat(baseline['captured_utc']).date() == now.date()
            and baseline['source_commit'] == OLD and baseline['candidate_commit'] == NEW
            and baseline.get('hostname') == TARGET_HOST and baseline.get('ip') == TARGET_IP
            and approval.get('custody_mode') == baseline.get('custody_mode') in {'parent', 'scheduled'}, 'Fresh current-day exact baseline required')
    require(approval.get('controller_state_sha256') == digest(baseline['controller'])
            and approval.get('preserve_timer_baseline') is True and approval.get('content_mail_canonical_writes') is False,
            'Owned handoff and application-only scope must be approved explicitly')
    if baseline['custody_mode'] == 'parent':
        require(baseline['parent']['value']['pid'] == PARENT_PID
                and approval.get('controller_owner_sha256') == baseline['parent']['sha256']
                and approval.get('preserve_progress_delivery_hold') is True, 'Exact parent custody approval required')
    else:
        require(baseline['parent'] is None and approval.get('approve_scheduled_exclusive_controller') is True,
                'Normal scheduled exclusive-controller scope requires new explicit approval')
    snapshot_attestation(approval, now)


def validate_qualification(source, operator, operator_sha256, archive_sha256):
    require(source.get('source_commit') == NEW and source.get('source_archive_sha256') == archive_sha256
            and source.get('source_qualification_passed') is True and source.get('focused_and_adjacent_test_count') == 130
            and source.get('modules') and all(item.get('passed') is True for item in source['modules'])
            and {item['symbol'] for item in source.get('retained_completion', [])} == {'XLF', 'DJI'}
            and all(item.get('status') == 'passed_under_candidate_read_only' and item.get('retained_evidence_bytes_unchanged') is True
                    for item in source['retained_completion'])
            and source.get('linux_fcntl_stub') is False and source.get('source_bytes_unchanged') is True
            and source.get('current_pointer_unchanged') is True and source.get('model_calls') == 0
            and source.get('production_writes') == 0 and source.get('mail_sends') == 0,
            'Independent exact Linux source qualification required')
    require(operator.get('passed') is True and operator.get('source_commit') == NEW
            and operator.get('operator_sha256') == operator_sha256 and operator.get('real_fcntl') is True
            and operator.get('process_death_recovery_verified') is True and operator.get('inherited_parent_lock_preserved') is True
            and operator.get('scheduled_controller_exclusion_and_timer_restore_verified') is True
            and operator.get('homepage_only_native_quote_span_allowed') is True
            and operator.get('execstart_configuration_projection_verified') is True
            and operator.get('phase_worker_envelope_projection_verified') is True
            and operator.get('production_writes') == 0 and operator.get('model_calls') == 0,
            'Exact real-Linux operator lock/process-death qualification required')


def equivalent(qualified, deployed, name):
    if qualified == deployed:
        return True
    allowed = Path(name).suffix.lower() in SAFE_TEXT or Path(name).name in {'.gitignore', '.gitattributes'}
    return allowed and b'\0' not in qualified and qualified.replace(b'\r\n', b'\n') == deployed


def archive_equivalence(archive, checkout):
    expected = set(git(checkout, 'ls-tree', '-r', '-z', '--name-only', NEW, binary=True).decode().strip('\0').split('\0'))
    with tarfile.open(archive, 'r:') as packet:
        members = packet.getmembers()
        names = [item.name for item in members if item.isfile()]
        require(len(names) == len(set(names)) and set(names) == expected, 'Source archive/Git file lists differ')
        for item in members:
            path = PurePosixPath(item.name)
            require(not item.issym() and not item.islnk() and not path.is_absolute() and '..' not in path.parts,
                    'Unsafe archive member')
            require('\\' not in item.name and (item.isfile() or item.isdir()), 'Unsupported archive member')
            if item.isfile():
                require(equivalent(packet.extractfile(item).read(), git(checkout, 'show', NEW + ':' + item.name, binary=True), item.name),
                        'Source archive differs beyond permitted CRLF folding: ' + item.name)
    return {'files': len(expected), 'source_commit': NEW, 'passed': True}


def atomic(path, data):
    path = Path(path)
    before = metadata(path)
    require(before is not None, 'App refresh never creates unknown managed config/unit paths')
    handle, temporary = tempfile.mkstemp(prefix=path.name + '.app-refresh-', dir=path.parent)
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())
        os.chmod(temporary, before['mode']); os.chown(temporary, before['uid'], before['gid'])
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()


def save(path, value):
    path = Path(path)
    data = (json.dumps(value, indent=2) + '\n').encode()
    if path.exists():
        atomic(path, data)
    else:
        with path.open('xb') as out:
            out.write(data); out.flush(); os.fsync(out.fileno())


def point(target):
    temporary = CURRENT.with_name('current.app-refresh-' + str(os.getpid()))
    require(not temporary.exists() and not temporary.is_symlink(), 'Pointer transaction already exists')
    temporary.symlink_to(target)
    os.replace(temporary, CURRENT)


def planned_files(baseline):
    plans = {}
    activation = read(ACTIVATION)
    activation.update(source_commit=NEW, record=str(RECORD))
    plans[str(ACTIVATION)] = (json.dumps(activation, indent=2) + '\n').encode()
    for unit in LEGACY:
        info = baseline['services'][unit]
        for text in [info['FragmentPath'], *info['DropInPaths'].split()]:
            path = Path(text)
            original = path.read_bytes()
            if str(OLD_RELEASE).encode() in original:
                plans[text] = original.replace(str(OLD_RELEASE).encode(), str(RELEASE).encode())
    require(all(Path(text) == ACTIVATION or (UNITS in Path(text).parents and 'smn-continuity@' not in text)
                for text in plans), 'Refresh attempted to change continuity supervisor or unknown paths')
    return plans


def rollback_admissible(current, before, planned):
    require(current == before or current == planned, 'Peer changed an owned path; do not overwrite')


def preserved(baseline, audit=None):
    require(protected_content() == baseline['protected'], 'Content/mail/canonical/private evidence changed')
    if baseline.get('parent') is not None:
        expected_owner = baseline.get('owned_controller_after_sha256', baseline['parent']['sha256'])
        require(sha(PARENT_OWNER) == expected_owner, 'Approved controller owner record drift')
    elif baseline.get('custody_mode') == 'scheduled':
        require(sha(PARENT_OWNER) == baseline['controller']['last_manual_owner_sha256'], 'Released manual owner evidence drift')
    for text, before in baseline['files'].items():
        if text not in baseline.get('owned_paths', []):
            require(runtime_metadata(text) == before, 'Unchanged runtime/config drift: ' + text)
    observed = operational_snapshot()
    require(set(baseline.get('operational', {})) == set(observed) == set(OPERATIONAL), 'Exact operational preservation evidence missing')
    phases = {name: {'before': baseline['operational'][name], 'after': observed[name]}
              for name in OPERATIONAL[5:]}
    if audit is not None:
        # Populate evidence before validation so rollback_required retains the
        # actual rejected peer result as well as the immutable bound baseline.
        audit['terminal_phase_workers'] = phases
    for name, phase in ((OPERATIONAL[5], 'progress'), (OPERATIONAL[6], 'deliver')):
        phases[name]['verified_native_tick_transition'] = terminal_phase_worker_delta(
            phases[name]['before']['value'], phases[name]['after']['value'], phase)
    return {'terminal_phase_workers': phases}


def release_activation_lock():
    owner = read(ACTIVATION_LOCK / 'owner.json')
    require(owner.get('pid') == os.getpid() and owner.get('source_commit') == NEW and owner.get('record') == str(RECORD),
            'Activation ownership changed; retain peer lock')
    (ACTIVATION_LOCK / 'owner.json').unlink()
    ACTIVATION_LOCK.rmdir()


@contextmanager
def activation_lease():
    ACTIVATION_LOCK.mkdir()
    save(ACTIVATION_LOCK / 'owner.json', {'pid': os.getpid(), 'source_commit': NEW, 'record': str(RECORD), 'task': 'same-task exact app refresh v3-r2'})
    try:
        yield
    finally:
        receipt = RECORD / 'receipt.json'
        if not receipt.is_file() or read(receipt).get('status') != 'rollback_required':
            release_activation_lock()


def expected_timers(baseline, custody):
    expected = {unit: dict(value) for unit, value in baseline['timers'].items()}
    for unit in custody.get('paused_timers', []):
        expected[unit]['active'] = False
    return expected


@contextmanager
def coordination_locks():
    import fcntl
    handles = []
    try:
        for path in [SCHEDULE / 'scheduler.lock', SCHEDULE / 'newsletter.lock',
                     DAY / 'continuity-progress.lock', DAY / 'continuity-delivery.lock']:
            require(path.is_file() and not path.is_symlink(), 'Existing coordination lock missing/unsafe')
            handle = path.open('rb'); handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        for handle in reversed(handles):
            handle.close()


@contextmanager
def controller_lease(args, baseline, approval):
    import fcntl
    handle = None
    timer_paused = False
    paused = []
    inherited = args.controller_lock_fd is not None
    try:
        if getattr(args, 'custody_mode', 'parent') == 'scheduled':
            require(baseline.get('custody_mode') == 'scheduled' and approval.get('approve_scheduled_exclusive_controller') is True
                    and not inherited and not args.handoff_owned_parent and not args.retain_owned_idle_parent,
                    'Scheduled custody requires one explicit mode and genuine exclusive acquisition')
            require(scheduled_controller_state() == baseline['controller'], 'Approved scheduled controller availability changed')
            # Pause timers, never running services. Refuse any ongoing work after
            # pausing; restore every originally-active timer on every exit.
            for unit in TIMERS:
                if baseline['timers'][unit]['active']:
                    paused.append(unit); command('systemctl', 'stop', unit)
            no_running_services()
            handle = (DAILY / 'controller.lock').open('rb')
            info = os.fstat(handle.fileno())
            require((info.st_dev, info.st_ino) == (baseline['controller']['lock_device'], baseline['controller']['lock_inode']),
                    'Scheduled controller inode changed')
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            key = (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino)
            require(flock_record(Path('/proc/self/fdinfo/' + str(handle.fileno())).read_text(encoding='utf-8').splitlines(), key),
                    'Genuine own scheduled controller descriptor/flock proof missing')
            yield {'inherited': False, 'retained_live_parent': False, 'scheduled': True, 'pid': os.getpid(),
                   'controller_inode': info.st_ino, 'paused_timers': list(paused), 'previous_controller': baseline['controller']}
            return
        require(live_parent() == baseline['parent'], 'Approved parent custody changed')
        if args.retain_owned_idle_parent:
            require(not inherited and not args.handoff_owned_parent and approval.get('approve_retained_idle_controller_owner') is True,
                    'Retained idle parent requires an exclusive explicit mode/approval')
            # The exact same-task parent is idle and keeps its real descriptor.
            # We claim no inherited fd and do not acquire or release its flock.
            yield {'inherited': False, 'retained_live_parent': True, 'pid': os.getpid(), 'old_owner': baseline['parent']}
            require(live_parent() == baseline['parent'], 'Retained idle controller custody changed during refresh')
            return
        if inherited:
            require(not args.handoff_owned_parent, 'Choose only one controller custody mode')
            info = os.fstat(args.controller_lock_fd)
            require((info.st_dev, info.st_ino) == (baseline['parent']['lock_device'], baseline['parent']['lock_inode']),
                    'Inherited controller descriptor differs')
            handle = os.fdopen(os.dup(args.controller_lock_fd), 'rb')
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            require(args.handoff_owned_parent and approval.get('approve_guarded_owned_controller_handoff') is True,
                    'Only explicit owned-parent handoff or inherited descriptor is permitted')
            if baseline['timers'][RECONCILE_TIMER]['active']:
                command('systemctl', 'stop', RECONCILE_TIMER); timer_paused = True
            no_running_services()  # Never stop or kill a running service.
            require(live_parent() == baseline['parent'], 'Parent changed before owned release')
            signal = Path(baseline['parent']['value']['release_signal'])
            require(signal.parent == Path('/var/tmp/smn-release-b61b37f-20261009-v3') and not signal.exists(), 'Unexpected owned release signal')
            with signal.open('x', encoding='utf-8') as out:
                out.write('Explicit same-task handoff to approved678477ab app-refresh operator; no peer interruption\n')
            handle = (DAILY / 'controller.lock').open('rb')
            deadline = time.monotonic() + 15
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB); break
                except BlockingIOError:
                    require(time.monotonic() < deadline, 'Previous/peer controller retained; no source mutation')
                    time.sleep(0.1)
            released = read(PARENT_OWNER)
            original = baseline['parent']['value']
            require(released.get('status') == 'released'
                    and {key: value for key, value in released.items() if key not in {'status', 'released_utc'}}
                    == {key: value for key, value in original.items() if key not in {'status', 'released_utc'}}, 'Owned parent release record changed beyond explicit transition')
            baseline['owned_controller_after_sha256'] = sha(PARENT_OWNER)
        if timer_paused:
            command('systemctl', 'start', RECONCILE_TIMER); timer_paused = False
        yield {'inherited': inherited, 'retained_live_parent': False, 'pid': os.getpid(), 'old_owner': baseline['parent'], 'controller_inode': os.fstat(handle.fileno()).st_ino}
    finally:
        errors = []
        for unit in reversed(paused):
            try:
                command('systemctl', 'start', unit)
            except BaseException as error:
                errors.append(unit + ': ' + str(error))
        if paused:
            restored = {unit: timer_state(unit) for unit in TIMERS}
            if restored != baseline['timers']:
                errors.append('Actual timer active/enabled states differ from bound baseline')
            if RECORD.is_dir():
                save(RECORD / 'timer-restoration.json', {'baseline': baseline['timers'], 'actual': restored, 'errors': errors, 'utc': utc()})
            if errors and (RECORD/'receipt.json').is_file():
                record = read(RECORD/'receipt.json'); record.update(status='rollback_required', timer_restoration_errors=errors)
                save(RECORD/'receipt.json', record)
            elif not errors and (RECORD/'receipt.json').is_file():
                record = read(RECORD/'receipt.json')
                if record.get('status') == 'active_verified_controller_held':
                    record.update(status='active_verified', timers_restored=True, scheduled_controller_releasing=True, restored_utc=utc())
                    save(RECORD/'receipt.json', record)
        if timer_paused:
            command('systemctl', 'start', RECONCILE_TIMER)
        if handle:
            # Closing the inherited duplicate MUST NOT unlock the live parent's lease.
            handle.close()
        require(not errors, 'Timer restoration needs root review: ' + '; '.join(errors))


def rollback(record):
    baseline = record['baseline']
    record['rollback_preservation_evidence'] = {}
    preserved(baseline, record['rollback_preservation_evidence'])
    record['rollback_operational_evidence'] = operational_snapshot()
    no_running_services()
    require(os.readlink(CURRENT) in {baseline['pointer'], str(RELEASE)} and CURRENT.resolve() in {OLD_RELEASE, RELEASE},
            'Peer changed release pointer')
    for text, planned in record['planned'].items():
        rollback_admissible(metadata(text), baseline['files'][text], planned)
        require(sha(RECORD / 'backup' / hashlib.sha256(text.encode()).hexdigest()) == baseline['files'][text]['sha256'], 'Owned backup changed')
    for text in record['planned']:
        before = baseline['files'][text]
        atomic(text, (RECORD / 'backup' / hashlib.sha256(text.encode()).hexdigest()).read_bytes())
        require(metadata(text) == before, 'Owned restoration mismatch')
    point(baseline['pointer'])
    command('systemctl', 'daemon-reload')
    require(CURRENT.resolve() == OLD_RELEASE, 'Rollback pointer mismatch')
    require(configured_services({unit: system_properties(unit) for unit in SERVICES}) == configured_services(baseline['services']), 'Rollback effective units differ')
    require({unit: timer_state(unit) for unit in TIMERS} == expected_timers(baseline, record['custody']), 'Rollback timer state differs')
    record['rollback_postrestore_preservation_evidence'] = {}
    preserved(baseline, record['rollback_postrestore_preservation_evidence'])
    record.update(status='rolled_back', rollback_utc=utc())
    save(RECORD / 'receipt.json', record)


def postcheck(record):
    baseline = record['baseline']
    require(CURRENT.resolve() == RELEASE and git(RELEASE, 'rev-parse', 'HEAD') == NEW
            and not git(RELEASE, 'status', '--porcelain', '--untracked-files=no'), 'Installed exact source changed')
    require(read(ACTIVATION).get('source_commit') == NEW, 'Activation source mismatch')
    for text, planned in record['planned'].items():
        require(metadata(text) == planned, 'Installed owned path differs: ' + text)
    no_running_services()
    observed_services = {unit: system_properties(unit, normalize=True) for unit in SERVICES}
    require(configured_services(observed_services) == configured_services(baseline['services']),
            'Effective service/config changed beyond exact source paths')
    record['postcheck_service_observations'] = observed_services
    require({unit: timer_state(unit) for unit in TIMERS} == expected_timers(baseline, record['custody']), 'Timer state changed')
    record['postcheck_preverification_preservation_evidence'] = {}
    preserved(baseline, record['postcheck_preverification_preservation_evidence'])
    sys.path.insert(0, str(RELEASE / 'blog'))
    import smn_models
    def no_dispatch(*args, **kwargs):
        raise RuntimeError('App-refresh verification permits no model prepare/dispatch')
    smn_models.prepare = smn_models.run = no_dispatch
    import editorial_gate
    checks = {symbol: editorial_gate.verify_complete(PUBLIC_READER / 'results' / symbol) for symbol in PUBLISHED}
    record['postcheck_postverification_preservation_evidence'] = {}
    preserved(baseline, record['postcheck_postverification_preservation_evidence'])
    no_running_services()
    record['operational_delta'] = operational_delta(baseline['operational'], operational_snapshot())
    record['homepage_refresh_delta'] = {'before': baseline['homepage_observation'], 'after': homepage_observation()}
    return {'source_commit': NEW, 'actual_retained_complete_checks': checks,
            'unchanged_live_publication_receipt_sha256': PUBLIC_RECEIPT_SHA,
            'continuity_supervisor_bounds_unchanged': True, 'immutable_content_jobs_receipts_and_mail_bytes_unchanged': True,
            'canonical_core_unchanged': True, 'scheduled_operational_clock_deltas_attributed': True,
            'model_calls': 0, 'mail_calls': 0}


def apply(args):
    require(os.name == 'posix' and sys.flags.optimize == 0 and 'PYTHONOPTIMIZE' not in os.environ, 'Unoptimized Linux execution required')
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'; sys.dont_write_bytecode = True
    approval, manifest, baseline = read(args.approval), read(args.manifest), read(args.baseline)
    hashes = {'bundle': sha(args.bundle), 'archive': sha(args.source_archive), 'source_qualification': sha(args.source_qualification),
              'operator_qualification': sha(args.operator_qualification), 'baseline': sha(args.baseline)}
    validate_approval(approval, manifest, baseline, hashes, sha(__file__), datetime.now(timezone.utc))
    validate_qualification(read(args.source_qualification), read(args.operator_qualification), sha(__file__), hashes['archive'])
    require(args.custody_mode == baseline['custody_mode'], 'Apply custody mode differs from approved read-only baseline')
    fresh = capture_baseline(sha(__file__), args.custody_mode)
    # Capture clocks are provenance, not a state fingerprint. Runtime state,
    # owner, files and protected evidence must still match the approved capture.
    require(baseline_state(fresh) == baseline_state(baseline), 'Fresh read-only preflight drift; no mutation')
    preflight_operational_evidence = operational_delta(baseline['operational'], fresh['operational'])
    require(not RECORD.exists() and not RELEASE.exists(), 'Prior app transaction/checkout retained; no automatic restart')
    with activation_lease(), coordination_locks(), controller_lease(args, baseline, approval) as custody:
        no_running_services()
        premutation_preservation = {}
        preserved(baseline, premutation_preservation)
        retain_lock = False
        record = None
        try:
            RECORD.mkdir(mode=0o700); (RECORD / 'backup').mkdir()
            plans = planned_files(baseline)
            baseline['owned_paths'] = list(plans)
            record = {'status': 'prepared', 'source_commit': NEW, 'baseline_source_commit': OLD, 'baseline': baseline,
                       'approval': approval, 'custody': custody, 'planned': {}, 'created_utc': utc(), 'model_calls': 0, 'mail_calls': 0,
                       'fresh_preflight_service_observations': fresh['services'], 'preflight_operational_evidence': preflight_operational_evidence,
                       'premutation_preservation_evidence': premutation_preservation}
            for text, data in plans.items():
                require(metadata(text) == baseline['files'][text], 'Managed file changed before backup')
                shutil.copy2(text, RECORD / 'backup' / hashlib.sha256(text.encode()).hexdigest())
                record['planned'][text] = {**baseline['files'][text], 'sha256': hashlib.sha256(data).hexdigest()}
            save(RECORD / 'receipt.json', record)
            heads = command('/usr/bin/sudo', '-u', 'flask', '/usr/bin/git', 'bundle', 'list-heads', str(args.bundle.resolve())).splitlines()
            require(heads == [NEW + ' ' + SOURCE_REF], 'Exact bounded source bundle ref differs')
            git(CURRENT, 'bundle', 'verify', str(args.bundle.resolve()))
            git(CURRENT, 'fetch', str(args.bundle.resolve()), SOURCE_REF)
            git(CURRENT, 'worktree', 'add', '--detach', str(RELEASE), NEW)
            require(git(RELEASE, 'rev-parse', 'HEAD') == NEW and not git(RELEASE, 'status', '--porcelain', '--untracked-files=no'), 'Candidate source differs')
            require(set(git(RELEASE, 'diff', '--name-only', OLD, NEW).splitlines()) == EXPECTED_PATCH, 'Candidate change scope differs')
            record['archive_equivalence'] = archive_equivalence(args.source_archive, RELEASE)
            save(RECORD / 'receipt.json', record)
            for text, data in plans.items():
                require(metadata(text) == baseline['files'][text], 'Peer changed app path before write')
                atomic(text, data)
            require(os.readlink(CURRENT) == baseline['pointer'] and CURRENT.resolve() == OLD_RELEASE, 'Peer changed pointer before app refresh')
            point(RELEASE)
            command('systemctl', 'daemon-reload')
            record['postcheck'] = postcheck(record)
            record.update(status='active_verified_controller_held', verified_utc=utc())
            save(RECORD / 'receipt.json', record)
            print(json.dumps({'record': str(RECORD), 'status': record['status'], 'source_commit': NEW,
                              'receipt_sha256': sha(RECORD / 'receipt.json'), 'content_writes': 0, 'mail_sends': 0}), flush=True)
        except BaseException:
            if record is not None:
                try:
                    rollback(record)
                except BaseException as error:
                    retain_lock = True
                    record.update(status='rollback_required', rollback_error=str(error)); save(RECORD / 'receipt.json', record)
            raise
        if not custody['inherited'] and not custody['retained_live_parent'] and not custody.get('scheduled'):
            release = RECORD / 'release-owned-controller-lease'
            save(RECORD / 'controller-owner.json', {'pid': os.getpid(), 'source_commit': NEW, 'status': 'manual_owner_held', 'release_signal': str(release)})
            print(json.dumps({'owned_controller_held_until_explicit_release': str(release), 'progress_deliver_still_held': True}), flush=True)
            while not release.exists():
                time.sleep(1)
            save(RECORD / 'controller-owner.json', {'pid': os.getpid(), 'source_commit': NEW, 'status': 'released', 'released_utc': utc()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    preflight = commands.add_parser('preflight')
    preflight.add_argument('--operator-sha256', required=True)
    preflight.add_argument('--custody-mode', choices=('scheduled', 'parent'), default='scheduled')
    apply_parser = commands.add_parser('apply')
    for name in ('approval', 'manifest', 'baseline', 'bundle', 'source-archive', 'source-qualification', 'operator-qualification'):
        apply_parser.add_argument('--' + name, type=Path, required=True)
    apply_parser.add_argument('--controller-lock-fd', type=int)
    apply_parser.add_argument('--handoff-owned-parent', action='store_true')
    apply_parser.add_argument('--retain-owned-idle-parent', action='store_true')
    apply_parser.add_argument('--custody-mode', choices=('scheduled', 'parent'), default='scheduled')
    args = parser.parse_args()
    if args.action == 'preflight':
        require(re.fullmatch('[0-9a-f]{64}', args.operator_sha256), 'Exact operator hash required')
        print(json.dumps(capture_baseline(args.operator_sha256, args.custody_mode), indent=2))
    else:
        apply(args)


if __name__ == '__main__':
    main()
