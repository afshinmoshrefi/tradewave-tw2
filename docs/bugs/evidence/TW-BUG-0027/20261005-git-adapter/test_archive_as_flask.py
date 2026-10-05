"""Actual Linux archive verification against a Flask-owned, isolated Git fixture."""
from pathlib import Path
import hashlib,importlib.util,io,json,os,pwd,subprocess,sys,tarfile,tempfile
operator=Path(sys.argv[1]).resolve()
spec=importlib.util.spec_from_file_location('candidate_operator',operator)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
with tempfile.TemporaryDirectory(prefix='smn-git-owner-proof-') as tmp:
    root=Path(tmp);root.chmod(0o755)
    repo=root/'repo';repo.mkdir()
    user=pwd.getpwnam('flask');os.chown(repo,user.pw_uid,user.pw_gid)
    def git(*args):
        return subprocess.check_output(['sudo','-u','flask','git','-C',str(repo),*args])
    git('init','-q');git('config','user.name','Isolated SMN Test');git('config','user.email','test@example.invalid')
    data={'app.py':b'print("fixture")\n','legacy.md':b'Legacy \x96 text\n'}
    for name,body in data.items():(repo/name).write_bytes(body)
    git('add','.');git('commit','-qm','Isolated fixture');c.SHA=git('rev-parse','HEAD').decode().strip()
    direct=subprocess.run(['/usr/bin/git','-C',str(repo),'rev-parse','HEAD'],capture_output=True)
    assert direct.returncode==128 and b'dubious ownership' in direct.stderr
    def archive(path,change=False):
        with tarfile.open(path,'w') as tar:
            for name,body in data.items():
                body=body.replace(b'\n',b'\r\n')
                if change and name=='app.py':body+=b'changed\r\n'
                info=tarfile.TarInfo(name);info.size=len(body);tar.addfile(info,io.BytesIO(body))
    good=root/'good.tar';archive(good)
    verified=c.verify_archive_equivalence(good,repo)
    assert verified=={'files':2,'crlf_normalized':2}
    bad=root/'bad.tar';archive(bad,True)
    try:c.verify_archive_equivalence(bad,repo)
    except ValueError as e:assert 'beyond CRLF' in str(e)
    else:raise AssertionError('Changed application accepted')
    print(json.dumps({'operator_sha256':hashlib.sha256(operator.read_bytes()).hexdigest(),
      'isolated_linux_fixture':True,'direct_root_git_reproduced_dubious_ownership':True,
      'archive_read_as_flask_passed':verified,'changed_blob_rejected':True,
      'production_actions':False,'passed':True},indent=2))
