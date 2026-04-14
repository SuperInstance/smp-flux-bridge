"""Comprehensive tests for LockTile core functionality."""

import pytest
from lock_tile import LockTile, ConfidenceZone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _always_true(pattern: str, bytecode: bytes) -> bool:
    return True


def _always_false(pattern: str, bytecode: bytes) -> bool:
    return False


def _check_bytecode_nonempty(pattern: str, bytecode: bytes) -> bool:
    return len(bytecode) > 0


def _make_tile(pattern="test pattern", bytecode=b'\x01\x02', confidence=0.9,
               safety_contract=None, metadata=None):
    return LockTile(
        pattern=pattern,
        bytecode=bytecode,
        confidence=confidence,
        safety_contract=safety_contract or _always_true,
        metadata=metadata or {},
    )


def _make_conditional(pred, true_b, false_b):
    """Helper: call conditional() with a dummy caller tile."""
    dummy = _make_tile(pattern="__cond__", confidence=1.0)
    return dummy.conditional(pred, true_b, false_b)


# ===========================================================================
# 1. Construction & Validation
# ===========================================================================

class TestLockTileConstruction:
    """Tests for LockTile creation and property validation."""

    def test_valid_tile_creation(self):
        tile = _make_tile()
        assert tile.pattern == "test pattern"
        assert tile.bytecode == b'\x01\x02'
        assert tile.confidence == 0.9

    def test_default_metadata_is_empty_dict(self):
        tile = _make_tile()
        assert tile.metadata == {}

    def test_custom_metadata(self):
        tile = _make_tile(metadata={'id': 'nav-1', 'domain': 'maritime'})
        assert tile.metadata['id'] == 'nav-1'
        assert tile.metadata['domain'] == 'maritime'

    def test_confidence_at_minimum_boundary(self):
        tile = _make_tile(confidence=0.0)
        assert tile.confidence == 0.0

    def test_confidence_at_maximum_boundary(self):
        tile = _make_tile(confidence=1.0)
        assert tile.confidence == 1.0

    def test_confidence_negative_raises(self):
        with pytest.raises(ValueError, match="Confidence must be in"):
            _make_tile(confidence=-0.01)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="Confidence must be in"):
            _make_tile(confidence=1.01)

    def test_confidence_very_negative_raises(self):
        with pytest.raises(ValueError):
            _make_tile(confidence=-100.0)

    def test_empty_bytecode_allowed(self):
        tile = _make_tile(bytecode=b'')
        assert tile.bytecode == b''

    def test_empty_pattern_allowed(self):
        tile = _make_tile(pattern="")
        assert tile.pattern == ""


# ===========================================================================
# 2. Confidence Zone Classification
# ===========================================================================

class TestConfidenceZone:
    """Tests for three-zone intelligence classification."""

    def test_green_zone_high(self):
        assert _make_tile(confidence=1.0).zone == ConfidenceZone.GREEN

    def test_green_zone_boundary(self):
        assert _make_tile(confidence=0.96).zone == ConfidenceZone.GREEN

    def test_green_zone_just_above_threshold(self):
        assert _make_tile(confidence=0.951).zone == ConfidenceZone.GREEN

    def test_yellow_zone_mid(self):
        assert _make_tile(confidence=0.85).zone == ConfidenceZone.YELLOW

    def test_yellow_zone_high(self):
        assert _make_tile(confidence=0.95).zone == ConfidenceZone.YELLOW

    def test_yellow_zone_low(self):
        assert _make_tile(confidence=0.76).zone == ConfidenceZone.YELLOW

    def test_red_zone_mid(self):
        assert _make_tile(confidence=0.5).zone == ConfidenceZone.RED

    def test_red_zone_high(self):
        assert _make_tile(confidence=0.75).zone == ConfidenceZone.RED

    def test_red_zone_zero(self):
        assert _make_tile(confidence=0.0).zone == ConfidenceZone.RED

    def test_zone_enum_values(self):
        assert ConfidenceZone.GREEN.value == "GREEN"
        assert ConfidenceZone.YELLOW.value == "YELLOW"
        assert ConfidenceZone.RED.value == "RED"


