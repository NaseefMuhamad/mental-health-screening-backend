from pathlib import Path
import sys,unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_permissions as fixtures
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.database.entities import Screening,AuditEvent
from app.services import screening_service
from app.services.errors import Conflict

class CleanupTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.StaffPermissionsTests.setUpClass.__func__)
    setUp=fixtures.StaffPermissionsTests.setUp
    login=fixtures.StaffPermissionsTests.login
    headers=fixtures.StaffPermissionsTests.headers
    student=fixtures.StaffPermissionsTests.student
    case=fixtures.StaffPermissionsTests.case

    def test_take_case_is_one_step_idempotent_and_private(self):
        case=self.case(assign=False)
        path=f"/screenings/{case['id']}/begin-review"
        response=self.client.post(path,headers=self.headers('counsellor'))
        self.assertEqual(response.status_code,200,response.text);row=response.json()
        self.assertEqual(row['assigned_counsellor_id'],self.ids['counsellor']);self.assertEqual(row['assigned_counsellor_name'],'counsellor');self.assertEqual(row['review_status'],'in_review')
        self.assertEqual(self.client.post(path,headers=self.headers('counsellor')).status_code,200)
        self.assertEqual(self.client.post(path,headers=self.headers('other_counsellor')).status_code,409)
        self.assertEqual(self.client.get(f"/screenings/{case['id']}/assessment",headers=self.headers('other_counsellor')).status_code,404)
        self.assertEqual(self.client.post(path,headers=self.headers('officer')).status_code,403)
        self.assertEqual(self.client.post(path,headers=self.headers('admin')).status_code,403)

    def test_simultaneous_take_has_exactly_one_owner(self):
        from uuid import UUID
        case=self.case(assign=False)
        def take(role):
            with Session(self.engine,expire_on_commit=False) as db:
                try:
                    value=screening_service.begin_review(db,UUID(case['id']),actor_id=UUID(self.ids[role]));return ('ok',str(value.assigned_counsellor_id))
                except Conflict:return ('conflict',role)
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(take,['counsellor','other_counsellor']))
        self.assertEqual(sum(status=='ok' for status,_ in results),1,results)
        self.assertEqual(sum(status=='conflict' for status,_ in results),1,results)

    def test_transfer_names_and_personal_case_filter(self):
        case=self.case(begin=True)
        response=self.client.post(f"/screenings/{case['id']}/handover",headers=self.headers(),json={'assigned_counsellor_id':self.ids['other_counsellor'],'reason':'Test transfer'})
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['assigned_counsellor_name'],'other_counsellor')
        self.assertEqual(self.client.get('/screenings',headers=self.headers('counsellor'),params={'assigned_only':True}).json()['total'],0)
        self.assertEqual(self.client.get('/screenings',headers=self.headers('other_counsellor'),params={'assigned_only':True}).json()['total'],1)
        queue=self.client.get('/reports/counsellor-queue',headers=self.headers('counsellor')).json()
        self.assertEqual(queue['items'][0]['assigned_counsellor_name'],'other_counsellor')

    def test_activity_is_aggregate_and_role_scoped(self):
        self.case(submit=False,assign=False);self.case(assign=False)
        for role,expected in [('admin',2),('officer',2),('other_officer',0),('counsellor',1)]:
            response=self.client.get('/reports/activity',headers=self.headers(role));self.assertEqual(response.status_code,200,response.text)
            data=response.json();self.assertEqual(data['timezone'],'UTC');self.assertEqual(len(data['items']),7);self.assertEqual(sum(item['screenings'] for item in data['items']),expected)
            self.assertNotIn('measurements',response.text)

    def test_institution_default_and_preserve_on_edit(self):
        first=self.student()
        settings=self.client.get('/students/registration-settings',headers=self.headers('officer'));self.assertEqual(settings.status_code,200,settings.text);self.assertEqual(settings.json()['institution'],'Demo Institution')
        body={'student_code':'SECOND-001','name':'Second Student','age':21,'department':'Electrical Engineering','academic_year':'2'}
        response=self.client.post('/students',headers=self.headers('officer'),json=body);self.assertEqual(response.status_code,201,response.text);self.assertEqual(response.json()['institution'],'Demo Institution')
        updated={k:v for k,v in body.items() if k!='student_code'}
        response=self.client.patch(f"/students/{first['id']}",headers=self.headers('officer'),json=updated);self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['institution'],'Demo Institution')

    def test_malformed_model_response_becomes_safe_service_error(self):
        from io import BytesIO
        self.model_mock.stop()
        from app.services import ml_client
        from app.services.errors import DependencyUnavailable
        with patch('urllib.request.urlopen',return_value=BytesIO(b'[]')):
            with self.assertRaises(DependencyUnavailable):ml_client.predict({})

if __name__=='__main__':unittest.main()
