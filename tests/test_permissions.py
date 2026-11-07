"""HTTP tests with real hashing/tokens and isolated storage, never the user's DB."""

from datetime import timedelta
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.auth.security import hash_password, hash_token
from app.database.base import Base
from app.database.connection import get_db
from app.database.entities import AuthSession, Invitation, User, utc_now
from app.main import create_app


PASSWORD = "Fictional-password-for-tests-2046"


class StaffPermissionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = hash_password(PASSWORD)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name)/'api.db'}", connect_args={"check_same_thread":False})
        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        self.ids = {}
        with Session(self.engine) as db:
            for name, role, active in [
                ("admin","administrator",True), ("officer","screening_personnel",True),
                ("other_officer","screening_personnel",True), ("counsellor","counsellor",True),
                ("other_counsellor","counsellor",True), ("inactive","counsellor",False),
            ]:
                user=User(name=name,email=f"{name}@example.org",email_key=f"{name}@example.org",role=role,
                    is_active=active,password_hash=self.password_hash)
                db.add(user); db.flush(); self.ids[name]=str(user.id)
            db.commit()
        app = create_app()
        def override_db():
            with Session(self.engine, expire_on_commit=False) as db:
                try: yield db
                except BaseException: db.rollback(); raise
        app.dependency_overrides[get_db] = override_db
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.tokens = {}
        self.counter = 0
        self.model_mock = patch('app.services.ml_client.predict',return_value={'contract_version':'student-wellbeing-demo-v1','model_version':'isolated-permission-test','stress':{'level':'Medium'},'anxiety':{'level':'Low'}})
        self.model_mock.start(); self.addCleanup(self.model_mock.stop)

    def login(self, name="admin", password=PASSWORD):
        return self.client.post("/auth/login",json={"email":f"{name}@example.org","password":password})

    def headers(self, name="admin"):
        if name not in self.tokens:
            response=self.login(name)
            self.assertEqual(response.status_code,200,response.text)
            self.tokens[name]=response.json()["access_token"]
        return {"Authorization":f"Bearer {self.tokens[name]}"}

    def student(self):
        self.counter += 1
        response = self.client.post("/students",headers=self.headers("officer"),json={
            "student_code":f"DEMO-{self.counter:03}","name":"Demo Student","age":20,
            "department":"Computing","academic_year":"2","institution":"Demo Institution",
        })
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def case(self, *, submit=True, assign=True, begin=False):
        student=self.student()
        response=self.client.post("/screenings",headers=self.headers("officer"),json={
            "student_id":student["id"],"measured_at":utc_now().isoformat(),"measurements":{"heart_rate_bpm":72},"assessment":{"sleep_hours":7,"screen_time":5,"assignment_load":5,"exam_pressure":5,"social_support":5},
        })
        self.assertEqual(response.status_code,201,response.text)
        case=response.json()
        if submit:
            response=self.client.post(f"/screenings/{case['id']}/submit",headers=self.headers("officer"))
            self.assertEqual(response.status_code,200,response.text);case=response.json()
        if assign:
            response=self.client.put(f"/screenings/{case['id']}/assignment",headers=self.headers(),
                json={"assigned_counsellor_id":self.ids["counsellor"]})
            self.assertEqual(response.status_code,200,response.text);case=response.json()
        if begin:
            response=self.client.post(f"/screenings/{case['id']}/begin-review",headers=self.headers("counsellor"))
            self.assertEqual(response.status_code,200,response.text);case=response.json()
        return case

    def invite(self, email="newstaff@example.org", role="screening_personnel"):
        response=self.client.post("/users/invitations",headers=self.headers(),json={
            "name":"New Demo Staff","email":email,"role":role,
        })
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def test_registration_and_editing_screening_only(self):
        body={"student_code":"ROLE-001","name":"Role Test Student","age":20,"department":"Computing","academic_year":"2","institution":"Test University"}
        for role in ["admin","counsellor"]:
            response=self.client.post("/students",headers=self.headers(role),json=body)
            self.assertEqual(response.status_code,403,response.text)
        student=self.student()
        update={key:value for key,value in body.items() if key!="student_code"}
        for role in ["admin","counsellor"]:
            response=self.client.patch(f"/students/{student['id']}",headers=self.headers(role),json=update)
            self.assertEqual(response.status_code,403,response.text)
        self.assertEqual(self.client.patch(f"/students/{student['id']}",headers=self.headers("officer"),json=update).status_code,200)

    def test_all_roles_see_registered_unscreened_students(self):
        student=self.student()
        for role in ["admin","officer","counsellor","other_counsellor"]:
            self.assertEqual(self.client.get(f"/students/{student['id']}",headers=self.headers(role)).status_code,200)
            response=self.client.get("/students",headers=self.headers(role)).json()
            self.assertEqual(response["total"],1)

    def test_counsellors_read_all_submitted_not_drafts(self):
        draft=self.case(submit=False,assign=False)
        case=self.case(assign=False)
        for role in ["counsellor","other_counsellor"]:
            self.assertEqual(self.client.get(f"/screenings/{draft['id']}",headers=self.headers(role)).status_code,404)
            response=self.client.get(f"/screenings/{case['id']}",headers=self.headers(role))
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn("measurements",response.json())
            self.assertEqual(self.client.get("/screenings",headers=self.headers(role)).json()["total"],1)
            self.assertEqual(self.client.get(f"/predictions/{case['id']}",headers=self.headers(role)).json()["status"],"available")
        self.assertEqual(self.client.post(f"/screenings/{case['id']}/begin-review",headers=self.headers("counsellor")).status_code,200)

    def test_admin_responses_are_operational(self):
        case=self.case()
        self.assertNotIn("measurements",case)
        for path in [f"/screenings/{case['id']}","/screenings"]:
            data=self.client.get(path,headers=self.headers()).json()
            rows=data["items"] if "items" in data else [data]
            self.assertTrue(rows)
            for row in rows:self.assertNotIn("measurements",row)
        self.assertEqual(self.client.get("/counselling",headers=self.headers()).status_code,403)
        self.assertEqual(self.client.get("/followups",headers=self.headers()).status_code,403)

    def test_only_assignee_can_review_or_read_confidential_notes(self):
        case=self.case(begin=True)
        self.assertEqual(self.client.post(f"/screenings/{case['id']}/begin-review",headers=self.headers("other_counsellor")).status_code,409)
        payload={"screening_id":case["id"],"action":"followup_required","occurred_at":utc_now().isoformat(),"notes":"Private test note"}
        self.assertEqual(self.client.post("/counselling",headers=self.headers("other_counsellor"),json=payload).status_code,404)
        self.assertEqual(self.client.post("/counselling",headers=self.headers("counsellor"),json=payload).status_code,201)
        self.assertEqual(self.client.get("/counselling",headers=self.headers("other_counsellor")).json()["total"],0)
        self.assertEqual(self.client.get("/counselling",params={"screening_id":case["id"]},headers=self.headers("other_counsellor")).status_code,404)
        self.assertEqual(self.client.get("/counselling",headers=self.headers("counsellor")).json()["total"],1)
        self.assertEqual(self.client.get(f"/screenings/{case['id']}",headers=self.headers("other_counsellor")).status_code,200)

    def test_followups_stay_private_to_assignee(self):
        case=self.case(begin=True)
        payload={"screening_id":case["id"],"scheduled_for":(utc_now()+timedelta(days=1)).isoformat(),"reason":"Test follow-up"}
        self.assertEqual(self.client.post("/followups",headers=self.headers("other_counsellor"),json=payload).status_code,404)
        response=self.client.post("/followups",headers=self.headers("counsellor"),json=payload)
        self.assertEqual(response.status_code,201,response.text);followup=response.json()
        self.assertEqual(self.client.get("/followups",headers=self.headers("other_counsellor")).json()["total"],0)
        for path,body in [(f"/followups/{followup['id']}/complete",{"outcome":"Denied"}),(f"/followups/{followup['id']}/cancel",{"reason":"Denied"})]:
            self.assertEqual(self.client.post(path,headers=self.headers("other_counsellor"),json=body).status_code,404)
        self.assertEqual(self.client.get(f"/followups/{followup['id']}",headers=self.headers("other_counsellor")).status_code,404)
        self.assertEqual(self.client.patch(f"/followups/{followup['id']}",headers=self.headers("other_counsellor"),json={"scheduled_for":payload["scheduled_for"],"reason":"Denied"}).status_code,404)

    def test_handover_changes_responsibility_without_hiding_screening(self):
        case=self.case(begin=True)
        payload={"screening_id":case["id"],"action":"followup_required","occurred_at":utc_now().isoformat(),"notes":"Private handover note"}
        self.assertEqual(self.client.post("/counselling",headers=self.headers("counsellor"),json=payload).status_code,201)
        response=self.client.post(f"/screenings/{case['id']}/handover",headers=self.headers(),json={"assigned_counsellor_id":self.ids["other_counsellor"],"reason":"Test reassignment"})
        self.assertEqual(response.status_code,200,response.text);self.assertNotIn("measurements",response.json())
        self.assertEqual(self.client.get(f"/screenings/{case['id']}",headers=self.headers("counsellor")).status_code,200)
        self.assertEqual(self.client.get("/counselling",headers=self.headers("counsellor")).json()["total"],0)
        self.assertEqual(self.client.get("/counselling",headers=self.headers("other_counsellor")).json()["total"],1)

    def test_report_scope_and_staff_management(self):
        self.case()
        data=self.client.get("/reports/summary",headers=self.headers("other_counsellor")).json()
        self.assertEqual(data["scope"],"submitted_screenings");self.assertEqual(data["screening_sessions"],1);self.assertEqual(data["scheduled_followups"],0)
        self.assertEqual(self.client.get("/users",headers=self.headers()).status_code,200)
        for role in ["officer","counsellor"]:
            self.assertEqual(self.client.get("/users",headers=self.headers(role)).status_code,403)
        for role in ["admin","counsellor"]:
            student=self.student()
            response=self.client.post("/screenings",headers=self.headers(role),json={"student_id":student["id"],"measured_at":utc_now().isoformat(),"measurements":{"heart_rate_bpm":72}})
            self.assertEqual(response.status_code,403,response.text)

    def test_screening_staff_still_see_only_their_screenings(self):
        case=self.case()
        self.assertEqual(self.client.get(f"/screenings/{case['id']}",headers=self.headers("other_officer")).status_code,404)
        self.assertEqual(self.client.get("/screenings",headers=self.headers("other_officer")).json()["total"],0)

if __name__ == "__main__":
    unittest.main()
