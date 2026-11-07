# Student wellbeing backend

FastAPI owns authentication, staff permissions, student records, screenings, predictions, counselling and follow-ups. PostgreSQL runs in the existing Docker setup. The frontend calls this API; this API calls the separate loopback ML service.

## Setup

From the backend root, activate its existing virtual environment and install runtime dependencies:

```powershell
python -m pip install -r requirements.txt
```

Merge the .env.example settings into the backend root .env, keeping the real database password private. Do not overwrite a working .env with the template. DB_NAME is mental_health_screening in the current setup. DATABASE_URL, if present, takes precedence over separate DB_* settings.

For initial setup of a new database:

```powershell
python -m app.database.init_db --check
python -m app.database.init_db --create-tables
python -m app.auth.bootstrap_admin --email "admin@example.org" --name "Institution Administrator"
```

Use the existing administrator if already created; do not recreate the project database. The bootstrap command prompts privately for a 12–128-character password. Start the API:

```powershell
python -m uvicorn app.main:app --reload
```

API documentation: http://127.0.0.1:8000/docs. The frontend origin defaults to http://127.0.0.1:5173. ML_SERVICE_URL defaults to http://127.0.0.1:8010; start the trained service from the ML repository's own environment.

## Case workflow and permissions

- Screening personnel register/edit students, collect heart rate and five contextual demo values, and submit their own cases. Submission automatically runs prediction; drafts do not.
- Counsellors see every submitted case and separate stress/anxiety categories. On an unclaimed submitted case, begin-review atomically sets the caller as responsible and starts counselling. A second counsellor cannot overwrite ownership. Repeating the action by the same owner is idempotent.
- The responsible counsellor can verify screening answers, record confidential counselling and manage follow-ups. Other counsellors can still see the screening results but not private notes or answers.
- Administrators manage staff, view operational information and transfer responsibility. The legacy assignment endpoint is retained for compatibility, but is not required in the normal interface. Transfers preserve authorship, notes and history and move scheduled appointments to the new responsible counsellor.
- Deactivation revokes sessions immediately and preserves records. Transfer outstanding cases as needed; never delete accounts to remove access.

Claiming, staff management and transfers use a consistent locking order, with an atomic conditional case update. Existing owners are not changed by this cleanup. No database migration is needed for the display relationships or new read endpoints.

## Institution and reports

Set INSTITUTION_NAME once in .env if desired. Otherwise registration uses the single institution already on file. A new deployment can supply the name for its first registration. Student updates that omit institution preserve the existing value.

GET /reports/counsellor-queue is paginated and returns only submitted-case summaries and current-input predictions. GET /reports/activity returns seven aggregated UTC dates within the caller's role scope, rather than exposing full measurement histories for charts. Personal counselling lists can use assigned_only=true on GET /screenings.

Prediction/assessment snapshots are preserved. A failed ML request does not lose a submitted screening. Model categories are simulated-data estimates, not diagnoses. Depression has no model in this dataset.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests use isolated SQLite storage and fictional users, not the configured PostgreSQL records. They check role access, automatic prediction handoff, case ownership/concurrent claims, transfers, dashboard scopes, malformed-model responses and institution defaults. PostgreSQL-specific behavior should also be checked before deployment.
