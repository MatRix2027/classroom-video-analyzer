"""测试 ScoreCard.compute_grade 的边界条件"""

import pytest
from classroom_analyzer.models import ScoreCard, ScoreDimension


class TestScoreCardComputeGrade:
    """测试评分卡等级计算的各种边界情况。"""

    def make_card(self, total_score: float, total_max: float = 100.0, red_line: bool = False) -> ScoreCard:
        """快速构造 ScoreCard。"""
        card = ScoreCard(
            dimensions=[],
            total_score=total_score,
            total_max=total_max,
            red_line_violation=red_line,
        )
        return card

    # ── 边界测试：49分 → 不达标，50分 → 博学 ──

    def test_49_points_below_pass(self):
        """49分应判定为不达标（< 50）。"""
        card = self.make_card(total_score=49.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "不达标"

    def test_50_points_just_pass(self):
        """50分应判定为博学（>= 50）。"""
        card = self.make_card(total_score=50.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "博学"

    def test_69_points_top_of_boshi(self):
        """69分应判定为博学（< 70）。"""
        card = self.make_card(total_score=69.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "博学"

    def test_70_points_just_challenge(self):
        """70分应判定为挑战（>= 70）。"""
        card = self.make_card(total_score=70.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "挑战"

    def test_89_points_top_of_challenge(self):
        """89分应判定为挑战（< 90）。"""
        card = self.make_card(total_score=89.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "挑战"

    def test_90_points_just_innovate(self):
        """90分应判定为创新（>= 90）。"""
        card = self.make_card(total_score=90.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "创新"

    def test_100_points_perfect(self):
        """100分应判定为创新。"""
        card = self.make_card(total_score=100.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "创新"

    # ── 红线违规 → 不达标（红线违规） ──

    def test_red_line_violation(self):
        """红线违规时，无论分数多少都应为不达标（红线违规）。"""
        card = self.make_card(total_score=95.0, red_line=True)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "不达标（红线违规）"

    def test_red_line_with_low_score(self):
        """红线违规且低分，仍应为不达标（红线违规）。"""
        card = self.make_card(total_score=30.0, red_line=True)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "不达标（红线违规）"

    # ── 不同班型 ──

    @pytest.mark.parametrize("level", ["L1_L3", "L4_L6", "L7_L9"])
    def test_all_levels_same_boundaries(self, level):
        """所有班型使用相同的分数边界（统一百分制）。"""
        card = self.make_card(total_score=75.0)
        grade = card.compute_grade(level=level)
        assert grade == "挑战"

    # ── 归一化测试 ──

    def test_normalized_score(self):
        """当 total_max 不是 100 时，应正确归一化。"""
        # total_max=200, total_score=100 → 50% → 博学
        card = self.make_card(total_score=100.0, total_max=200.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "博学"

    def test_normalized_score_high(self):
        """归一化后90%以上应为创新。"""
        # total_max=200, total_score=180 → 90% → 创新
        card = self.make_card(total_score=180.0, total_max=200.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "创新"

    # ── total_max 为 0 的保护 ──

    def test_zero_max_score(self):
        """total_max 为 0 时应返回博学（保护逻辑）。"""
        card = self.make_card(total_score=0.0, total_max=0.0)
        grade = card.compute_grade(level="L4_L6")
        assert grade == "博学"
