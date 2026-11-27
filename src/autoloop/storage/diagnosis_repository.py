"""保存诊断任务、报告和修复计划。"""

from pathlib import Path
import sqlite3

from autoloop.schemas.diagnosis import DiagnosisRun
from autoloop.schemas.report import DiagnosisReport
from autoloop.storage.execution_store import connect

DIAGNOSIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS diagnosis_runs (
    diagnosis_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS diagnosis_history
ON diagnosis_runs (incident_id, started_at DESC, diagnosis_id);

CREATE TABLE IF NOT EXISTS diagnosis_results (
    diagnosis_id TEXT PRIMARY KEY REFERENCES diagnosis_runs(diagnosis_id),
    result_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repair_plans (
    plan_id TEXT PRIMARY KEY,
    diagnosis_id TEXT UNIQUE NOT NULL REFERENCES diagnosis_results(diagnosis_id),
    incident_id TEXT NOT NULL REFERENCES incidents(id),
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class DiagnosisRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        with connect(path) as db:
            db.executescript(DIAGNOSIS_SCHEMA)

    def start(self, run: DiagnosisRun) -> None:
        with connect(self.path) as db, db:
            db.execute(
                "INSERT INTO diagnosis_runs VALUES (?, ?, ?, ?, ?)",
                (run.diagnosis_id, run.incident_id, run.started_at.isoformat(timespec="microseconds"),
                 run.status, run.model_dump_json()),
            )

    def _update(self, db: sqlite3.Connection, run: DiagnosisRun) -> None:
        changed = db.execute(
            "UPDATE diagnosis_runs SET status=?, payload=? WHERE diagnosis_id=? AND status='RUNNING'",
            (run.status, run.model_dump_json(), run.diagnosis_id),
        )
        if changed.rowcount != 1:
            raise ValueError("诊断任务不存在或已结束")

    def fail(self, run: DiagnosisRun) -> None:
        with connect(self.path) as db, db:
            self._update(db, run)

    def save(self, report: DiagnosisReport) -> None:
        result, plan = report.result, report.plan
        with connect(self.path) as db, db:
            self._update(db, report.run)
            db.execute(
                "INSERT INTO diagnosis_results VALUES (?, ?, ?, ?)",
                (result.diagnosis_id, result.model_dump_json(),
                 report.model_dump_json(include={"evidence"}), result.created_at.isoformat()),
            )
            db.execute(
                "INSERT INTO repair_plans VALUES (?, ?, ?, ?, ?)",
                (plan.plan_id, plan.diagnosis_id, plan.incident_id,
                 plan.model_dump_json(), plan.created_at.isoformat()),
            )

    def history(self, incident_id: str, limit: int, offset: int) -> list[DiagnosisRun]:
        with connect(self.path) as db:
            rows = db.execute(
                """SELECT payload FROM diagnosis_runs WHERE incident_id=?
                ORDER BY started_at DESC, diagnosis_id LIMIT ? OFFSET ?""",
                (incident_id, limit, offset),
            )
            return [DiagnosisRun.model_validate_json(row[0]) for row in rows]

    def get(self, diagnosis_id: str) -> DiagnosisRun | DiagnosisReport:
        with connect(self.path) as db:
            row = db.execute(
                """SELECT run.payload, result.result_json, result.evidence_json, plan.plan_json
                FROM diagnosis_runs AS run
                LEFT JOIN diagnosis_results AS result USING (diagnosis_id)
                LEFT JOIN repair_plans AS plan USING (diagnosis_id)
                WHERE run.diagnosis_id=?""", (diagnosis_id,),
            ).fetchone()
        if row is None:
            raise ValueError("找不到指定的诊断任务")
        run = DiagnosisRun.model_validate_json(row[0])
        if row[1] is None:
            return run
        return DiagnosisReport.rehydrate(run, row[1], row[2], row[3])
