from __future__ import annotations

import os
import shutil
import unittest
import uuid
from pathlib import Path

from control_plane.common import ContractError
from dispatch.container_adapter import inspect_host
from dispatch.container_commissioning import (
    DEFAULT_IMAGE_REF,
    prepare_container_commissioning_drill,
    run_prepared_container_commissioning_drill,
    verify_container_commissioning_drill,
    verify_prepared_container_commissioning_drill,
)


FACTORY_ROOT = Path(__file__).resolve().parents[2]


class ContainerCommissioningTests(unittest.TestCase):
    def output(self) -> Path:
        return FACTORY_ROOT / "state" / f"container-commissioning-test-{uuid.uuid4().hex}"

    def test_prepare_writes_an_inspectable_non_secret_package(self) -> None:
        output = self.output()
        release = "container-commissioning-test-release"
        try:
            result = prepare_container_commissioning_drill(
                output,
                factory_root=FACTORY_ROOT,
                image_ref="example.invalid/factory/fixture@sha256:" + "a" * 64,
                operator_id="human:container-commissioning-test",
                release_capability=release,
            )
            self.assertTrue(result["valid"])
            self.assertEqual("PREPARED_AWAITING_HUMAN_RELEASE", result["state"])
            self.assertFalse(result["counts_as_independent_reproduction"])
            self.assertFalse(result["eligible_for_promotion"])
            self.assertEqual(
                {"budget.json", "ticket.json", "request.json"},
                {path.name for path in (output / "public").iterdir()},
            )
            self.assertNotIn(release, "".join(path.read_text(encoding="utf-8") for path in (output / "public").iterdir()))
            self.assertTrue(verify_prepared_container_commissioning_drill(output, factory_root=FACTORY_ROOT)["valid"])
        finally:
            shutil.rmtree(output, ignore_errors=True)

    def test_prepare_rejects_non_state_output_and_tampered_request(self) -> None:
        with self.assertRaisesRegex(ContractError, "factory/state"):
            prepare_container_commissioning_drill(
                FACTORY_ROOT / "dispatch" / "not-state",
                factory_root=FACTORY_ROOT,
                release_capability="release",
            )
        output = self.output()
        try:
            prepare_container_commissioning_drill(
                output,
                factory_root=FACTORY_ROOT,
                release_capability="release",
            )
            request = output / "public" / "request.json"
            request.write_text(request.read_text(encoding="utf-8").replace("runner-output", "changed-output"), encoding="utf-8")
            with self.assertRaises(ContractError):
                verify_prepared_container_commissioning_drill(output, factory_root=FACTORY_ROOT)
        finally:
            shutil.rmtree(output, ignore_errors=True)

    @unittest.skipUnless(
        os.environ.get("FACTORY_CONTAINER_E2E") == "1",
        "set FACTORY_CONTAINER_E2E=1 to run the local Docker commissioning drill",
    )
    def test_prepared_package_runs_and_verifies_on_a_local_docker_host(self) -> None:
        if not inspect_host()["ready"]:
            self.skipTest("Docker daemon is not available")
        output = self.output()
        try:
            prepare_container_commissioning_drill(
                output,
                factory_root=FACTORY_ROOT,
                image_ref=DEFAULT_IMAGE_REF,
                release_capability="container-commissioning-e2e-release",
            )
            result = run_prepared_container_commissioning_drill(
                output,
                factory_root=FACTORY_ROOT,
                release_capability="container-commissioning-e2e-release",
            )
            self.assertTrue(result["valid"])
            self.assertEqual("COMMISSIONED", result["state"])
            artifact = output / "public" / "runner-output" / "stdout-artifact.bin"
            artifact.write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(ContractError):
                verify_container_commissioning_drill(output, factory_root=FACTORY_ROOT)
        finally:
            shutil.rmtree(output, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
