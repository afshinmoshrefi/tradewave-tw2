import pytest
from tara_security_lists import build_security_list_command, requested_security_list, MIDCAP, SP400, STOCKS, FUNDS
import chatbot
import tara_gateway
from flask import Flask
import jwt, time

pytestmark = pytest.mark.unit
ACCESS = {'1':['0'], '4':['4','11'], '6':['4','11']}

def row(name=MIDCAP, **extra):
    return dict(name=name, resource_id='11' if name==FUNDS else '4', symbols=['MSFT','AAPL'], access_levels=['4','6'], enabled=True, **extra)

@pytest.mark.parametrize('question,name',[
 ('show me a list of midcaps',MIDCAP),('mid-cap stocks',MIDCAP),('open S&P MidCap 400',SP400),
 ('list of optionable stocks',STOCKS),('switch to optionable ETFs',FUNDS),('show optionable funds',FUNDS),
 ('how can I select the midcaps list?',MIDCAP),
])
def test_requested_aliases(question,name):
 assert requested_security_list(question)==name

@pytest.mark.parametrize('question',['analyze MSFT','best midcap stocks','what should I buy among optionable stocks?','compare midcaps to large caps'])
def test_does_not_intercept_research(question):
 assert requested_security_list(question) is None

@pytest.mark.parametrize('name',[MIDCAP,SP400,STOCKS,FUNDS])
def test_catalog_action_and_manual_instructions(name):
 result=build_security_list_command('show '+name,'authenticated-token',{'user_level':'4'},lambda *a:(200,{'published_lists':[row(name)]}),ACCESS)
 assert result['actions']==[{'type':'set_view','spec':{'market':'11' if name==FUNDS else '4','published_list':name}}]
 assert '2 symbols' in result['reply'] and 'Published Lists' in result['reply'] and 'check the list' in result['reply']
 assert 'snapshot' in result['reply'] and 'detected patterns' in result['reply']

def test_how_to_does_not_move_view():
 result=build_security_list_command('how can I open midcaps?','token',{'user_level':'4'},lambda *a:(200,{'published_lists':[row()]}),ACCESS)
 assert result['actions']==[]

@pytest.mark.parametrize('catalog,claims',[
 ([],{'user_level':'4'}),([dict(row(),enabled=False)],{'user_level':'4','is_admin':True}),
 ([row()],{'user_level':'1'}),([dict(row(),resource_id='11')],{'user_level':'4'}),
 ([dict(row(),access_levels=['6'])],{'user_level':'4'}),([row(),row()],{'user_level':'4'}),
 ([dict(row(),symbols=['<script>'])],{'user_level':'4'}),
])
def test_unavailable_or_invalid_catalog_never_fires_action(catalog,claims):
 result=build_security_list_command('show midcaps','token',claims,lambda *a:(200,{'published_lists':catalog}),ACCESS)
 assert result['actions']==[]

def test_failed_catalog_is_explicit():
 result=build_security_list_command('show midcaps','token',{'user_level':'4'},lambda *a:(503,{}),ACCESS)
 assert result['actions']==[] and 'could not retrieve' in result['reply']

def test_signed_spec_contains_exact_list_identity():
 spec={'market':'4','published_list':MIDCAP}
 assert chatbot._clean_signed_spec(spec)==spec
 assert tara_gateway._validate_view_spec(spec)==spec
 app=Flask(__name__); app.config['SECRET_KEY']='test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
 with app.app_context():
  prepared=chatbot._prepare_audited_actions('test-user','a'*32,[{'type':'set_view','spec':spec}])
 assert prepared[0]['spec']==spec and prepared[0]['receipt']

@pytest.mark.parametrize('spec',[
 {'published_list':MIDCAP}, {'market':'4','published_list':'<unsafe>','symbol':'MSFT'},
 {'market':'4','published_list':''}, {'market':'4','published_list':'x'*121},
 {'market':'4','published_list':' midcaps'}, {'market':'4','published_list':'é'},
])
def test_malformed_list_specs_rejected_atomically(spec):
 assert chatbot._clean_signed_spec(spec) is None
 assert tara_gateway._validate_view_spec(spec)=={}

def test_authenticated_chat_routes_list_and_acknowledges_exact_name(tmp_path,monkeypatch):
 app=Flask(__name__); app.config['SECRET_KEY']='test-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
 app.register_blueprint(chatbot.chatbot_bp,url_prefix='/chatbot')
 monkeypatch.setattr(chatbot,'QUESTION_LOG',str(tmp_path/'questions.jsonl'))
 monkeypatch.setattr(chatbot,'ACTION_AUDIT_LOG',str(tmp_path/'actions.jsonl'))
 monkeypatch.setattr(chatbot,'_loopback_json',lambda *a:(200,{'published_lists':[row()]}))
 monkeypatch.setattr(chatbot,'_claim_action_result',lambda *a:(True,'memory'))
 token=jwt.encode({'user':'list-test','user_level':'4','aud':'tw2-appserver','iss':'tw2-web','exp':int(time.time())+300},app.config['SECRET_KEY'],algorithm='HS256')
 client=app.test_client()
 response=client.post('/chatbot/chat',json={'token':token,'message':'show me a list of midcaps'})
 assert response.status_code==200
 payload=response.get_json(); action=payload['actions'][0]
 assert action['spec']=={'market':'4','published_list':MIDCAP}
 proof={'action_id':action['action_id'],'spec':action['spec'],'receipt':action['receipt'],'manifest':action['action_manifest'],'expires_at':action['receipt_expires_at']}
 acknowledgement={'token':token,'turn_id':payload['turn_id'],'actions':[proof],'status':'succeeded','observed_view':{'market':'4','published_list':MIDCAP},'data_points':0,'displayed_response':'Securities list selected.'}
 assert client.post('/chatbot/action_result',json=acknowledgement).status_code==200
 acknowledgement['observed_view']['published_list']=SP400
 assert client.post('/chatbot/action_result',json=acknowledgement).status_code==409
