import json
import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase

from agent_optimization import QueryDenied
from app.cybereye.backend.optimization.dataset import GuideDataset
from app.cybereye.backend.optimization.evaluation import GradeEvaluator, score


class OptimizationEvaluationTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "manifest.json").write_text(json.dumps({"dataset_id": "fixture"}))
        with sqlite3.connect(self.root / "source.sqlite") as db:
            db.execute("CREATE TABLE evidence(row_id INTEGER,case_id TEXT,event_time TEXT,detector_id TEXT,category TEXT,mitre_techniques TEXT,entity_type TEXT,evidence_role TEXT)")
            db.executemany("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)", [(1,"a"*16,"2024-01-01","7","InitialAccess","T1078","User","Related"),(2,"b"*16,"2024-02-01","9","Other","","Ip","Impacted")])
            db.execute("CREATE TABLE training_profile(feature TEXT,value TEXT,true_positive INTEGER,benign_positive INTEGER,false_positive INTEGER,support INTEGER)")
            db.execute("INSERT INTO training_profile VALUES('detector_id','7',10,1,0,11)")
        self.dataset = GuideDataset(self.root, self.root / "contexts")

    def test_candidate_sees_one_incident_and_cannot_read_labels_or_other_cases(self):
        result = self.dataset.query("a"*16,"SELECT detector_id FROM evidence")
        self.assertEqual(result["rows"], [["7"]])
        for sql in ("SELECT * FROM labels", "ATTACH DATABASE 'elsewhere' AS other", "DELETE FROM evidence", "SELECT * FROM cases", "SELECT * FROM sqlite_master"):
            with self.subTest(sql=sql), self.assertRaises(Exception):
                self.dataset.query("a"*16, sql)

    def test_score_counts_failures_and_all_grade_classes(self):
        cases = [{"expected":"TruePositive","predicted":"TruePositive","correct":True,"elapsed_ms":10},
                 {"expected":"FalsePositive","predicted":None,"correct":False,"elapsed_ms":20,"error":"timeout"},
                 {"expected":"BenignPositive","predicted":"BenignPositive","correct":True,"elapsed_ms":30}]
        metrics = score(cases, 60)
        self.assertAlmostEqual(metrics["macro_f1"], 2/3)
        self.assertAlmostEqual(metrics["error_rate"], 1/3)
        self.assertEqual(metrics["median_ms"], 20)

    def test_predictor_never_receives_the_expected_label(self):
        seen = []
        def predict(prompt, evidence, model):
            seen.append(evidence)
            return {"grade":"TruePositive","rationale":"fixture"}
        cases, metrics = GradeEvaluator(self.dataset,predict).run(
            {"system_prompt":"test","model":"test"}, [{"name":"query","sql":"SELECT * FROM evidence"}],
            [{"case_id":"a"*16,"expected":"TruePositive","split":"validation","start_time":"2024","end_time":"2024"}], lambda:False, lambda case:None)
        self.assertNotIn("expected", json.dumps(seen))
        self.assertNotIn("TruePositive", json.dumps(seen))
        self.assertEqual(metrics["accuracy"], 1)