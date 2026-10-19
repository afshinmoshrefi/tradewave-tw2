"""Focused checks for new wrapper's effective systemd source-path binding."""
from pathlib import Path, PurePosixPath
import ast, types, unittest

ROOT=Path(__file__).resolve().parent
primitive=ROOT/'qualified-retained-operator.py'
if not primitive.is_file():primitive=ROOT/'smn-deployment-678477ab-20261009-v3-r2/operator/cutover-app-refresh.py'
tree=ast.parse(primitive.read_bytes())
projection=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='execstart_projection')
space={'re':__import__('re'),'hashlib':__import__('hashlib'),'require':lambda value,message: None if value else (_ for _ in ()).throw(ValueError(message))}
exec(compile(ast.Module(body=[projection],type_ignores=[]),'qualified-projection','exec'),space)
cutover=ROOT/'bounded-cutover.py'
if not cutover.is_file():cutover=ROOT/'smn-oct19-bounded-cutover.py'
wrapper=ast.parse(cutover.read_bytes())
effective=next(node for node in wrapper.body if isinstance(node,ast.FunctionDef) and node.name=='effective')
OLD='2b0075c85e45d8cd547c95b8868f8560532cf86b';NEW='55afe01a5683c6f2471e0d578867ad77390bb739'
BASE=PurePosixPath('/opt/smn-subscription')
def info(source,clock='16:31:00',pid=100):
    path=str(BASE/'releases'/source/'blog/operational_schedule.py')
    return {'FragmentPath':'/etc/systemd/system/smn-weekday-newsletter.service','DropInPaths':'/etc/systemd/system/smn-weekday-newsletter.service.d/10-release-git.conf',
      'WorkingDirectory':str(BASE/'releases'/source/'blog'),
      'ExecStart':'{ path=/home/flask/venv/bin/python ; argv[]=/home/flask/venv/bin/python '+path+' --target production --newsletter-only ; ignore_errors=no ; start_time=[Mon 2026-10-19 '+clock+' UTC] ; stop_time=[Mon 2026-10-19 '+clock+' UTC] ; pid='+str(pid)+' ; code=exited ; status=0 }'}
class Bindings(unittest.TestCase):
    def run_case(self,current,expected=NEW):
        ctx={'BASE':BASE,'baseline':{'services':{'mail':info(OLD)}},'op':types.SimpleNamespace(execstart_projection=space['execstart_projection'],OLD_RELEASE=BASE/'releases'/OLD),
             'services':lambda:{'mail':current},'require':space['require']}
        exec(compile(ast.Module(body=[effective],type_ignores=[]),'wrapper-effective','exec'),ctx)
        return ctx['effective'](expected)
    def test_exact_new_source_allows_runtime_observation_changes(self):self.run_case(info(NEW,'16:36:01',200))
    def test_exact_old_source_rollback(self):self.run_case(info(OLD,'16:36:01',200),OLD)
    def test_old_pinned_command_rejected(self):
        with self.assertRaises(ValueError):self.run_case(info(OLD))
    def test_wrong_cwd_rejected(self):
        row=info(NEW);row['WorkingDirectory']=info(OLD)['WorkingDirectory']
        with self.assertRaises(ValueError):self.run_case(row)
    def test_dropin_drift_rejected(self):
        row=info(NEW);row['DropInPaths']+=' /etc/systemd/system/smn-weekday-newsletter.service.d/99-other.conf'
        with self.assertRaises(ValueError):self.run_case(row)
    def test_sender_instead_of_scheduler_rejected(self):
        row=info(NEW);row['ExecStart']=row['ExecStart'].replace('operational_schedule.py','send_smn_emails.py')
        with self.assertRaises(ValueError):self.run_case(row)
if __name__=='__main__':unittest.main()
