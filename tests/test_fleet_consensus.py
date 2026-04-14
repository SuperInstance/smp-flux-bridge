"""Tests for FleetConsensus distributed lock aggregation."""

import pytest
from lock_tile import FleetConsensus, LockTile


def _make_tile(pattern="check gauge", confidence=0.85, bytecode=b'\x30\x05',
               safety_contract=None, metadata=None):
    return LockTile(
        pattern=pattern,
        bytecode=bytecode,
        confidence=confidence,
        safety_contract=safety_contract or (lambda p, b: True),
        metadata=metadata or {},
    )


class TestProposeLock:
    """Tests for propose_lock."""

    def test_returns_lock_id_string(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        lock_id = fleet.propose_lock(tile, "agent-A")
        assert isinstance(lock_id, str)
        assert len(lock_id) == 16

    def test_stores_lock_in_library(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        lock_id = fleet.propose_lock(tile, "agent-A")
        assert lock_id in fleet.lock_library

    def test_different_agents_same_tile_different_ids(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        id1 = fleet.propose_lock(tile, "agent-A")
        id2 = fleet.propose_lock(tile, "agent-B")
        assert id1 != id2

    def test_same_agent_same_tile_same_id(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        id1 = fleet.propose_lock(tile, "agent-A")
        # Re-proposing same tile with same agent should produce same ID
        # because the tile metadata is the same (pattern + bytecode + agent_id)
        id2 = fleet.propose_lock(tile, "agent-A")
        assert id1 == id2

    def test_sets_proposed_by_metadata(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        fleet.propose_lock(tile, "agent-42")
        # Find the lock in the library
        stored_tile = list(fleet.lock_library.values())[0]
        assert stored_tile.metadata.get('proposed_by') == "agent-42"

    def test_sets_timestamp_metadata(self):
        import time
        before = time.time()
        fleet = FleetConsensus()
        tile = _make_tile()
        fleet.propose_lock(tile, "agent-A")
        after = time.time()
        stored_tile = list(fleet.lock_library.values())[0]
        ts = stored_tile.metadata.get('timestamp')
        assert before <= ts <= after


class TestAggregateLocks:
    """Tests for aggregate_locks."""

    def test_single_lock_no_conflict(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        result = fleet.aggregate_locks([tile], level=1)
        assert len(result) == 1

    def test_different_patterns_no_conflict(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="check gauge")
        t2 = _make_tile(pattern="check temperature")
        result = fleet.aggregate_locks([t1, t2], level=1)
        assert len(result) == 2

    def test_same_pattern_conflict_resolution(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="check gauge", confidence=0.80,
                        metadata={'id': 'low'})
        t2 = _make_tile(pattern="check gauge", confidence=0.90,
                        metadata={'id': 'high'})
        result = fleet.aggregate_locks([t1, t2], level=1)
        assert len(result) == 1
        # Should select higher confidence lock
        resolved = list(result.values())[0]
        assert resolved.confidence == pytest.approx(0.90)

    def test_conflict_resolution_with_verification_bonus(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="check gauge", confidence=0.85,
                        metadata={'verified_by': ['model-a', 'model-b']})
        t2 = _make_tile(pattern="check gauge", confidence=0.90,
                        metadata={})
        result = fleet.aggregate_locks([t1, t2], level=1)
        resolved = list(result.values())[0]
        # t1 has base 0.85 + 0.1*2 = 1.05 -> wins over t2's 0.90
        assert resolved.confidence == pytest.approx(0.85)

    def test_three_way_conflict(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="navigate", confidence=0.70)
        t2 = _make_tile(pattern="navigate", confidence=0.85)
        t3 = _make_tile(pattern="navigate", confidence=0.80)
        result = fleet.aggregate_locks([t1, t2, t3], level=1)
        assert len(result) == 1
        resolved = list(result.values())[0]
        assert resolved.confidence == pytest.approx(0.85)

    def test_empty_list_returns_empty(self):
        fleet = FleetConsensus()
        result = fleet.aggregate_locks([], level=1)
        assert len(result) == 0

    def test_case_insensitive_pattern_grouping(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="Check Gauge")
        t2 = _make_tile(pattern="check gauge")
        result = fleet.aggregate_locks([t1, t2], level=1)
        assert len(result) == 1


class TestVerifyLockCrossModel:
    """Tests for verify_lock_cross_model."""

    def test_adds_verifiers(self):
        fleet = FleetConsensus()
        tile = _make_tile()
        verified = fleet.verify_lock_cross_model(tile, ['model-a', 'model-b'])
        assert 'model-a' in verified.metadata['verified_by']
        assert 'model-b' in verified.metadata['verified_by']

    def test_no_duplicate_verifiers(self):
        fleet = FleetConsensus()
        tile = _make_tile(metadata={'verified_by': ['model-a']})
        verified = fleet.verify_lock_cross_model(tile, ['model-a', 'model-b'])
        assert verified.metadata['verified_by'] == ['model-a', 'model-b']

    def test_confidence_increases_with_verification(self):
        fleet = FleetConsensus()
        tile = _make_tile(confidence=0.80)
        verified = fleet.verify_lock_cross_model(tile, ['model-a'])
        assert verified.confidence > tile.confidence
        # 0.80 + 0.05*1 = 0.85
        assert verified.confidence == pytest.approx(0.85)

    def test_confidence_clamped_at_1(self):
        fleet = FleetConsensus()
        tile = _make_tile(confidence=0.95)
        verified = fleet.verify_lock_cross_model(tile, ['a', 'b', 'c', 'd', 'e'])
        assert verified.confidence == pytest.approx(1.0)

    def test_preserves_pattern_and_bytecode(self):
        fleet = FleetConsensus()
        tile = _make_tile(pattern="nav", bytecode=b'\xff')
        verified = fleet.verify_lock_cross_model(tile, ['model-a'])
        assert verified.pattern == "nav"
        assert verified.bytecode == b'\xff'


class TestGroupByPattern:
    """Tests for _group_by_pattern internal method."""

    def test_groups_identical_patterns(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="test")
        t2 = _make_tile(pattern="test")
        groups = fleet._group_by_pattern([t1, t2])
        assert len(groups) == 1
        assert len(groups["test"]) == 2

    def test_strips_and_lowercases(self):
        fleet = FleetConsensus()
        t1 = _make_tile(pattern="  Test  ")
        t2 = _make_tile(pattern="test")
        groups = fleet._group_by_pattern([t1, t2])
        assert len(groups) == 1


class TestResolveConflict:
    """Tests for _resolve_conflict internal method."""

    def test_picks_highest_confidence(self):
        fleet = FleetConsensus()
        t1 = _make_tile(confidence=0.70)
        t2 = _make_tile(confidence=0.90)
        resolved = fleet._resolve_conflict([t1, t2])
        assert resolved.confidence == pytest.approx(0.90)

    def test_sets_resolution_metadata(self):
        fleet = FleetConsensus()
        t1 = _make_tile(confidence=0.70)
        t2 = _make_tile(confidence=0.90)
        resolved = fleet._resolve_conflict([t1, t2])
        assert 'resolution_score' in resolved.metadata
        assert resolved.metadata['resolution_candidates'] == 2
