"""Contract checks for role-scoped MCP configuration files."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
AGENTTEAMS_DIR = PROJECT_ROOT / "workspace" / "agentteams"

EXPECTED_TOOLS = {
    "frontline": {"resolve_order_reference", "record_customer_confirmation"},
    "resolution": {
        "get_authorized_order",
        "evaluate_rebooking",
        "record_internal_decision",
        "validate_execution_authorization",
        "execute_rebooking",
    },
    "verification": {"get_order_state", "verify_rebooking"},
}

EXPECTED_WORKERS = {
    "frontline": ("identify-hotel-order", "mcp-goai-frontline"),
    "resolution": ("investigate-hotel-supply-exception", "mcp-goai-resolution"),
    "verification": ("verify-hotel-rebooking", "mcp-goai-verification"),
}


def tool_names(path: Path) -> set[str]:
    return set(re.findall(r"^- name: ([a-z_]+)$", path.read_text(encoding="utf-8"), re.M))


class AgentTeamsContractsTest(unittest.TestCase):
    def test_each_role_surface_exposes_exact_tool_set(self) -> None:
        for role, expected in EXPECTED_TOOLS.items():
            path = AGENTTEAMS_DIR / f"mcp-goai-{role}.yaml"
            self.assertEqual(tool_names(path), expected)

    def test_manager_configuration_has_no_business_mcp(self) -> None:
        role_surfaces = {
            path.stem.removeprefix("mcp-goai-")
            for path in AGENTTEAMS_DIR.glob("mcp-goai-*.yaml")
            if path.stem != "mcp-goai-order"
        }
        self.assertEqual(role_surfaces, set(EXPECTED_TOOLS))
        self.assertEqual(list(AGENTTEAMS_DIR.glob("*manager*.yaml")), [])

    def test_each_worker_has_one_role_scoped_mcp_and_skill(self) -> None:
        for worker, (skill, mcp_server) in EXPECTED_WORKERS.items():
            content = (AGENTTEAMS_DIR / f"{worker}-worker.yaml").read_text(encoding="utf-8")
            self.assertIn(f"name: {worker}", content)
            self.assertIn(f"- {skill}", content)
            self.assertEqual(re.findall(r"^    - name: (mcp-goai-[a-z]+)$", content, re.M), [mcp_server])

    def test_skills_handoff_in_the_case_project_room(self) -> None:
        skill_dir = PROJECT_ROOT / "workspace" / "skills"
        frontline = (skill_dir / "identify-hotel-order" / "SKILL.md").read_text(encoding="utf-8")
        resolution = (skill_dir / "investigate-hotel-supply-exception" / "SKILL.md").read_text(encoding="utf-8")
        verification = (skill_dir / "verify-hotel-rebooking" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("mcp-goai-frontline.resolve_order_reference", frontline)
        self.assertIn("Case Project Room", frontline)
        self.assertIn("You may call mcp-goai-frontline.record_customer_confirmation", frontline)
        self.assertNotIn("execute_rebooking", frontline)
        self.assertIn("mcp-goai-resolution.get_authorized_order", resolution)
        self.assertIn("Case Project Room", resolution)
        self.assertIn("mcp-goai-verification.get_order_state", verification)
        self.assertIn("Verification Package", verification)
        self.assertIn("must not join the Case Project Room", verification)
        self.assertIn("verify_package_hash", verification)
        self.assertIn("must stop without calling an order Tool", verification)
        self.assertNotIn("Execution Record", verification)
