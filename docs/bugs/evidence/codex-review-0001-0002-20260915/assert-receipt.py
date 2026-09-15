import json, sys
from pathlib import Path
for name in sys.argv[1:]:
    receipt = json.loads(Path(name).read_text())
    assert receipt.get('execution_complete'), name + ': execution incomplete'
    assert receipt.get('cases'), name + ': no cases'
    assert all(case.get('pass') for case in receipt['cases']), name + ': case failure'
    assert not receipt.get('errors'), name + ': browser error'
    assert not receipt.get('consoleErrors'), name + ': console error (inspect before accepting)'
    print(name + ': ' + str(len(receipt['cases'])) + ' cases passed')