# ===========================================================================
# 3. Safety Contract Verification
# ===========================================================================

class TestSafetyContract:
    """Tests for safety contract invocation."""

    def test_verify_returns_true(self):
        tile = _make_tile(safety_contract=_always_true)
        assert tile.verify("any", b'\x00') is True

    def test_verify_returns_false(self):
        tile = _make_tile(safety_contract=_always_false)
        assert tile.verify("any", b'\x00') is False

    def test_verify_bytecode_nonempty(self):
        tile = _make_tile(safety_contract=_check_bytecode_nonempty)
        assert tile.verify("p", b'\x01') is True
        assert tile.verify("p", b'') is False

    def test_verify_passes_correct_args(self):
        received = {}

        def capture(pattern, bytecode):
            received['p'] = pattern
            received['b'] = bytecode
            return True

        tile = _make_tile(safety_contract=capture)
        tile.verify("hello", b'\xff')
        assert received['p'] == "hello"
        assert received['b'] == b'\xff'


# ===========================================================================
# 4. Sequential Composition
# ===========================================================================

class TestSequentialComposition:
    """Tests for the compose operator (sequential composition)."""

    def test_confidence_multiplies(self):
        t1 = _make_tile(confidence=0.9)
        t2 = _make_tile(confidence=0.8)
        composed = t1.compose(t2)
        assert composed.confidence == pytest.approx(0.9 * 0.8)

    def test_confidence_with_1_and_any(self):
        t1 = _make_tile(confidence=1.0)
        t2 = _make_tile(confidence=0.85)
        composed = t1.compose(t2)
        assert composed.confidence == pytest.approx(0.85)

    def test_confidence_with_0(self):
        t1 = _make_tile(confidence=0.0)
        t2 = _make_tile(confidence=0.9)
        composed = t1.compose(t2)
        assert composed.confidence == pytest.approx(0.0)

    def test_pattern_joined_with_semicolon(self):
        t1 = _make_tile(pattern="step1")
        t2 = _make_tile(pattern="step2")
        composed = t1.compose(t2)
        assert composed.pattern == "step1; step2"

    def test_bytecode_concatenated(self):
        t1 = _make_tile(bytecode=b'\x01')
        t2 = _make_tile(bytecode=b'\x02')
        composed = t1.compose(t2)
        assert composed.bytecode == b'\x01\x02'

    def test_metadata_has_composition_type(self):
        t1 = _make_tile(metadata={'id': 'a'})
        t2 = _make_tile(metadata={'id': 'b'})
        composed = t1.compose(t2)
        assert composed.metadata['composition_type'] == 'sequential'

    def test_metadata_tracks_source_ids(self):
        t1 = _make_tile(metadata={'id': 'alpha'})
        t2 = _make_tile(metadata={'id': 'beta'})
        composed = t1.compose(t2)
        assert 'alpha' in composed.metadata['composed_from']
        assert 'beta' in composed.metadata['composed_from']

    def test_composed_verify_both_pass(self):
        t1 = _make_tile(safety_contract=_always_true)
        t2 = _make_tile(safety_contract=_always_true)
        composed = t1.compose(t2)
        assert composed.verify("a", b'\x01\x02') is True

    def test_composed_verify_first_fails(self):
        t1 = _make_tile(safety_contract=_always_false)
        t2 = _make_tile(safety_contract=_always_true)
        composed = t1.compose(t2)
        assert composed.verify("a", b'\x01\x02') is False

    def test_composed_verify_second_fails(self):
        t1 = _make_tile(safety_contract=_always_true)
        t2 = _make_tile(safety_contract=_always_false)
        composed = t1.compose(t2)
        assert composed.verify("a", b'\x01\x02') is False

    def test_associativity_confidence(self):
        """Theorem T3: (L1 o L2) o L3 = L1 o (L2 o L3) for confidence."""
        t1 = _make_tile(confidence=0.95)
        t2 = _make_tile(confidence=0.90)
        t3 = _make_tile(confidence=0.85)

        left = t1.compose(t2).compose(t3)
        right = t1.compose(t2.compose(t3))

        assert left.confidence == pytest.approx(right.confidence)

    def test_monotonicity_composed_confidence_lower(self):
        """Confidence of composed tile <= min of individual confidences."""
        t1 = _make_tile(confidence=0.9)
        t2 = _make_tile(confidence=0.8)
        composed = t1.compose(t2)
        assert composed.confidence <= min(t1.confidence, t2.confidence)
        assert composed.confidence < min(t1.confidence, t2.confidence)

    def test_associativity_bytecode(self):
        """Bytecode concatenation is associative."""
        t1 = _make_tile(bytecode=b'\x01')
        t2 = _make_tile(bytecode=b'\x02')
        t3 = _make_tile(bytecode=b'\x03')

        left = t1.compose(t2).compose(t3)
        right = t1.compose(t2.compose(t3))

        assert left.bytecode == right.bytecode == b'\x01\x02\x03'


