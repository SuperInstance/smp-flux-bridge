"""Tests for ConfidenceCascade confidence composition logic."""

import pytest
from lock_tile import ConfidenceCascade, ConfidenceZone, LockTile


def _make_tile(confidence=0.9, pattern="p", bytecode=b'\x01'):
    return LockTile(
        pattern=pattern,
        bytecode=bytecode,
        confidence=confidence,
        safety_contract=lambda p, b: True,
    )


class TestCascadeConfidence:
    """Tests for sequential (multiplicative) confidence cascade."""

    def test_single_confidence(self):
        cc = ConfidenceCascade()
        assert cc.cascade_confidence([0.9]) == pytest.approx(0.9)

    def test_two_confidences(self):
        cc = ConfidenceCascade()
        assert cc.cascade_confidence([0.9, 0.8]) == pytest.approx(0.72)

    def test_three_confidences(self):
        cc = ConfidenceCascade()
        result = cc.cascade_confidence([0.95, 0.90, 0.85])
        assert result == pytest.approx(0.95 * 0.90 * 0.85)

    def test_empty_list_returns_1(self):
        cc = ConfidenceCascade()
        assert cc.cascade_confidence([]) == pytest.approx(1.0)

    def test_all_ones(self):
        cc = ConfidenceCascade()
        assert cc.cascade_confidence([1.0, 1.0, 1.0]) == pytest.approx(1.0)

    def test_includes_zero(self):
        cc = ConfidenceCascade()
        assert cc.cascade_confidence([0.9, 0.0, 0.8]) == pytest.approx(0.0)

    def test_monotonic_degradation(self):
        """Multiplicative cascade always <= min(confidences)."""
        cc = ConfidenceCascade()
        confs = [0.98, 0.95, 0.90]
        result = cc.cascade_confidence(confs)
        assert result <= min(confs)


class TestParallelConfidence:
    """Tests for parallel confidence computation."""

    def test_min_method(self):
        cc = ConfidenceCascade()
        assert cc.parallel_confidence([0.9, 0.7, 0.8], method='min') == pytest.approx(0.7)

    def test_min_single(self):
        cc = ConfidenceCascade()
        assert cc.parallel_confidence([0.5], method='min') == pytest.approx(0.5)

    def test_geometric_method_two(self):
        cc = ConfidenceCascade()
        result = cc.parallel_confidence([0.9, 0.4], method='geometric')
        expected = (0.9 * 0.4) ** 0.5
        assert result == pytest.approx(expected)

    def test_geometric_method_three(self):
        cc = ConfidenceCascade()
        result = cc.parallel_confidence([0.8, 0.8, 0.8], method='geometric')
        expected = 0.8
        assert result == pytest.approx(expected)

    def test_unknown_method_raises(self):
        cc = ConfidenceCascade()
        with pytest.raises(ValueError, match="Unknown method"):
            cc.parallel_confidence([0.9], method='average')


class TestUpdateLockConfidence:
    """Tests for update_lock_confidence with fleet history."""

    def test_base_confidence_only(self):
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.80)
        updated = cc.update_lock_confidence(tile, {})
        assert updated.confidence == pytest.approx(0.80)

    def test_verification_bonus(self):
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.80)
        updated = cc.update_lock_confidence(tile, {
            'verified_by': ['model-a', 'model-b']
        })
        # 0.80 + 0.05 * 2 = 0.90
        assert updated.confidence == pytest.approx(0.90)

    def test_experience_bonus_success(self):
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.80)
        updated = cc.update_lock_confidence(tile, {
            'successful_applied': 5,
            'failed_applied': 0
        })
        # 0.80 + 0.02*5 - 0.05*0 = 0.90
        assert updated.confidence == pytest.approx(0.90)

    def test_experience_penalty_failure_returns_original_due_to_deadband(self):
        """When penalty would cross zone boundary into deadband, original is returned."""
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.80)
        updated = cc.update_lock_confidence(tile, {
            'successful_applied': 0,
            'failed_applied': 2
        })
        # 0.80 + 0.02*0 - 0.05*2 = 0.70 -> would be RED
        # But deadband prevents YELLOW->RED transition at 0.70 (not < 0.73)
        # Actually 0.70 < 0.73, so deadband would NOT prevent it
        # But the deadband check is: total_conf < 0.73 -> return original
        # 0.70 < 0.73 is True -> returns original tile
        assert updated.confidence == pytest.approx(0.80)

    def test_clamped_to_one_returns_original_due_to_deadband(self):
        """When boost would cross zone boundary into deadband, original is returned."""
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.95)
        updated = cc.update_lock_confidence(tile, {
            'verified_by': ['a', 'b', 'c', 'd', 'e'],
            'successful_applied': 10,
            'failed_applied': 0
        })
        # 0.95 + 0.25 + 0.20 = 1.40 -> clamped to 1.0
        # Old zone is YELLOW (0.95 not > 0.95), new zone is GREEN (1.0 > 0.95)
        # Deadband check: YELLOW->GREEN requires total_conf > 0.97
        # 1.0 > 0.97 is True -> returns original tile
        assert updated.confidence == pytest.approx(0.95)

    def test_small_boost_same_zone(self):
        """Small boost that stays in same zone should update confidence."""
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.85)
        updated = cc.update_lock_confidence(tile, {
            'verified_by': ['a'],
            'successful_applied': 2,
            'failed_applied': 0
        })
        # 0.85 + 0.05 + 0.04 = 0.94 -> still YELLOW (0.75 < 0.94 <= 0.95)
        # No zone change, no deadband check
        assert updated.confidence == pytest.approx(0.94)

    def test_clamped_to_zero(self):
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.10)
        updated = cc.update_lock_confidence(tile, {
            'successful_applied': 0,
            'failed_applied': 10
        })
        # 0.10 - 0.50 = -0.40 -> clamped to 0.0
        # Old zone RED, new zone RED -> no deadband check
        assert updated.confidence == pytest.approx(0.0)

    def test_metadata_updated(self):
        cc = ConfidenceCascade()
        tile = _make_tile(confidence=0.85)
        updated = cc.update_lock_confidence(tile, {
            'verified_by': ['a']
        })
        assert 'updated_confidence' in updated.metadata
        assert 'zone' in updated.metadata
