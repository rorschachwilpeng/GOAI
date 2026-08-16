from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_markers import DemoMarkers, MARKERS, MarkerError, validate_manifest


class DemoMarkersTest(unittest.TestCase):
    def make_markers(self) -> DemoMarkers:
        return DemoMarkers(
            run_id="RUN-SYNTHETIC-001",
            case_id="CASE-SYNTHETIC-001",
            project_room_id="!synthetic-room:example.test",
            conversation_id="CONV-SYNTHETIC-001",
        )

    def fill_markers(self, markers: DemoMarkers) -> None:
        for index, marker in enumerate(MARKERS):
            markers.record(
                marker,
                matrix_event_id=f"$synthetic-matrix-{index}",
                business_event_id=f"BUS-SYNTHETIC-{index}",
                occurred_at=f"2026-08-15T10:0{index}:00+08:00",
            )

    def test_complete_manifest_has_required_identity_counts_and_markers(self):
        markers = self.make_markers()
        self.fill_markers(markers)

        manifest = markers.manifest(
            incident_count=2,
            execution_count=2,
            verification_count=2,
            final_case_state="RESOLVED",
        )

        self.assertTrue(validate_manifest(manifest))
        self.assertEqual(manifest["case_id"], "CASE-SYNTHETIC-001")
        self.assertEqual(manifest["incident_count"], 2)
        self.assertEqual(
            [item["marker"] for item in manifest["markers"]],
            list(MARKERS),
        )
        self.assertNotIn("token", str(manifest).lower())

    def test_record_rejects_out_of_order_marker_immediately(self):
        markers = self.make_markers()

        with self.assertRaisesRegex(MarkerError, "out of order"):
            markers.record("SCENE_1_END", "$matrix-1", "BUS-1")

    def test_record_rejects_duplicate_marker_immediately(self):
        markers = self.make_markers()
        markers.record("DEMO_START", "$matrix-0", "BUS-0")

        with self.assertRaisesRegex(MarkerError, "out of order"):
            markers.record("DEMO_START", "$matrix-1", "BUS-1")

    def test_manifest_rejects_missing_marker(self):
        markers = self.make_markers()
        markers.record("DEMO_START", "$matrix-0", "BUS-0")

        with self.assertRaisesRegex(MarkerError, "marker set is incomplete"):
            markers.manifest(2, 2, 2, "RESOLVED")

    def test_validate_manifest_rejects_missing_required_field(self):
        markers = self.make_markers()
        self.fill_markers(markers)
        manifest = markers.manifest(2, 2, 2, "RESOLVED")
        invalid = deepcopy(manifest)
        del invalid["project_room_id"]

        with self.assertRaisesRegex(MarkerError, "fields are incomplete"):
            validate_manifest(invalid)

    def test_validate_manifest_rejects_duplicate_event_reference(self):
        markers = self.make_markers()
        self.fill_markers(markers)
        manifest = markers.manifest(2, 2, 2, "RESOLVED")
        invalid = deepcopy(manifest)
        invalid["markers"][1]["matrix_event_id"] = invalid["markers"][0][
            "matrix_event_id"
        ]

        with self.assertRaisesRegex(MarkerError, "references must be unique"):
            validate_manifest(invalid)


if __name__ == "__main__":
    unittest.main()
