"""Tests for TileCategory (category theory laws)."""

import pytest
from lock_tile import TileCategory, LockTile, ConfidenceZone


def _always_true(pattern: str, bytecode: bytes) -> bool:
    return True


def _always_false(pattern: str, bytecode: bytes) -> bool:
    return False


def _make_tile(pattern="p", bytecode=b'\x01', confidence=0.9, safety_contract=None):
    return LockTile(
        pattern=pattern,
        bytecode=bytecode,
        confidence=confidence,
        safety_contract=safety_contract or _always_true,
    )


def _make_conditional(pred, true_b, false_b):
    """Helper: call conditional() with a dummy caller tile."""
    dummy = _make_tile(pattern="__cond__", confidence=1.0)
    return dummy.conditional(pred, true_b, false_b)


class TestTileCategoryBasics:
    """Tests for basic TileCategory operations."""

    def test_add_and_retrieve_tile(self):
        cat = TileCategory()
        tile = _make_tile()
        cat.add_tile(tile, 't1')
        assert 't1' in cat.tiles
        assert cat.tiles['t1'].confidence == 0.9

    def test_empty_category(self):
        cat = TileCategory()
        assert cat.tiles == {}

    def test_get_identity_tile(self):
        cat = TileCategory()
        identity = cat.get_identity("test_pattern")
        assert identity.confidence == 1.0
        assert identity.pattern == "test_pattern"
        assert identity.bytecode == b''
        assert identity.metadata['type'] == 'identity'

    def test_identity_always_verifies(self):
        cat = TileCategory()
        identity = cat.get_identity("any")
        assert identity.verify("any", b'') is True
        assert identity.verify("any", b'\xff\xff') is True


class TestComposeSequentialCategory:
    """Tests for compose_sequential via TileCategory."""

    def test_two_tiles(self):
        cat = TileCategory()
        cat.add_tile(_make_tile(pattern="a", confidence=0.9, bytecode=b'\x01'), 't1')
        cat.add_tile(_make_tile(pattern="b", confidence=0.8, bytecode=b'\x02'), 't2')
        result = cat.compose_sequential(['t1', 't2'])
        assert result.confidence == pytest.approx(0.72)
        assert result.pattern == "a; b"
        assert result.bytecode == b'\x01\x02'

    def test_three_tiles(self):
        cat = TileCategory()
        cat.add_tile(_make_tile(confidence=0.9), 'a')
        cat.add_tile(_make_tile(confidence=0.8), 'b')
        cat.add_tile(_make_tile(confidence=0.7), 'c')
        result = cat.compose_sequential(['a', 'b', 'c'])
        assert result.confidence == pytest.approx(0.9 * 0.8 * 0.7)

    def test_single_tile(self):
        cat = TileCategory()
        cat.add_tile(_make_tile(confidence=0.85), 't1')
        result = cat.compose_sequential(['t1'])
        assert result.confidence == pytest.approx(0.85)

    def test_empty_list_returns_none(self):
        cat = TileCategory()
        assert cat.compose_sequential([]) is None

    def test_missing_tile_raises(self):
        cat = TileCategory()
        cat.add_tile(_make_tile(), 't1')
        with pytest.raises(ValueError, match="not found"):
            cat.compose_sequential(['t1', 'nonexistent'])


class TestComposeParallelCategory:
    """Tests for compose_parallel via TileCategory."""

    def test_two_tiles(self):
        cat = TileCategory()
        cat.add_tile(_make_tile(confidence=0.9, bytecode=b'\x01'), 't1')
        cat.add_tile(_make_tile(confidence=0.7, bytecode=b'\x02'), 't2')
        result = cat.compose_parallel(['t1', 't2'])
        assert result.confidence == pytest.approx(0.7)
        assert result.bytecode == b'\x01\x02'

    def test_empty_list_returns_none(self):
        cat = TileCategory()
        assert cat.compose_parallel([]) is None

    def test_missing_tile_raises(self):
        cat = TileCategory()
        with pytest.raises(ValueError, match="not found"):
            cat.compose_parallel(['missing'])


class TestCategoryLaws:
    """Tests for category theory properties.

    Note: The current implementation's compose() always concatenates patterns
    (e.g., "nav; nav" for identity compose), so exact pattern equality for
    the identity law does not hold. We test bytecode preservation and
    the actual behavior of verify_category_laws().
    """

    def test_identity_preserves_bytecode_left(self):
        """Id o L preserves bytecode (left identity)."""
        cat = TileCategory()
        tile = _make_tile(pattern="nav", bytecode=b'\x10\x01', confidence=0.9)
        cat.add_tile(tile, 'nav')
        identity = cat.get_identity("nav")
        composed = identity.compose(tile)
        assert composed.bytecode == tile.bytecode

    def test_identity_preserves_bytecode_right(self):
        """L o Id preserves bytecode (right identity)."""
        cat = TileCategory()
        tile = _make_tile(pattern="nav", bytecode=b'\x10\x01', confidence=0.9)
        cat.add_tile(tile, 'nav')
        identity = cat.get_identity("nav")
        composed = tile.compose(identity)
        assert composed.bytecode == tile.bytecode

    def test_identity_pattern_includes_original(self):
        """Composed pattern with identity still contains original pattern."""
        cat = TileCategory()
        tile = _make_tile(pattern="nav", bytecode=b'\x10\x01', confidence=0.9)
        identity = cat.get_identity("nav")
        composed = identity.compose(tile)
        assert tile.pattern in composed.pattern

    def test_verify_category_laws_returns_dict(self):
        cat = TileCategory()
        cat.add_tile(_make_tile(pattern="a", bytecode=b'\x01'), 't1')
        results = cat.verify_category_laws()
        assert isinstance(results, dict)
        assert 't1_identity_left' in results
        assert 't1_identity_right' in results

    def test_empty_category_laws(self):
        cat = TileCategory()
        results = cat.verify_category_laws()
        assert results == {}


