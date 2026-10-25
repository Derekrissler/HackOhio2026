"""No live services: verify identity mapping, cookie protections and client separation."""
from types import SimpleNamespace

from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
import pytest

from tutor.auth import COOKIE, LoginBody, identity, login, logout
from tutor.models import Learner
from tutor.repo import SupabaseTutorRepo
from tutor.service import NotFound

UID = '00000000-0000-0000-0000-000000000001'
CID = '00000000-0000-0000-0000-000000000002'
LID = '00000000-0000-0000-0000-000000000003'


class Query:
    def __init__(self, rows): self.rows, self.filters = rows, []
    def select(self, columns): return self
    def eq(self, key, value): self.filters.append((key,value)); return self
    def limit(self, n): return self
    def order(self, *args, **kwargs): return self
    def execute(self):
        return SimpleNamespace(data=[row for row in self.rows if all(row.get(k)==v for k,v in self.filters)])


class Reader:
    def __init__(self):
        self.tables = {'courses':[{'id':CID,'canvas_id':'1001'}],
                       'enrollments':[{'course_id':CID,'user_id':UID,'role':'student'}],
                       'learner_identities':[{'course_id':CID,'user_id':UID,'learner_id':LID}],
                       'learners':[{'id':LID,'course_id':CID,'pseudonym':'Fictional-1'}]}
        self.auth = SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=UID)),
            sign_in_with_password=lambda body:SimpleNamespace(session=SimpleNamespace(access_token='fictional-access',expires_in=3600)))
        self.rpc_calls = []
    def table(self, name): return Query(self.tables.get(name,[]))
    def rpc(self, name, params):
        self.rpc_calls.append((name,params))
        return SimpleNamespace(execute=lambda:SimpleNamespace(data=[]))


@pytest.fixture
def boundary(monkeypatch):
    import supabase_client
    reader = Reader()
    tokens=[]
    def client(token=None): tokens.append(token); return reader
    monkeypatch.setattr(supabase_client,'user_client',client)
    app=FastAPI()
    @app.api_route('/courses/{course_id}/identity',methods=['GET','POST'])
    def who(course_id:str, request:Request):
        _, learner=identity(request,course_id)
        return {'learner_id':learner.learner_id,'role':learner.role}
    @app.post('/courses/{course_id}/login')
    def sign_in(course_id:str,body:LoginBody,request:Request,response:Response): return login(body,request,response)
    @app.post('/courses/{course_id}/logout')
    def sign_out(course_id:str,request:Request,response:Response): return logout(request,response)
    return TestClient(app), reader, tokens


def test_demo_identity_and_pseudonym_cannot_authorize(boundary):
    client,_,_=boundary
    client.cookies.set('demo_user','1')
    assert client.get('/courses/1001/identity',headers={'X-Demo-User':'1'}).status_code==401


def test_verified_user_resolves_own_mapping(boundary):
    client,reader,tokens=boundary
    reader.tables['learner_identities'].append({'course_id':CID,'user_id':'other','learner_id':'other-learner'})
    response=client.get('/courses/1001/identity?learner_id=other-learner',headers={'Authorization':'Bearer fictional-access'})
    assert response.json()=={'learner_id':LID,'role':'student'} and tokens==['fictional-access']


@pytest.mark.parametrize('missing',['enrollments','learner_identities','learners'])
def test_missing_authorization_data_fails_closed(boundary,missing):
    client,reader,_=boundary
    reader.tables[missing]=[]
    assert client.get('/courses/1001/identity',headers={'Authorization':'Bearer fictional-access'}).status_code==403


def test_invalid_user_token_is_not_replaced_by_demo(boundary):
    client,reader,_=boundary
    def bad(token): raise ValueError('private-auth-diagnostic')
    reader.auth.get_user=bad
    response=client.get('/courses/1001/identity',headers={'Authorization':'Bearer invalid','X-Demo-User':'1'})
    assert response.status_code==401 and 'private-auth' not in response.text