# ===========================================================================
# 5. Parallel Composition
# ===========================================================================

class TestParallelComposition:
    """Tests for the parallel operator (parallel composition)."""

    def test_confidence_is_minimum(self):
        t1 = _make_tile(confidence=0.9)
        t2 = _make_tile(confidence=0.7)
        composed = t1.parallel(t2)
        assert composed.confidence == pytest.approx(0.7)

    def test_confidence_equal_inputs(self):
        t1 = _make_tile(confidence=0.85)
        t2 = _make_tile(confidence=0.85)
        composed = t1.parallel(t2)
        assert composed.confidence == pytest.approx(0.85)

    def test_confidence_one_is_1(self):
        t1 = _make_tile(confidence=1.0)
        t2 = _make_tile(confidence=0.6)
        composed = t1.parallel(t2)
        assert composed.confidence == pytest.approx(0.6)

    def test_pattern_contains_parallel_symbol(self):
        t1 = _make_tile(pattern="a")
        t2 = _make_tile(pattern="b")
        composed = t1.parallel(t2)
        assert "a" in composed.pattern
        assert "b" in composed.pattern
        assert "\u2225" in composed.pattern

    def test_bytecode_concatenated(self):
        t1 = _make_tile(bytecode=b'\x10')
        t2 = _make_tile(bytecode=b'\x20')
        composed = t1.parallel(t2)
        assert composed.bytecode == b'\x10\x20'

    def test_metadata_composition_type_parallel(self):
        t1 = _make_tile(metadata={'id': 'x'})
        t2 = _make_tile(metadata={'id': 'y'})
        composed = t1.parallel(t2)
        assert composed.metadata['composition_type'] == 'parallel'

    def test_commutativity_confidence(self):
        t1 = _make_tile(confidence=0.8)
        t2 = _make_tile(confidence=0.6)
        assert t1.parallel(t2).confidence == pytest.approx(
            t2.parallel(t1).confidence
        )

    def test_verify_both_pass(self):
        t1 = _make_tile(safety_contract=_always_true)
        t2 = _make_tile(safety_contract=_always_true)
        composed = t1.parallel(t2)
        assert composed.verify("a", b'\x01\x02') is True

    def test_verify_one_fails(self):
        t1 = _make_tile(safety_contract=_always_false)
        t2 = _make_tile(safety_contract=_always_true)
        composed = t1.parallel(t2)
        assert composed.verify("a", b'\x01\x02') is False

    def test_parallel_with_three_tiles(self):
        t1 = _make_tile(confidence=0.95)
        t2 = _make_tile(confidence=0.80)
        t3 = _make_tile(confidence=0.70)
        result = t1.parallel(t2).parallel(t3)
        assert result.confidence == pytest.approx(0.70)


