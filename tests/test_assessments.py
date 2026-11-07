from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import test_permissions as fixtures
from app.services.errors import DependencyUnavailable

class ScreeningHandoffTests(unittest.TestCase):
    setUpClass=classmethod(fixtures.StaffPermissionsTests.setUpClass.__func__)
    setUp=fixtures.StaffPermissionsTests.setUp
    login=fixtures.StaffPermissionsTests.login
    headers=fixtures.StaffPermissionsTests.headers
    student=fixtures.StaffPermissionsTests.student
    case=fixtures.StaffPermissionsTests.case
    answers={'sleep_hours':7,'screen_time':5,'assignment_load':5,'exam_pressure':5,'social_support':5}

    def create(self,submit=True,answers=True):
        student=self.student()
        body={'student_id':student['id'],'measured_at':'2026-11-06T10:00:00Z','measurements':{'heart_rate_bpm':78},'submit_for_review':submit}
        if answers:body['assessment']=self.answers
        return self.client.post('/screenings',headers=self.headers('officer'),json=body)

    def queue(self,role='counsellor',**params):
        return self.client.get('/reports/counsellor-queue',headers=self.headers(role),params=params)

    def test_submit_runs_prediction_before_assignment_and_reaches_dashboard(self):
        response=self.create();self.assertEqual(response.status_code,201,response.text);case=response.json()
        self.assertEqual(case['review_status'],'awaiting_review');self.assertEqual(case['prediction_status'],'available');self.assertIsNone(case['assigned_counsellor_id'])
        self.assertNotIn('stress_level',case)
        row=self.queue().json()['items'][0];self.assertEqual(row['id'],case['id']);self.assertEqual(row['stress_level'],'Medium');self.assertEqual(row['anxiety_level'],'Low');self.assertEqual(row['student_name'],'Demo Student')
        self.assertFalse(row['assigned_to_me']);self.assertNotIn('inputs',row);self.assertNotIn('notes',row)
        self.assertEqual(self.queue('admin').status_code,403);self.assertEqual(self.queue('officer').status_code,403)

    def test_draft_and_legacy_completion(self):
        with patch('app.services.ml_client.predict') as infer:
            draft=self.create(submit=False).json();self.assertEqual(draft['review_status'],'draft');infer.assert_not_called()
        self.assertEqual(self.queue().json()['total'],0)
        response=self.client.post(f"/screenings/{draft['id']}/submit",headers=self.headers('officer'));self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['prediction_status'],'available')
        legacy=self.create(submit=False,answers=False).json()
        self.assertEqual(self.client.post(f"/screenings/{legacy['id']}/submit",headers=self.headers('officer')).status_code,409)
        response=self.client.post(f"/screenings/{legacy['id']}/assessment",headers=self.headers('officer'),json=self.answers);self.assertEqual(response.status_code,201,response.text)
        self.assertEqual(self.client.post(f"/screenings/{legacy['id']}/submit",headers=self.headers('officer')).status_code,200)

    def test_collection_permissions_and_submitted_answers_are_immutable(self):
        draft=self.create(submit=False).json();path=f"/screenings/{draft['id']}/assessment"
        for role,expected in [('admin',403),('counsellor',403),('other_officer',404)]:self.assertEqual(self.client.post(path,headers=self.headers(role),json=self.answers).status_code,expected)
        self.assertEqual(self.client.get(path,headers=self.headers('officer')).status_code,200)
        self.client.post(f"/screenings/{draft['id']}/submit",headers=self.headers('officer'))
        self.assertEqual(self.client.post(path,headers=self.headers('officer'),json=self.answers).status_code,409)
        self.client.put(f"/screenings/{draft['id']}/assignment",headers=self.headers(),json={'assigned_counsellor_id':self.ids['counsellor']})
        self.assertEqual(self.client.get(path,headers=self.headers('counsellor')).status_code,200)
        self.assertEqual(self.client.get(path,headers=self.headers('other_counsellor')).status_code,404)

    def test_inference_failure_preserves_submission_and_retry_is_idempotent(self):
        with patch('app.services.ml_client.predict',side_effect=DependencyUnavailable('Stopped for test')):
            response=self.create()
        self.assertEqual(response.status_code,201,response.text);case=response.json();self.assertEqual(case['review_status'],'awaiting_review');self.assertEqual(case['prediction_status'],'failed')
        row=self.queue().json()['items'][0];self.assertTrue(row['assessment_complete']);self.assertIsNone(row['stress_level']);self.assertEqual(row['prediction_status'],'failed')
        path=f"/screenings/{case['id']}/retry-prediction"
        self.assertEqual(self.client.post(path,headers=self.headers('other_officer')).status_code,404)
        self.assertEqual(self.client.post(path,headers=self.headers()).status_code,403)
        result={'contract_version':'student-wellbeing-demo-v1','model_version':'retry-test','stress':{'level':'Low'},'anxiety':{'level':'Low'}}
        with patch('app.services.ml_client.predict',return_value=result) as infer:
            for _ in range(2):
                response=self.client.post(path,headers=self.headers('officer'));self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['prediction_status'],'available')
            self.assertEqual(infer.call_count,1)
        row=self.queue().json()['items'][0];self.assertEqual(row['stress_level'],'Low');self.assertEqual(row['anxiety_level'],'Low')

    def test_complete_inputs_and_queue_pagination(self):
        self.assertEqual(self.create(answers=False).status_code,422)
        for _ in range(3):self.create()
        first=self.queue(offset=0,limit=2).json();second=self.queue(offset=2,limit=2).json()
        self.assertEqual(first['total'],3);self.assertEqual(len(first['items']),2);self.assertEqual(len(second['items']),1)
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})

if __name__=='__main__':unittest.main()
