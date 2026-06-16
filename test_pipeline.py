import asyncio
import json
import unittest

# Global state to control what the mock LLM returns
CURRENT_SCENARIO = "normal"

class MockResponse:
    def __init__(self, content: str):
        self.content = content

class MockCheapLLM:
    def invoke(self, messages):
        system_msg = ""
        user_msg = ""
        for role, content in messages:
            if role == "system":
                system_msg = content
            elif role == "human":
                user_msg = content

        if "intake agent" in system_msg:
            return MockResponse(json.dumps({
                "problem": "HR automated pipeline",
                "solution": "Multi-agent screening",
                "track": "Enterprise",
                "team_size": 3,
                "key_features": ["resume screening", "ranking"]
            }))

        elif "code analysis agent" in system_msg:
            if CURRENT_SCENARIO == "normal":
                return MockResponse(json.dumps({
                    "framework": "Band",
                    "agent_count": 3,
                    "band_usage": True,
                    "tech_stack": ["python", "langchain"],
                    "has_tests": True,
                    "architecture_summary": "Intake agent parses, match agent matches, rank agent ranks.",
                    "fraud_flags": []
                }))
            else:
                return MockResponse(json.dumps({
                    "framework": "Band",
                    "agent_count": 3,
                    "band_usage": True,
                    "tech_stack": ["python", "langchain"],
                    "has_tests": False,
                    "architecture_summary": "Intake agent parses, match agent matches, rank agent ranks.",
                    "fraud_flags": []
                }))

        elif "early signs of fraud" in system_msg or (messages and "Check this hackathon submission for early signs of fraud" in messages[0][1]):
            # FraudDetector does not have system prompt, it uses single human message
            if CURRENT_SCENARIO == "fraud":
                return MockResponse(json.dumps({
                    "fraud_score": 80,
                    "flags": ["suspected_copypasta"],
                    "abort_evaluation": True
                }))
            else:
                return MockResponse(json.dumps({
                    "fraud_score": 10,
                    "flags": [],
                    "abort_evaluation": False
                }))

        elif "business value judge" in system_msg:
            if "participating in a hackathon panel debate" in system_msg:
                return MockResponse(json.dumps({
                    "adjusted_score": 90,
                    "justification": "Held ground because of market size."
                }))
            else:
                score = 85 if CURRENT_SCENARIO == "normal" else 90
                return MockResponse(json.dumps({
                    "business_score": score,
                    "reasoning": "High market demand for HR automation.",
                    "confidence": "high",
                    "strengths": ["Clear ROI"],
                    "weaknesses": []
                }))

        elif "innovation judge" in system_msg:
            if "participating in a hackathon panel debate" in system_msg:
                return MockResponse(json.dumps({
                    "adjusted_score": 70,
                    "justification": "Increased score slightly based on feedback."
                }))
            else:
                score = 80 if CURRENT_SCENARIO == "normal" else 60
                return MockResponse(json.dumps({
                    "innovation_score": score,
                    "reasoning": "Good use of multi-agent flow.",
                    "confidence": "high",
                    "strengths": ["Multi-agent design"],
                    "weaknesses": []
                }))

        elif "Band framework" in system_msg:
            if "participating in a hackathon panel debate" in system_msg:
                return MockResponse(json.dumps({
                    "adjusted_score": 85,
                    "justification": "Score is stable."
                }))
            else:
                return MockResponse(json.dumps({
                    "band_score": 85 if CURRENT_SCENARIO == "debate" else 88,
                    "reasoning": "Proper framework usage.",
                    "confidence": "high",
                    "strengths": ["Proper framework usage"],
                    "weaknesses": []
                }))

        elif "demo" in system_msg:
            if "participating in a hackathon panel debate" in system_msg:
                return MockResponse(json.dumps({
                    "adjusted_score": 80,
                    "justification": "Score is stable."
                }))
            else:
                score = 82 if CURRENT_SCENARIO == "normal" else 80
                return MockResponse(json.dumps({
                    "demo_score": score,
                    "reasoning": "Walkthrough covers all parts.",
                    "confidence": "high",
                    "strengths": ["Working demo shown"],
                    "weaknesses": []
                }))

        raise ValueError(f"Unknown system message in MockCheapLLM: {system_msg[:200]}")

