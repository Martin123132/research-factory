from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from control_plane.common import ControlPlaneError
from engine.fixture_packets import FixturePacketController


FACTORY_ROOT = Path(__file__).resolve().parents[2]


class FixturePacketControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.controller = FixturePacketController(FACTORY_ROOT)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_list_exposes_only_allowlisted_non_live_adapters(self) -> None:
        packets = self.controller.list()

        self.assertEqual(["WB-001", "WB-013"], [row["workbench_code"] for row in packets])
        self.assertTrue(all(row["scientific_standing"] == "NONE" for row in packets))
        self.assertTrue(all(row["live_research_authorized"] is False for row in packets))

    def test_unknown_workbench_is_not_a_general_runner(self) -> None:
        with self.assertRaisesRegex(ControlPlaneError, "no allowlisted fixture packet adapter"):
            self.controller.execute(
                "build",
                workbench="WB-002",
                output=self.root / "unexpected-packet",
            )

    def test_rehearsal_requires_a_demo_identity(self) -> None:
        with self.assertRaisesRegex(ControlPlaneError, "demo: operator identity"):
            self.controller.execute(
                "rehearse",
                workbench="WB-001",
                package=self.root / "not-used",
                output=self.root / "not-used-receipt.json",
                operator_id="human:alice",
            )

    def test_build_verify_and_rehearse_each_known_safe_fixture(self) -> None:
        for workbench in ("WB-001", "WB-013"):
            with self.subTest(workbench=workbench):
                package = self.root / f"{workbench.lower()}-packet"
                receipt = self.root / f"{workbench.lower()}-rehearsal.json"

                built = self.controller.execute("build", workbench=workbench, output=package)
                self.assertEqual("BUILD", built["action"])
                self.assertFalse(built["construction_boundary"]["scientific_evidence"])

                verified = self.controller.execute("verify", workbench=workbench, package=package)
                self.assertTrue(verified["result"]["valid"])
                self.assertFalse(verified["construction_boundary"]["eligible_for_promotion"])

                rehearsed = self.controller.execute(
                    "rehearse",
                    workbench=workbench,
                    package=package,
                    output=receipt,
                    operator_id=f"demo:{workbench.lower()}-test",
                )
                self.assertTrue(receipt.is_file())
                self.assertFalse(rehearsed["construction_boundary"]["counts_as_independent_reproduction"])


if __name__ == "__main__":
    unittest.main()
