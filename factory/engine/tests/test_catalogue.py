from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from control_plane.common import ContractError
from engine.catalogue import StationCatalogue, doctor


FACTORY_ROOT = Path(__file__).resolve().parents[2]


class StationCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = StationCatalogue(FACTORY_ROOT)

    def test_full_registry_and_kits_verify(self) -> None:
        result = self.catalogue.verify(full=True)
        self.assertTrue(result["valid"])
        self.assertEqual(100, result["stations"])
        self.assertEqual(3, result["runnable_entry_gates"])
        self.assertEqual(0, result["live_ready"])
        self.assertEqual(1, result["readiness_stages"]["COMMISSIONING_READY"])
        self.assertEqual(99, result["readiness_stages"]["CONTRACT_DRAFT"])

    def test_resolves_number_code_compact_code_and_slug(self) -> None:
        expected = "WB-013"
        for identifier in (
            "13",
            "WB-013",
            "wb013",
            "travelling-salesperson-route-kernel",
        ):
            with self.subTest(identifier=identifier):
                self.assertEqual(expected, self.catalogue.resolve(identifier)["workbench_code"])

    def test_entry_ready_filter_is_truthful(self) -> None:
        rows = self.catalogue.list(entry_ready=True)
        self.assertEqual(["WB-001", "WB-002", "WB-013"], [row["workbench_code"] for row in rows])
        self.assertTrue(all(row["starter_pack_status"] == "KNOWN_ANSWER_READY" for row in rows))

    def test_inspection_preserves_the_live_boundary(self) -> None:
        value = self.catalogue.inspect("WB-001")
        self.assertEqual("SYNTHETIC_COMMISSIONING", value["safe_scope"])
        self.assertFalse(value["live_research_allowed"])
        self.assertEqual(
            value["registry"]["contract_sha256"],
            self.catalogue.resolve("WB-001")["contract_sha256"],
        )

    def test_unknown_station_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractError, "unknown workbench"):
            self.catalogue.inspect("WB-999")

    def test_doctor_has_no_hosted_provider_dependency(self) -> None:
        value = doctor(FACTORY_ROOT)
        self.assertTrue(value["engine_ready"])
        self.assertEqual("NOT_INITIALIZED", value["ledger"]["status"])
        self.assertTrue(all(flag is False for flag in value["provider_dependencies"].values()))
        self.assertFalse(value["live_research_ready"])

    def test_doctor_rejects_an_explicit_missing_ledger(self) -> None:
        with TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ContractError, "ledger does not exist"):
                doctor(FACTORY_ROOT, ledger=Path(temporary) / "not-there.jsonl")


if __name__ == "__main__":
    unittest.main()
