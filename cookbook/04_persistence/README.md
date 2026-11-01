# Persistence

| File | Shows | You should see |
|---|---|---|
| [01_persist_and_resume.py](01_persist_and_resume.py) | A SQLite file keeps the learned state across a restart | `same learned state after reopening: True`, then learning continues |
| [02_crash_and_orphans.py](02_crash_and_orphans.py) | An incident left waiting by a crashed host, a strict policy stuck behind it, and the start-up censoring that frees it | `awaiting_result`, then `PolicyBusy`, then `censored` and a policy that accepts incidents again |

Use an absolute path for `db_url` in real code: the default is relative to the folder you start from. Keep one process per database file, because policy locks live in process memory.
