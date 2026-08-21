import unittest
from unittest.mock import patch

from app.assistant.plan_recommendation import recommend_plan_conversational


SAMPLE_PLANS = [
    {"plan_id": "PLN-CHN-100", "name": "Singara Chennai 100M", "speed_mbps": 100, "price_inr": 499, "type": "Fiber", "description": "Budget plan"},
    {"plan_id": "PLN-CHN-300", "name": "Marina Fiber Speed 300M", "speed_mbps": 300, "price_inr": 799, "type": "Fiber", "description": "High speed WFH plan"},
    {"plan_id": "PLN-CHN-1G", "name": "Chennai Giga Super 1G", "speed_mbps": 1000, "price_inr": 1499, "type": "Fiber", "description": "Ultimate gaming plan"},
]


class PlanRecommendationTests(unittest.TestCase):
    @patch("app.assistant.plan_recommendation.generate", return_value="The Marina Fiber Speed 300M plan is ideal for working from home.")
    def test_llm_conversational_recommendation(self, mock_generate):
        result = recommend_plan_conversational(SAMPLE_PLANS, "I work from home, which is best?")
        self.assertIn("Marina Fiber", result)

    @patch("app.assistant.plan_recommendation.generate", side_effect=Exception("LLM Timeout"))
    def test_fallback_recommendation_gaming(self, mock_generate):
        result = recommend_plan_conversational(SAMPLE_PLANS, "Best plan for low ping gaming?")
        self.assertIn("LLM API Key Required", result)

    @patch("app.assistant.plan_recommendation.generate", side_effect=Exception("LLM Timeout"))
    def test_fallback_recommendation_budget(self, mock_generate):
        result = recommend_plan_conversational(SAMPLE_PLANS, "What is the cheap budget option?")
        self.assertIn("LLM API Key Required", result)


if __name__ == "__main__":
    unittest.main()