def test_login_cookie_and_same_origin_write_protection(boundary):
    client,_,_=boundary
    body={'email':'fictional@example.invalid','password':'fictional-password'}
    assert client.post('/courses/1001/login',json=body).status_code==403
    assert client.post('/courses/1001/login',json=body,headers={'X-Tutor-Request':'1','Origin':'https://elsewhere.invalid'}).status_code==403
    response=client.post('/courses/1001/login',json=body,headers={'X-Tutor-Request':'1'})
    assert response.json()=={'signed_in':True}
    assert 'HttpOnly' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert 'fictional-access' not in response.text and 'fictional-password' not in response.text
    assert response.headers['cache-control']=='no-store'
    assert client.get('/courses/1001/identity').status_code==200
    assert client.post('/courses/1001/identity').status_code==403
    assert client.post('/courses/1001/identity',headers={'X-Tutor-Request':'1'}).status_code==200
    client.post('/courses/1001/logout',headers={'X-Tutor-Request':'1'})
    assert client.get('/courses/1001/identity').status_code==401


def test_requests_do_not_reuse_previous_identity(boundary):
    client,reader,tokens=boundary
    assert client.get('/courses/1001/identity',headers={'Authorization':'Bearer first'}).status_code==200
    reader.tables['learner_identities']=[]
    assert client.get('/courses/1001/identity',headers={'Authorization':'Bearer second'}).status_code==403
    assert tokens==['first','second']


def test_rpc_uses_user_client_and_denies_other_course_and_sessions():
    reader=Reader()
    class Writer:
        def rpc(self,*args): raise AssertionError('privileged retrieval forbidden')
        def table(self,*args): raise AssertionError('unauthorized write')
    repo=SupabaseTutorRepo(Writer(),reader,Learner(CID,LID,'Fictional-1'))
    assert repo.search(CID,'question',[],6)==[]
    assert reader.rpc_calls[0][0]=='search_resource_chunks'
    assert reader.rpc_calls[0][1]['p_student_safe'] is True
    with pytest.raises(NotFound): repo.search('other-course','question',[],6)
    with pytest.raises(NotFound): repo.add_turns('other-session',[{'content':'no'}])
    with pytest.raises(NotFound): repo.create_session(Learner(CID,'other','other'), 'independent_study',None,None)


def test_shared_api_settings_fallback_does_not_mix_project_urls(monkeypatch):
    import supabase_client
    monkeypatch.setattr(supabase_client,'_shared_settings',{'SUPABASE_URL':'https://shared.invalid','SUPABASE_SECRET_KEY':'fictional-server-key'})
    monkeypatch.setenv('SUPABASE_URL','https://shared.invalid')
    monkeypatch.setenv('SUPABASE_SECRET_KEY','YOUR-SECRET-KEY')
    monkeypatch.delenv('SUPABASE_SERVICE_ROLE_KEY',raising=False)
    assert supabase_client._env('SUPABASE_SECRET_KEY')=='fictional-server-key'
    monkeypatch.setenv('SUPABASE_URL','https://different.invalid')
    with pytest.raises(RuntimeError): supabase_client._env('SUPABASE_SECRET_KEY')


@pytest.mark.parametrize('placeholder',['REPLACE_ME','YOUR-SECRET-KEY'])
def test_ingestion_preflight_rejects_both_placeholder_forms(monkeypatch,placeholder):
    import db_store
    import supabase_client
    monkeypatch.setattr(supabase_client,'_shared_settings',{})
    monkeypatch.setenv('SUPABASE_URL','https://fictional.invalid')
    for key in supabase_client.SERVICE_KEY_NAMES:
        monkeypatch.setenv(key,placeholder)
    assert db_store.configured() is not None


def test_ingestion_preflight_uses_project_safe_api_fallback(monkeypatch):
    import db_store
    import supabase_client
    monkeypatch.setattr(supabase_client,'_shared_settings',{
        'SUPABASE_URL':'https://fictional-shared.invalid','SUPABASE_SECRET_KEY':'fictional-key'})
    for key in ('SUPABASE_URL',*supabase_client.SERVICE_KEY_NAMES):
        monkeypatch.delenv(key,raising=False)
    assert db_store.configured() is None
    monkeypatch.setenv('SUPABASE_URL','https://different.invalid')
    assert db_store.configured() is not None
