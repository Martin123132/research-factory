from __future__ import annotations

from pathlib import Path
import re
import sqlite3
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPOSITORY_ROOT / "factory" / "hangar" / "drizzle"
BOOTSTRAP = REPOSITORY_ROOT / "factory" / "hangar" / "db" / "bootstrap.ts"
SHIFT_REPORT_TRIGGERS = (
    "shift_reports_reject_update",
    "shift_reports_reject_delete",
    "shift_reports_enforce_chain",
)


class HangarShiftReportMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = sqlite3.connect(":memory:")
        for name in ("0000_glorious_screwball.sql", "0001_remarkable_fat_cobra.sql"):
            sql = (MIGRATIONS / name).read_text(encoding="utf-8")
            self.database.executescript(sql.replace("--> statement-breakpoint", ""))

        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        for trigger_name in SHIFT_REPORT_TRIGGERS:
            match = re.search(
                rf"`(CREATE TRIGGER IF NOT EXISTS {trigger_name}\b[^`]*)`,",
                bootstrap,
                re.DOTALL,
            )
            self.assertIsNotNone(match, f"missing bootstrap trigger {trigger_name}")
            self.database.execute(match.group(1))

        self.database.execute(
            """
            INSERT INTO work_orders (
              id, workbench_id, mode, title, description, status,
              assignee_user_id, assignee_display, created_by_user_id,
              created_by_display, revision
            ) VALUES (?, 1, 'SYNTHETIC_COMMISSIONING', 'Synthetic order', '',
                      'IN_PROGRESS', 'operator-1', 'Operator 1', 'operator-1',
                      'Operator 1', 2)
            """,
            ("WO-EXAMPLE00001",),
        )
        self.database.execute(
            """
            INSERT INTO shift_reports (
              report_id, work_order_id, report_sequence, previous_report_sha256,
              report_sha256, workbench_id, mode, work_order_revision,
              work_order_status, outcome_class, report_json, actor_user_id,
              actor_display
            ) VALUES (?, ?, 1, NULL, ?, 1, 'SYNTHETIC_COMMISSIONING', 2,
                      'IN_PROGRESS', 'NO_GAIN', '{}', 'operator-1', 'Operator 1')
            """,
            ("SR-EXAMPLE00001", "WO-EXAMPLE00001", "a" * 64),
        )
        self.database.commit()

    def tearDown(self) -> None:
        self.database.close()

    def test_migration_and_bootstrap_install_both_append_only_trigger_pairs(self) -> None:
        triggers = {
            row[0]
            for row in self.database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        self.assertTrue(
            {
                "activity_events_reject_update",
                "activity_events_reject_delete",
                "shift_reports_reject_update",
                "shift_reports_reject_delete",
                "shift_reports_enforce_chain",
            }.issubset(triggers)
        )

    def test_shift_report_update_and_delete_are_rejected(self) -> None:
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.database.execute(
                "UPDATE shift_reports SET outcome_class = 'PROGRESS' WHERE report_id = ?",
                ("SR-EXAMPLE00001",),
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.database.execute(
                "DELETE FROM shift_reports WHERE report_id = ?",
                ("SR-EXAMPLE00001",),
            )

    def test_database_rejects_scientific_standing_and_completion_credit(self) -> None:
        for column in (
            "scientific_evidence",
            "counts_as_independent_reproduction",
            "eligible_for_promotion",
            "closes_work_order",
        ):
            with self.subTest(column=column):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.database.execute(
                        f"""
                        INSERT INTO shift_reports (
                          report_id, work_order_id, report_sequence,
                          previous_report_sha256, report_sha256, workbench_id,
                          mode, work_order_revision, work_order_status,
                          outcome_class, report_json, actor_user_id,
                          actor_display, {column}
                        ) VALUES (?, ?, 2, ?, ?, 1, 'SYNTHETIC_COMMISSIONING',
                                  2, 'IN_PROGRESS', 'NO_GAIN', '{{}}',
                                  'operator-1', 'Operator 1', 1)
                        """,
                        (
                            f"SR-{column[:12].upper():0<12}",
                            "WO-EXAMPLE00001",
                            "a" * 64,
                            (column[0] * 64),
                        ),
                    )

    def test_database_rejects_a_non_head_previous_hash(self) -> None:
        with self.assertRaisesRegex(sqlite3.IntegrityError, "previous hash must match"):
            self.database.execute(
                """
                INSERT INTO shift_reports (
                  report_id, work_order_id, report_sequence,
                  previous_report_sha256, report_sha256, workbench_id, mode,
                  work_order_revision, work_order_status, outcome_class,
                  report_json, actor_user_id, actor_display
                ) VALUES (?, ?, 2, ?, ?, 1, 'SYNTHETIC_COMMISSIONING', 2,
                          'IN_PROGRESS', 'NO_GAIN', '{}', 'operator-1', 'Operator 1')
                """,
                ("SR-BADCHAIN0001", "WO-EXAMPLE00001", "b" * 64, "c" * 64),
            )

    def test_database_rejects_a_non_contiguous_sequence(self) -> None:
        with self.assertRaisesRegex(sqlite3.IntegrityError, "sequence must append"):
            self.database.execute(
                """
                INSERT INTO shift_reports (
                  report_id, work_order_id, report_sequence,
                  previous_report_sha256, report_sha256, workbench_id, mode,
                  work_order_revision, work_order_status, outcome_class,
                  report_json, actor_user_id, actor_display
                ) VALUES (?, ?, 3, ?, ?, 1, 'SYNTHETIC_COMMISSIONING', 2,
                          'IN_PROGRESS', 'NO_GAIN', '{}', 'operator-1', 'Operator 1')
                """,
                ("SR-BADSEQUENCE", "WO-EXAMPLE00001", "a" * 64, "d" * 64),
            )

    def test_filing_a_report_does_not_mutate_the_parent_work_order(self) -> None:
        row = self.database.execute(
            "SELECT status, revision, completed_at FROM work_orders WHERE id = ?",
            ("WO-EXAMPLE00001",),
        ).fetchone()
        self.assertEqual(row, ("IN_PROGRESS", 2, None))

    def test_schema_version_advances_to_two(self) -> None:
        row = self.database.execute(
            "SELECT value FROM schema_metadata WHERE key = 'hangar_schema_version'"
        ).fetchone()
        self.assertEqual(row, ("2",))

    def test_shift_report_schema_migration_is_idempotent(self) -> None:
        sql = (MIGRATIONS / "0001_remarkable_fat_cobra.sql").read_text(
            encoding="utf-8"
        )
        self.database.executescript(sql.replace("--> statement-breakpoint", ""))
        row = self.database.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'shift_reports'"
        ).fetchone()
        self.assertEqual(row, (1,))


if __name__ == "__main__":
    unittest.main()
