"""Offline exporter tests against the retained engine and real EOD validator."""
from datetime import datetime,timedelta,timezone
import copy,hashlib,importlib.util,io,json,os,subprocess,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
configuration=types.ModuleType('config');configuration.csv_folder='';configuration.blog_queue_server='http://receiver.invalid/'
saved=sys.modules.get('config');sys.modules['config']=configuration
try:
    from appserver.appserver import volume_feed_exporter as exporter
    from appserver.appserver import highest_volume_stocks as engine
finally:
    if saved is None:sys.modules.pop('config',None)
    else:sys.modules['config']=saved
from appserver.appserver.volume_feed_protocol import FILES,install_bundle,canonical
from data_updater.eod_readiness import build_status_marker,evaluate_eod_readiness,terminal_row_fingerprint,validate_success_marker,latest_completed_us_equity_session,target_table_date,NY_TZ

NOW=datetime(2026,10,13,7,tzinfo=timezone.utc)
class Clock(datetime):
    instant=NOW
    @classmethod
    def now(cls,tz=None):return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

def valid_marker(now=NOW):
    session=latest_completed_us_equity_session(now)
    targets={'US':[f'T{i:03}' for i in range(100)],'ETF':[f'E{i:03}' for i in range(25)]}
    observations={f'{market}:{symbol}':{'state':'verified','terminal_date':session.isoformat(),
        'terminal_row_fingerprint':terminal_row_fingerprint([symbol,session.isoformat(),1.0])}
        for market,symbols in targets.items() for symbol in symbols}
    readiness=evaluate_eod_readiness(targets_by_exchange=targets,observations=observations,
        completed_session=session,resource_ids=['0','1','2','3','4','11'])
    marker=build_status_marker(base={'started_at':(now-timedelta(hours=3)).isoformat(),'completed_at':(now-timedelta(hours=2)).isoformat(),
        'market_date':now.astimezone(NY_TZ).date().isoformat(),'target_table_date':target_table_date(now).isoformat(),'latest_us_date':session.isoformat(),
        'total':125,'updated':125,'skipped':0,'missing':0,'failed':0,'source':'synthetic'},readiness=readiness)
    assert validate_success_marker(marker)
    return marker

class ExporterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.prices=self.root/'csv'/'US';self.prices.mkdir(parents=True)
        self.marker=self.root/'status.json';self.marker.write_text(json.dumps(valid_marker()))
        self.state=self.root/'attempts'
        self.addCleanup(patch.stopall)
        patch.object(engine.config,'csv_folder',str(self.root/'csv')).start()
        patch.object(engine,'datetime',Clock).start()
        self.write_price('HPQ');self.write_price('JPM',last_volume='18000003')
    def write_price(self,symbol,*,last_volume='14000001',close='50',end=datetime(2026,10,12),count=30,newline='\n'):
        lines=[]
        for index in range(count):
            day=end-timedelta(days=count-1-index)
            volume=last_volume if index==count-1 else '6000001'
            lines.append(f'{symbol},{day.date().isoformat()},0,0,0,{close},{volume}')
        (self.prices/(symbol+'.csv')).write_bytes((newline.join(lines)+newline).encode())
    def prepare(self):return exporter.prepare_attempt(self.marker,self.state,'d'*40,now=NOW)
    def test_original_engine_outputs_and_csv_bytes_unchanged(self):
        # Run the retained baseline itself; do not implement a second formula.
        baseline_path=os.environ.get('VOLUME_ENGINE_BASELINE_FILE')
        raw=Path(baseline_path).read_bytes() if baseline_path else subprocess.check_output(['git','-C',str(ROOT),'show','c25ffd562dc3058ab41db5b07e9075dd841fb29b:appserver/appserver/highest_volume_stocks.py'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'ed4fdf66342cb2487c0b3caa3999bcf277c2e41730a547e72a33c5a7143cfbe9')
        source=raw.decode('utf-8')
        baseline=types.ModuleType('retained_volume_engine');baseline.__file__=str(ROOT/'appserver/appserver/highest_volume_stocks.py')
        with patch.dict(sys.modules,{'config':engine.config}):exec(compile(source,baseline.__file__,'exec'),baseline.__dict__)
        baseline.datetime=Clock
        self.write_price('STALE',end=datetime(2026,8,1));self.write_price('LOW',close='1')
        self.write_price('SHORT',count=2);self.write_price('CRLF',newline='\r\n')
        before=baseline.get_highest_volume_US_stocks()
        original={name:(self.prices/name).read_bytes() for name in FILES}
        observations={};after=engine.get_highest_volume_US_stocks(observations=observations)
        self.assertEqual(before,after)
        self.assertEqual(original,{name:(self.prices/name).read_bytes() for name in FILES})
        self.assertEqual(observations['CRLF']['source_csv_sha256'],hashlib.sha256((self.prices/'CRLF.csv').read_bytes()).hexdigest())
        self.assertNotIn('STALE',observations);self.assertNotIn('LOW',observations)
    def test_existing_real_success_validator_and_calendar_are_used(self):
        bundle,attempt=self.prepare()
        proof=bundle['files'][FILES[0]]['provenance']['completion_proof']
        self.assertEqual(proof['completed_session'],'2026-10-12')
        self.assertEqual(proof['marker_sha256'],hashlib.sha256(self.marker.read_bytes()).hexdigest())
        self.assertTrue((attempt/'bundle.json').is_file())
    def test_failed_actual_style_marker_stops_before_calculation(self):
        marker=valid_marker();marker['ok']=False;self.marker.write_text(json.dumps(marker));calculate=Mock()
        with self.assertRaises(ValueError):exporter.prepare_attempt(self.marker,self.state,'d'*40,now=NOW,calculate=calculate)
        calculate.assert_not_called();self.assertFalse(self.state.exists())
    def test_changed_marker_fingerprint_is_not_accepted(self):
        marker=valid_marker();marker['generation_fingerprint']='e'*64;self.marker.write_text(json.dumps(marker))
        with self.assertRaises(ValueError):self.prepare()
    def test_wrong_target_date_stops_before_calculation(self):
        marker=valid_marker();marker['target_table_date']='2026-10-12';self.marker.write_text(json.dumps(marker))
        with self.assertRaises(ValueError):self.prepare()
    def test_future_completion_clock_fails(self):
        with patch.object(exporter,'validate_success_marker',return_value=True):
            marker=valid_marker();marker['completed_at']='2026-10-13T08:00:00Z';self.marker.write_text(json.dumps(marker))
            with self.assertRaises(ValueError):self.prepare()
    def test_restart_reuses_frozen_attempt_without_second_calculation(self):
        first,attempt=self.prepare()
        with patch.object(engine,'get_highest_volume_US_stocks',side_effect=AssertionError('No second calculation')):
            second,same=exporter.prepare_attempt(self.marker,self.state,'d'*40,now=NOW+timedelta(minutes=10))
        self.assertEqual(first,second);self.assertEqual(attempt,same)
    def test_changed_cached_payload_is_rejected(self):
        bundle,attempt=self.prepare();bundle['delivery_id']='0'*64;(attempt/'bundle.json').write_bytes(canonical(bundle))
        with self.assertRaises(ValueError):self.prepare()
    def response(self,bundle,receiver,**kwargs):
        receipt=install_bundle(receiver,bundle,now=NOW,attribution={'source_peer_ip':'10.0.0.96','receiver_module_sha256':'f'*64,'proxy_transport':'unix'})
        return types.SimpleNamespace(status_code=200,json=lambda:receipt)
    def send(self,*args,**kwargs):
        kwargs.setdefault('clock',lambda:kwargs['now'])
        return exporter.send_bundle(*args,expected_source_peer='10.0.0.96',
            expected_receiver_module_sha256='f'*64,**kwargs)
    def test_received_clock_uses_time_after_http_completes(self):
        bundle,attempt=self.prepare();accepted=NOW+timedelta(seconds=5)
        receipt=install_bundle(self.root/'receiver',bundle,now=accepted,
            attribution={'source_peer_ip':'10.0.0.96','receiver_module_sha256':'f'*64})
        post=Mock(return_value=types.SimpleNamespace(status_code=200,json=lambda:receipt))
        self.assertEqual(receipt,self.send(bundle,'http://receiver.invalid/',post=post,
            attempt_directory=attempt,now=NOW,clock=lambda:accepted))
    def test_missing_or_wrong_ack_attribution_never_saves_completion(self):
        bundle,attempt=self.prepare();valid=self.response(bundle,self.root/'receiver').json()
        for field,value in [('source_peer_ip',None),('source_peer_ip','10.0.0.99'),
                            ('receiver_module_sha256',None),('receiver_module_sha256','bad'),
                            ('receiver_module_sha256','e'*64)]:
            with self.subTest(field=field,value=value):
                receipt=copy.deepcopy(valid)
                if value is None:receipt['attribution'].pop(field)
                else:receipt['attribution'][field]=value
                post=Mock(return_value=types.SimpleNamespace(status_code=200,json=lambda:receipt))
                with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW,max_attempts=1)
                self.assertFalse((attempt/'receipt.json').exists())
    def test_missing_or_invalid_ack_received_clock_never_saves_completion(self):
        bundle,attempt=self.prepare();valid=self.response(bundle,self.root/'receiver').json()
        for clock in (None,'bad','2026-10-13T07:00:00','2026-10-13T06:59:59Z','2026-10-13T07:00:01Z'):
            with self.subTest(clock=clock):
                receipt=copy.deepcopy(valid)
                if clock is None:receipt.pop('received_at')
                else:receipt['received_at']=clock
                post=Mock(return_value=types.SimpleNamespace(status_code=200,json=lambda:receipt))
                with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW,max_attempts=1)
                self.assertFalse((attempt/'receipt.json').exists())
    def test_missing_intended_ack_target_prevents_dispatch(self):
        bundle,attempt=self.prepare();post=Mock()
        with self.assertRaises(ValueError):exporter.send_bundle(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        post.assert_not_called();self.assertFalse((attempt/'delivery-attempts.json').exists())
    def test_repeated_successful_invocations_use_one_reservation_and_dispatch(self):
        bundle,attempt=self.prepare();post=Mock(side_effect=lambda url,**kw:self.response(kw['json'],self.root/'receiver'))
        first=self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        before={p.name:p.read_bytes() for p in attempt.iterdir() if p.is_file()}
        for minutes in range(1,13):
            self.assertEqual(first,self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW+timedelta(minutes=minutes)))
        self.assertEqual(post.call_count,1)
        self.assertEqual(before,{p.name:p.read_bytes() for p in attempt.iterdir() if p.is_file()})
        self.assertEqual(len(json.loads((attempt/'delivery-attempts.json').read_text())['events']),1)
    def test_success_on_ninth_reservation_remains_completed_after_restart(self):
        bundle,attempt=self.prepare()
        events=[{'number':i,'status':'failed'} for i in range(1,9)]
        (attempt/'delivery-attempts.json').write_bytes(canonical({'delivery_id':bundle['delivery_id'],'events':events}))
        post=Mock(side_effect=lambda url,**kw:self.response(kw['json'],self.root/'receiver'))
        first=self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(first,self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW))
        self.assertEqual(post.call_count,1)
        self.assertEqual(len(json.loads((attempt/'delivery-attempts.json').read_text())['events']),9)
    def test_saved_success_is_completed_after_bundle_expiry_without_dispatch(self):
        bundle,attempt=self.prepare();post=Mock(side_effect=lambda url,**kw:self.response(kw['json'],self.root/'receiver'))
        first=self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(first,self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW+timedelta(hours=25)))
        self.assertEqual(post.call_count,1)
    def test_saved_receipt_before_journal_completion_recovers_without_dispatch(self):
        bundle,attempt=self.prepare();receipt=self.response(bundle,self.root/'receiver').json()
        (attempt/'receipt.json').write_bytes(canonical(receipt))
        (attempt/'delivery-attempts.json').write_bytes(canonical({'delivery_id':bundle['delivery_id'],'status':'in_progress','events':[{'number':1,'status':'reserved'}]}))
        post=Mock();self.assertEqual(receipt,self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW))
        post.assert_not_called()
        journal=json.loads((attempt/'delivery-attempts.json').read_text())
        self.assertEqual(journal['status'],'acknowledged');self.assertEqual(journal['events'][0]['status'],'acknowledged')
    def test_corrupt_saved_receipt_does_not_return_success_or_dispatch(self):
        bundle,attempt=self.prepare();receipt=self.response(bundle,self.root/'receiver').json()
        receipt['attribution']['receiver_module_sha256']='e'*64
        (attempt/'receipt.json').write_bytes(canonical(receipt));post=Mock()
        with self.assertRaises(ValueError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        post.assert_not_called()
    def test_journal_ack_without_receipt_recovers_actual_receipt(self):
        bundle,attempt=self.prepare();post=Mock(side_effect=lambda url,**kw:self.response(kw['json'],self.root/'receiver'))
        first=self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        (attempt/'receipt.json').unlink()
        second=self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(first,second);self.assertEqual(post.call_count,2)
    def test_internal_upload_uses_bounded_timeout_and_exact_ack(self):
        bundle,attempt=self.prepare();receiver=self.root/'receiver';post=Mock(side_effect=lambda url,**kw:self.response(kw['json'],receiver))
        receipt=self.send(bundle,'http://receiver.invalid/update_volume_lists',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(receipt['delivery_id'],bundle['delivery_id'])
        self.assertEqual(post.call_args.kwargs['timeout'],(5,15));self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertTrue((attempt/'receipt.json').is_file())
    def test_failed_upload_exhausts_three_attempts_without_false_receipt(self):
        bundle,attempt=self.prepare();post=Mock(side_effect=TimeoutError('synthetic'))
        with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(post.call_count,3);self.assertFalse((attempt/'receipt.json').exists())
        self.assertEqual(json.loads((attempt/'delivery-attempts.json').read_text())['status'],'failed')
    def test_failed_http_status_is_not_delivery(self):
        bundle,attempt=self.prepare();post=Mock(return_value=types.SimpleNamespace(status_code=503))
        with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW,max_attempts=1)
        self.assertFalse((attempt/'receipt.json').exists())
    def test_wrong_acknowledged_hash_or_identity_fails(self):
        bundle,attempt=self.prepare()
        receipt={'status':'verified','delivery_id':bundle['delivery_id'],'csv_sha256':{name:'0'*64 for name in FILES}}
        post=Mock(return_value=types.SimpleNamespace(status_code=200,json=lambda:receipt))
        with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW,max_attempts=1)
        self.assertFalse((attempt/'receipt.json').exists())
    def test_lost_successful_response_retries_same_installed_identity(self):
        bundle,attempt=self.prepare();receiver=self.root/'receiver';calls=[]
        def post(url,**kw):
            calls.append(kw['json']['delivery_id']);response=self.response(kw['json'],receiver)
            if len(calls)==1:raise TimeoutError('lost successful response')
            return response
        self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(calls,[bundle['delivery_id']]*2)
        self.assertEqual(len(list((receiver/'.volume-generations').iterdir())),1)
    def test_retry_allowance_cannot_be_increased(self):
        bundle,attempt=self.prepare();post=Mock()
        with self.assertRaises(ValueError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW,max_attempts=4)
        post.assert_not_called()
    def test_default_cli_has_no_upload_or_generation(self):
        with patch.object(exporter,'prepare_attempt') as prepare,self.assertRaises(SystemExit):exporter.main([])
        prepare.assert_not_called()
    def test_persisted_nine_attempt_cap_survives_three_restarts(self):
        bundle,attempt=self.prepare();post=Mock(side_effect=TimeoutError('synthetic'))
        for _ in range(3):
            with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(post.call_count,9)
        with self.assertRaises(RuntimeError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        self.assertEqual(post.call_count,9)
        self.assertEqual(len(json.loads((attempt/'delivery-attempts.json').read_text())['events']),9)
    def test_unknown_reserved_dispatch_stays_consumed_after_restart(self):
        bundle,attempt=self.prepare()
        (attempt/'delivery-attempts.json').write_bytes(canonical({'delivery_id':bundle['delivery_id'],'events':[{'number':1,'status':'reserved'}]}))
        post=Mock(side_effect=lambda url,**kw:self.response(kw['json'],self.root/'receiver'))
        self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        events=json.loads((attempt/'delivery-attempts.json').read_text())['events']
        self.assertEqual(events[0]['status'],'reserved');self.assertEqual(events[1]['number'],2)
    def test_malformed_journal_prevents_dispatch(self):
        bundle,attempt=self.prepare();post=Mock()
        (attempt/'delivery-attempts.json').write_bytes(canonical({'delivery_id':bundle['delivery_id'],'events':[{'number':99,'status':'fake'}]}))
        with self.assertRaises(ValueError):self.send(bundle,'http://receiver.invalid/',post=post,attempt_directory=attempt,now=NOW)
        post.assert_not_called()
    def test_weekend_completion_is_reused_with_real_date_and_new_daily_cache(self):
        saturday=datetime(2026,10,17,7,tzinfo=timezone.utc);monday=saturday+timedelta(days=2)
        self.marker.write_text(json.dumps(valid_marker(saturday)))
        self.write_price('HPQ',end=datetime(2026,10,16));self.write_price('JPM',end=datetime(2026,10,16))
        with patch.object(Clock,'instant',saturday):
            first,a=exporter.prepare_attempt(self.marker,self.state,'d'*40,now=saturday)
        with patch.object(Clock,'instant',monday):
            second,b=exporter.prepare_attempt(self.marker,self.state,'d'*40,now=monday)
        self.assertNotEqual(a,b);self.assertNotEqual(first['delivery_id'],second['delivery_id'])
        self.assertEqual(second['files'][FILES[0]]['provenance']['observations']['HPQ']['observation_date'],'2026-10-16')
    def test_holiday_source_session_uses_existing_calendar(self):
        thursday=datetime(2026,11,26,7,tzinfo=timezone.utc);friday=thursday+timedelta(days=1)
        self.marker.write_text(json.dumps(valid_marker(thursday)))
        proof=exporter.completion_proof(self.marker,now=friday)
        self.assertEqual(proof['completed_session'],'2026-11-25')

if __name__=='__main__':unittest.main()