class MockSmartLLM:
    def invoke(self, messages):
        human_content = messages[0][1]
        if "arbitrating divergent scores" in human_content:
            return MockResponse(json.dumps({
                "arbitration": "The Head Judge resolves the innovation score to 72 based on debate inputs.",
                "adjusted_scores": {
                    "business": 90,
                    "innovation": 72,
                    "band": 85,
                    "demo": 80
                }
            }))
        raise ValueError(f"Unknown prompt in MockSmartLLM: {human_content[:200]}")

# Patch core.llm functions BEFORE importing main or stage modules
import core.llm
core.llm.get_cheap_llm = lambda: MockCheapLLM()
core.llm.get_smart_llm = lambda: MockSmartLLM()

# Now import evaluate safely
from main import evaluate

class TestHackathonJudgePanel(unittest.TestCase):
    def setUp(self):
        # Clear global state to ensure clean test runs in the same process
        from core.band_helper import PROCESSED_MESSAGE_IDS
        PROCESSED_MESSAGE_IDS.clear()

        from stage1.kg_builder_agent import KG_BUILT_FOR_MESSAGES
        KG_BUILT_FOR_MESSAGES.clear()

    def test_normal_scenario(self):
        global CURRENT_SCENARIO
        CURRENT_SCENARIO = "normal"

        submission = {
            "github_url": "https://github.com/example/project",
            "description": "HR automation tool using Band framework.",
            "video_transcript": "Demo showing resume parsing and candidate ranking.",
            "readme": "HR Agent Suite setup instructions."
        }

        # Run pipeline
        result = asyncio.run(evaluate(submission))

        # Assertions
        self.assertIn("final_score", result)
        self.assertIn("recommendation", result)
        self.assertEqual(result["debate_triggered"], False)
        # Expected score: Business=85, Innovation=80, Band=88, Demo=82, Code=100
        # Weighted = 85*0.25 + 80*0.20 + 88*0.20 + 82*0.15 + 100*0.20 = 87.15 => 87.2
        self.assertEqual(result["final_score"], 87.2)
        self.assertEqual(result["recommendation"], "Top 10 candidate")
        self.assertEqual(result["fraud_flags"], [])

    def test_debate_scenario(self):
        global CURRENT_SCENARIO
        CURRENT_SCENARIO = "debate"

        submission = {
            "github_url": "https://github.com/example/project",
            "description": "HR automation tool using Band framework.",
            "video_transcript": "Demo showing resume parsing and candidate ranking.",
            "readme": "HR Agent Suite setup instructions."
        }

        # Run pipeline
        result = asyncio.run(evaluate(submission))

        # Assertions
        self.assertIn("final_score", result)
        self.assertIn("recommendation", result)
        self.assertEqual(result["debate_triggered"], True)
        # Innovation starts at 60, Business at 90. Gap is 30 (triggers debate).
        # Arbitration adjusts Innovation to 72. Other scores: Business=90, Band=85, Demo=80, Code=90 (no tests)
        # Weighted = 90*0.25 + 72*0.20 + 85*0.20 + 80*0.15 + 90*0.20 = 22.5 + 14.4 + 17.0 + 12.0 + 18.0 = 83.9
        self.assertEqual(result["final_score"], 83.9)
        self.assertEqual(result["recommendation"], "Strong submission")
        self.assertIn("resolves the innovation score to 72", result["debate_summary"])

    def test_fraud_scenario(self):
        global CURRENT_SCENARIO
        CURRENT_SCENARIO = "fraud"

        submission = {
            "github_url": "https://github.com/example/project",
            "description": "HR automation tool using Band framework.",
            "video_transcript": "Demo showing resume parsing and candidate ranking.",
            "readme": "HR Agent Suite setup instructions."
        }

        # Run pipeline
        result = asyncio.run(evaluate(submission))

        # Assertions
        self.assertEqual(result["final_score"], 0)
        self.assertEqual(result["recommendation"], "DISQUALIFIED")
        self.assertEqual(result["debate_triggered"], False)
        self.assertIn("suspected_copypasta", result["fraud_flags"])

if __name__ == "__main__":
    unittest.main()
