import unittest
from services.opportunity_engine import OpportunityEngine

class TestOpportunityEngine(unittest.TestCase):
    def setUp(self):
        self.engine = OpportunityEngine()

    def test_calculate_readiness_no_prereqs(self):
        """If no prerequisites, user should be ready by default (difficulty-weighted)."""
        score = self.engine._calculate_readiness([], "A1")
        self.assertEqual(score, 1.0)  # A1 = 1.0 difficulty in map

    def test_calculate_readiness_with_low_score(self):
        """If any prerequisite is < 70, readiness should be 0."""
        score = self.engine._calculate_readiness([90.0, 69.9], "A1")
        self.assertEqual(score, 0.0)

    def test_calculate_readiness_with_high_scores(self):
        """If prerequisites are >= 70, readiness should be correctly calculated."""
        # avg = 80, Difficulty A2 = 0.8
        # Formula: (0.7 * 0.8) + (0.3 * 0.8) = 0.56 + 0.24 = 0.8
        score = self.engine._calculate_readiness([80.0, 80.0], "A2")
        self.assertAlmostEqual(score, 0.8)

    def test_calculate_uncertainty(self):
        """Test uncertainty formula: 1 / (1 + count)."""
        score = self.engine._calculate_uncertainty(0)
        self.assertEqual(score, 1.0)
        
        score = self.engine._calculate_uncertainty(9)
        self.assertEqual(score, 0.1)

    def test_calculate_weakness(self):
        """Test weakness formula: (0.5 * instability) + (0.3 * recency) + (0.2 * low_confidence)."""
        # instability = 1/10 = 0.1
        # recency = 1/5 = 0.2
        # low_confidence = 2/10 = 0.2
        # Score = (0.5 * 0.1) + (0.3 * 0.2) + (0.2 * 0.2) = 0.05 + 0.06 + 0.04 = 0.15
        score = self.engine._calculate_weakness(
            total_lapses=1,
            opportunity_count=10,
            recent_failures=1,
            total_recent_reviews=5,
            hard_grades=2,
            success_grades=10
        )
        self.assertAlmostEqual(score, 0.15)

if __name__ == "__main__":
    unittest.main()