# ===========================================================================
# 6. Conditional Composition
# ===========================================================================

class TestConditionalComposition:
    """Tests for the conditional operator (conditional composition)."""

    def _make_predicate_true(self):
        return _make_tile(pattern="pred", confidence=0.9, safety_contract=_always_true)

    def _make_predicate_false(self):
        return _make_tile(pattern="pred", confidence=0.9, safety_contract=_always_false)

    def test_confidence_formula_d33(self):
        """Theorem D3.3: c_cond = c_pred * (c_pred * c_true + (1-c_pred) * c_false)"""
        pred = _make_tile(pattern="p", confidence=0.8)
        true_b = _make_tile(pattern="t", confidence=0.9)
        false_b = _make_tile(pattern="f", confidence=0.7)

        composed = _make_conditional(pred, true_b, false_b)
        expected = 0.8 * (0.8 * 0.9 + 0.2 * 0.7)
        assert composed.confidence == pytest.approx(expected)

    def test_confidence_perfect_predicate_true_branch(self):
        pred = _make_tile(pattern="p", confidence=1.0)
        true_b = _make_tile(pattern="t", confidence=0.95)
        false_b = _make_tile(pattern="f", confidence=0.5)

        composed = _make_conditional(pred, true_b, false_b)
        expected = 1.0 * (1.0 * 0.95 + 0.0 * 0.5)
        assert composed.confidence == pytest.approx(0.95)

    def test_confidence_zero_predicate(self):
        pred = _make_tile(pattern="p", confidence=0.0)
        true_b = _make_tile(pattern="t", confidence=0.99)
        false_b = _make_tile(pattern="f", confidence=0.8)

        composed = _make_conditional(pred, true_b, false_b)
        assert composed.confidence == pytest.approx(0.0)

    def test_pattern_contains_if_then_else(self):
        pred = _make_tile(pattern="check")
        true_b = _make_tile(pattern="do_a")
        false_b = _make_tile(pattern="do_b")
        composed = _make_conditional(pred, true_b, false_b)
        assert "if" in composed.pattern
        assert "check" in composed.pattern
        assert "do_a" in composed.pattern
        assert "do_b" in composed.pattern

    def test_bytecode_is_empty(self):
        pred = self._make_predicate_true()
        true_b = _make_tile(bytecode=b'\x01')
        false_b = _make_tile(bytecode=b'\x02')
        composed = _make_conditional(pred, true_b, false_b)
        assert composed.bytecode == b''

    def test_metadata_composition_type_conditional(self):
        pred = self._make_predicate_true()
        true_b = _make_tile(metadata={'id': 't'})
        false_b = _make_tile(metadata={'id': 'f'})
        composed = _make_conditional(pred, true_b, false_b)
        assert composed.metadata['composition_type'] == 'conditional'

    def test_verify_true_branch(self):
        pred = self._make_predicate_true()
        true_b = _make_tile(safety_contract=_always_true)
        false_b = _make_tile(safety_contract=_always_false)
        composed = _make_conditional(pred, true_b, false_b)
        assert composed.verify("p", b'\x01') is True

    def test_verify_false_branch(self):
        pred = self._make_predicate_false()
        true_b = _make_tile(safety_contract=_always_false)
        false_b = _make_tile(safety_contract=_always_true)
        composed = _make_conditional(pred, true_b, false_b)
        assert composed.verify("p", b'\x01') is True

    def test_confidence_symmetric_equal_branches(self):
        """When true and false branches have equal confidence."""
        pred = _make_tile(pattern="p", confidence=0.5)
        true_b = _make_tile(pattern="t", confidence=0.8)
        false_b = _make_tile(pattern="f", confidence=0.8)
        composed = _make_conditional(pred, true_b, false_b)
        # c = 0.5 * (0.5*0.8 + 0.5*0.8) = 0.5 * 0.8 = 0.4
        assert composed.confidence == pytest.approx(0.4)
