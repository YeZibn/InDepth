import json
import unittest
from unittest.mock import patch

from app.tool.sub_agent_tool.sub_agent_tool import create_sub_agent


class SubAgentToolTests(unittest.TestCase):
    def test_reviewer_requires_acceptance_criteria(self):
        result = create_sub_agent.entrypoint(
            name="r1",
            description="review",
            task="review this change",
            role="reviewer",
            output_format="json checklist",
        )
        payload = json.loads(result)
        self.assertFalse(payload["success"])
        self.assertIn("acceptance_criteria", payload["error"])

    def test_verifier_requires_output_format(self):
        result = create_sub_agent.entrypoint(
            name="v1",
            description="verify",
            task="verify artifacts",
            role="verifier",
            acceptance_criteria="artifacts exist and non-empty",
        )
        payload = json.loads(result)
        self.assertFalse(payload["success"])
        self.assertIn("output_format", payload["error"])

    def test_reviewer_passes_gate_and_appends_constraints_into_task(self):
        with patch(
            "app.tool.sub_agent_tool.sub_agent_tool._manager.create",
            return_value=("abc12345", "reviewer"),
        ) as mock_create:
            result = create_sub_agent.entrypoint(
                name="r2",
                description="review",
                task="check release readiness",
                role="reviewer",
                acceptance_criteria="must include rollback plan",
                output_format="markdown checklist",
            )

        payload = json.loads(result)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["agent_id"], "abc12345")
        called_task = mock_create.call_args.args[2]
        self.assertIn("[验收口径]", called_task)
        self.assertIn("must include rollback plan", called_task)
        self.assertIn("[输出格式]", called_task)
        self.assertIn("markdown checklist", called_task)


if __name__ == "__main__":
    unittest.main()