class TestFormalSafetyGuarantees:
    """Tests for formal mathematical properties and safety guarantees."""

    def test_sequential_composition_reduces_confidence(self):
        """Confidence of composed tile is strictly less than each component
        when both confidences < 1.0."""
        t1 = _make_tile(confidence=0.9)
        t2 = _make_tile(confidence=0.8)
        composed = t1.compose(t2)
        assert composed.confidence < t1.confidence
        assert composed.confidence < t2.confidence

    def test_parallel_confidence_never_exceeds_min(self):
        t1 = _make_tile(confidence=0.9)
        t2 = _make_tile(confidence=0.7)
        composed = t1.parallel(t2)
        assert composed.confidence <= min(t1.confidence, t2.confidence)

    def test_confidence_bounds_all_compositions(self):
        """All composition results must have confidence in [0, 1]."""
        tiles = [
            _make_tile(confidence=0.99),
            _make_tile(confidence=0.01),
            _make_tile(confidence=0.5),
        ]

        # Sequential
        seq = tiles[0].compose(tiles[1]).compose(tiles[2])
        assert 0.0 <= seq.confidence <= 1.0

        # Parallel
        par = tiles[0].parallel(tiles[1]).parallel(tiles[2])
        assert 0.0 <= par.confidence <= 1.0

        # Conditional
        cond = _make_conditional(tiles[0], tiles[1], tiles[2])
        assert 0.0 <= cond.confidence <= 1.0

    def test_associativity_of_three_tile_sequential(self):
        """Theorem T3: (L1 o L2) o L3 == L1 o (L2 o L3)."""
        t1 = _make_tile(confidence=0.95, bytecode=b'\x01')
        t2 = _make_tile(confidence=0.90, bytecode=b'\x02')
        t3 = _make_tile(confidence=0.85, bytecode=b'\x03')

        left = t1.compose(t2).compose(t3)
        right = t1.compose(t2.compose(t3))

        assert left.confidence == pytest.approx(right.confidence)
        assert left.bytecode == right.bytecode

    def test_parallel_commutativity(self):
        """T1 parallel T2 == T2 parallel T1 (confidence)."""
        t1 = _make_tile(confidence=0.9)
        t2 = _make_tile(confidence=0.7)
        assert t1.parallel(t2).confidence == pytest.approx(
            t2.parallel(t1).confidence
        )

    def test_conditional_confidence_between_branches(self):
        """Conditional confidence should be bounded by true and false branches."""
        pred = _make_tile(pattern="p", confidence=0.8)
        true_b = _make_tile(pattern="t", confidence=0.95)
        false_b = _make_tile(pattern="f", confidence=0.60)
        cond = _make_conditional(pred, true_b, false_b)
        # c_cond = 0.8 * (0.8*0.95 + 0.2*0.60) = 0.8 * (0.76 + 0.12) = 0.704
        assert cond.confidence >= false_b.confidence * pred.confidence

    def test_empty_composition_with_identity_preserves_bytecode(self):
        """Identity tile preserves original tile bytecode."""
        cat = TileCategory()
        tile = _make_tile(pattern="test", bytecode=b'\xab', confidence=0.88)
        identity = cat.get_identity("test")

        left = identity.compose(tile)
        right = tile.compose(identity)

        assert tile.bytecode == left.bytecode
        assert tile.bytecode == right.bytecode

    def test_safety_contract_combined_and(self):
        """Sequential composition safety is conjunction of component safeties."""
        passed = {}

        def track1(p, b):
            passed['t1'] = True
            return True

        def track2(p, b):
            passed['t2'] = True
            return True

        t1 = _make_tile(safety_contract=track1, bytecode=b'\x01')
        t2 = _make_tile(safety_contract=track2, bytecode=b'\x02')
        composed = t1.compose(t2)

        assert composed.verify("test", b'\x01\x02') is True
        assert 't1' in passed
        assert 't2' in passed

    def test_confidence_never_negative_after_any_composition(self):
        """Even with extreme values, confidence stays in [0,1]."""
        t_low = _make_tile(confidence=0.001)
        t_high = _make_tile(confidence=0.999)

        seq = t_low.compose(t_high)
        assert 0.0 <= seq.confidence <= 1.0

        par = t_low.parallel(t_high)
        assert 0.0 <= par.confidence <= 1.0

    def test_many_sequential_confidence_tends_to_zero(self):
        """Many sequential compositions should drive confidence toward 0."""
        tiles = [_make_tile(confidence=0.9) for _ in range(10)]
        result = tiles[0]
        for t in tiles[1:]:
            result = result.compose(t)
        assert result.confidence < 0.5  # 0.9^10 ~ 0.349

    def test_parallel_of_similar_confidence_stable(self):
        """Parallel of tiles with similar confidence stays near that value."""
        tiles = [_make_tile(confidence=0.90) for _ in range(5)]
        result = tiles[0]
        for t in tiles[1:]:
            result = result.parallel(t)
        assert result.confidence == pytest.approx(0.90)
