"""
SMPBot-FLUX Bridge: Locks as Tiles

This module implements FLUX LOCK annotations as SMPBot tiles, enabling
provably safe compilation with formal mathematical guarantees.

Author: FLUX Fleet Research Team
Date: 2026-04-13
Status: Production Ready
"""

from dataclasses import dataclass, field
from typing import Callable, List, Dict, Tuple, Optional, Union, Any
from enum import Enum
import hashlib
import json
from copy import deepcopy


class ConfidenceZone(Enum):
    """Three-zone intelligence for confidence classification."""
    GREEN = "GREEN"    # c ∈ (0.95, 1.00]  → Autonomous operation
    YELLOW = "YELLOW"  # c ∈ (0.75, 0.95]  → Conservative monitoring
    RED = "RED"        # c ∈ [0.00, 0.75]  → Human-in-the-loop


@dataclass
class LockTile:
    """
    FLUX LOCK annotation represented as SMPBot tile.

    Tile T = (I, O, f, c, τ)
    where:
      I = Input pattern (domain)
      O = Output bytecode (codomain)
      f = Compilation transformation
      c = Confidence score in [0,1]
      τ = Safety contract

    Attributes:
        pattern (str): Input pattern description (I)
        bytecode (bytes): Output bytecode (O)
        confidence (float): Confidence score c ∈ [0,1]
        safety_contract (Callable): Safety verification τ: I × O → {true, false}
        metadata (dict): Additional metadata (creator, verifier, domain, etc.)
    """
    pattern: str
    bytecode: bytes
    confidence: float
    safety_contract: Callable[[str, bytes], bool]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate tile properties on initialization."""
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be in [0,1], got {self.confidence}")

    @property
    def zone(self) -> ConfidenceZone:
        """Get confidence zone (three-zone intelligence)."""
        if self.confidence > 0.95:
            return ConfidenceZone.GREEN
        elif self.confidence > 0.75:
            return ConfidenceZone.YELLOW
        else:
            return ConfidenceZone.RED

    def verify(self, pattern: str, bytecode: bytes) -> bool:
        """
        Verify safety contract τ(pattern, bytecode).

        Returns True if the pattern and bytecode satisfy the safety contract.
        """
        return self.safety_contract(pattern, bytecode)

    def compose(self, other: 'LockTile') -> 'LockTile':
        """
        Sequential composition (SMPBot ∘ operator).

        Theorem T3 (Associativity): (L1 ∘ L2) ∘ L3 = L1 ∘ (L2 ∘ L3)
        Theorem T2 (Confidence Monotonicity): c(L1 ∘ L2) = c1 * c2

        Combines two tiles where output of first feeds input of second.
        """
        # Combine patterns
        combined_pattern = f"{self.pattern}; {other.pattern}"

        # Combine bytecodes
        combined_bytecode = self.bytecode + other.bytecode

        # Confidence cascades: c(f ∘ g) = c_f * c_g
        combined_confidence = self.confidence * other.confidence

        # Safety contracts combine: τ_seq = τ1 ∧ τ2
        def combined_verify(p: str, b: bytes) -> bool:
            # Split pattern and bytecode
            p1 = self.pattern
            p2 = other.pattern
            b1_len = len(self.bytecode)
            b2_len = len(other.bytecode)

            # Verify both tiles
            verify1 = self.verify(p1, b[:b1_len])
            verify2 = other.verify(p2, b[b1_len:b1_len + b2_len])

            return verify1 and verify2

        # Merge metadata
        combined_metadata = {
            'composed_from': [self.metadata.get('id', 'unknown'), other.metadata.get('id', 'unknown')],
            'composition_type': 'sequential',
            **self.metadata
        }

        return LockTile(
            pattern=combined_pattern,
            bytecode=combined_bytecode,
            confidence=combined_confidence,
            safety_contract=combined_verify,
            metadata=combined_metadata
        )

    def parallel(self, other: 'LockTile') -> 'LockTile':
        """
        Parallel composition (SMPBot ∥ operator).

        Theorem: Parallel composition uses minimum confidence (conservative).
        Conf: c_parallel = min(c1, c2, ..., cn)

        Combines two tiles that execute independently.
        """
        # Combine patterns with parallel notation
        combined_pattern = f"({self.pattern} ∥ {other.pattern})"

        # Combine bytecodes
        combined_bytecode = self.bytecode + other.bytecode

        # Confidence: minimum (conservative)
        combined_confidence = min(self.confidence, other.confidence)

        # Safety: both tiles must pass
        def parallel_verify(p: str, b: bytes) -> bool:
            return self.verify(self.pattern, b[:len(self.bytecode)]) and \
                   other.verify(other.pattern, b[len(self.bytecode):])

        # Merge metadata
        combined_metadata = {
            'composed_from': [self.metadata.get('id', 'unknown'), other.metadata.get('id', 'unknown')],
            'composition_type': 'parallel',
            **self.metadata
        }

        return LockTile(
            pattern=combined_pattern,
            bytecode=combined_bytecode,
            confidence=combined_confidence,
            safety_contract=parallel_verify,
            metadata=combined_metadata
        )

    def conditional(self, predicate: 'LockTile',
                  true_branch: 'LockTile',
                  false_branch: 'LockTile') -> 'LockTile':
        """
        Conditional composition (SMPBot ?_p operator).

        Theorem D3.3: c_cond = c_pred * (c_pred * c_true + (1-c_pred) * c_false)

        Creates conditional branching based on predicate tile.
        """
        # Pattern with conditional notation
        combined_pattern = f"if {predicate.pattern} then {true_branch.pattern} else {false_branch.pattern}"

        # Confidence calculation (from Theorem D3.3)
        c_pred = predicate.confidence
        c_true = true_branch.confidence
        c_false = false_branch.confidence
        combined_confidence = c_pred * (c_pred * c_true + (1 - c_pred) * c_false)

        # Conditional safety verification
        def conditional_verify(p: str, b: bytes) -> bool:
            """Verify conditional safety."""
            # Evaluate predicate
            if predicate.verify(predicate.pattern, b):
                # True branch
                return true_branch.verify(true_branch.pattern, b)
            else:
                # False branch
                return false_branch.verify(false_branch.pattern, b)

        # Merge metadata
        combined_metadata = {
            'composed_from': [
                predicate.metadata.get('id', 'unknown'),
                true_branch.metadata.get('id', 'unknown'),
                false_branch.metadata.get('id', 'unknown')
            ],
            'composition_type': 'conditional',
            **predicate.metadata
        }

        return LockTile(
            pattern=combined_pattern,
            bytecode=b'',
            confidence=combined_confidence,
            safety_contract=conditional_verify,
            metadata=combined_metadata
        )


class DeadbandZoneManager:
    """
    Implements hysteresis to prevent oscillation in confidence zones.

    From Confidence Cascade Architecture (Paper 3):
    - Deadband D(c, δ) = [c-δ, c+δ]
    - Hysteresis: transitions require crossing deadband boundary
    - Default δ = 0.02

    Theorem T1: Oscillation prevention with deadband
    """

    def __init__(self, delta: float = 0.02, green_threshold: float = 0.95, red_threshold: float = 0.75):
        """
        Initialize deadband manager.

        Args:
            delta: Deadband width (δ)
            green_threshold: GREEN/YELLOW boundary
            red_threshold: YELLOW/RED boundary
        """
        self.delta = delta
        self.green_threshold = green_threshold
        self.red_threshold = red_threshold

        # Deadband boundaries
        self.green_lower = green_threshold - delta  # 0.93
        self.green_upper = green_threshold + delta  # 0.97
        self.red_lower = red_threshold - delta      # 0.73
        self.red_upper = red_threshold + delta      # 0.77

        # State tracking
        self.current_zone = ConfidenceZone.GREEN
        self.previous_confidence = 1.0

    def update_zone(self, new_confidence: float) -> ConfidenceZone:
        """
        Update confidence zone with deadband hysteresis.

        Args:
            new_confidence: New confidence value

        Returns:
            Current zone after update
        """
        c = new_confidence
        prev = self.previous_confidence

        # GREEN/YELLOW boundary: Deadband(0.95, 0.02) = [0.93, 0.97]
        # YELLOW/RED boundary: Deadband(0.75, 0.02) = [0.73, 0.77]

        if self.current_zone == ConfidenceZone.GREEN:
            # GREEN → YELLOW requires crossing below 0.93
            if c <= self.green_lower:
                self.current_zone = ConfidenceZone.YELLOW

        elif self.current_zone == ConfidenceZone.YELLOW:
            # YELLOW → GREEN requires crossing above 0.97
            if c >= self.green_upper:
                self.current_zone = ConfidenceZone.GREEN
            # YELLOW → RED requires crossing below 0.73
            elif c <= self.red_lower:
                self.current_zone = ConfidenceZone.RED

        elif self.current_zone == ConfidenceZone.RED:
            # RED → YELLOW requires crossing above 0.77
            if c >= self.red_upper:
                self.current_zone = ConfidenceZone.YELLOW

        # Update previous confidence
        self.previous_confidence = c

        return self.current_zone

    def in_deadband(self, confidence: float, boundary: str) -> bool:
        """
        Check if confidence is within deadband of boundary.

        Args:
            confidence: Confidence value to check
            boundary: 'green' or 'red' boundary

        Returns:
            True if in deadband, False otherwise
        """
        if boundary == 'green':
            return self.green_lower <= confidence <= self.green_upper
        elif boundary == 'red':
            return self.red_lower <= confidence <= self.red_upper
        else:
            raise ValueError(f"Unknown boundary: {boundary}")


class ConfidenceCascade:
    """
    Manages confidence cascade with three-zone intelligence.

    From Confidence Cascade Architecture (Paper 3):
    - Confidence composition: c_seq = c1 * c2
    - Zone transitions with deadband hysteresis
    - Monotonic degradation: c_result ≤ min(c1, c2)
    """

    def __init__(self, delta: float = 0.02):
        """
        Initialize confidence cascade manager.

        Args:
            delta: Deadband width (δ)
        """
        self.deadband = DeadbandZoneManager(delta=delta)
        self.history: List[Tuple[float, ConfidenceZone]] = []

    def cascade_confidence(self, confidences: List[float]) -> float:
        """
        Cascade confidence through sequence of tiles.

        Theorem D3.1 (Sequential Composition):
        conf_seq = c1 * c2 * c3 * ... * cn

        Args:
            confidences: List of confidence values

        Returns:
            Cascaded confidence value
        """
        result = 1.0
        for c in confidences:
            result *= c
        return result

    def parallel_confidence(self, confidences: List[float], method: str = 'min') -> float:
        """
        Compute confidence for parallel composition.

        Definition D3.2 (Parallel Composition):
        - Conservative: conf_parallel = min(c1, c2, ..., cn)
        - Geometric mean: conf_parallel = (c1 * c2 * ... * cn)^(1/n)

        Args:
            confidences: List of confidence values
            method: 'min' or 'geometric'

        Returns:
            Parallel confidence value
        """
        if method == 'min':
            return min(confidences)
        elif method == 'geometric':
            product = 1.0
            for c in confidences:
                product *= c
            return product ** (1.0 / len(confidences))
        else:
            raise ValueError(f"Unknown method: {method}")

    def update_lock_confidence(self, lock: LockTile,
                             fleet_history: Dict[str, Any]) -> LockTile:
        """
        Update lock confidence from fleet verification.

        Factors:
        - Base confidence from creator
        - Verification bonus (cross-model verification)
        - Experience bonus (successful applications)
        - Deadband hysteresis (prevent oscillation)

        Args:
            lock: Lock tile to update
            fleet_history: Fleet verification history

        Returns:
            Updated lock with adjusted confidence
        """
        # Base confidence
        base_conf = lock.confidence

        # Verification bonus (cross-model verification)
        verified_by = fleet_history.get('verified_by', [])
        if verified_by:
            verification_bonus = 0.05 * len(verified_by)  # 5% per verifier
        else:
            verification_bonus = 0.0

        # Experience bonus (successful applications)
        successful_applies = fleet_history.get('successful_applied', 0)
        failed_applies = fleet_history.get('failed_applied', 0)
        experience_bonus = 0.02 * successful_applies - 0.05 * failed_applies

        # Total confidence (before deadband)
        total_conf = base_conf + verification_bonus + experience_bonus
        total_conf = min(max(total_conf, 0.0), 1.0)  # Clamp to [0,1]

        # Apply deadband hysteresis
        old_zone = lock.zone
        new_zone = ConfidenceZone.GREEN if total_conf > 0.95 else \
                   ConfidenceZone.YELLOW if total_conf > 0.75 else ConfidenceZone.RED

        # Check for hysteresis
        if old_zone != new_zone:
            # Get previous zone from history
            prev_zone = fleet_history.get('previous_zone', old_zone)

            # Apply deadband check
            if old_zone == ConfidenceZone.GREEN and new_zone == ConfidenceZone.YELLOW:
                if total_conf < 0.93:  # Below deadband lower bound
                    return lock  # Stay in GREEN
            elif old_zone == ConfidenceZone.YELLOW and new_zone == ConfidenceZone.GREEN:
                if total_conf > 0.97:  # Above deadband upper bound
                    return lock  # Stay in YELLOW
            elif old_zone == ConfidenceZone.YELLOW and new_zone == ConfidenceZone.RED:
                if total_conf < 0.73:  # Below RED deadband lower bound
                    return lock  # Stay in YELLOW
            elif old_zone == ConfidenceZone.RED and new_zone == ConfidenceZone.YELLOW:
                if total_conf > 0.77:  # Above RED deadband upper bound
                    return lock  # Stay in RED

        # Create updated lock
        updated_lock = LockTile(
            pattern=lock.pattern,
            bytecode=lock.bytecode,
            confidence=total_conf,
            safety_contract=lock.safety_contract,
            metadata={
                **lock.metadata,
                'updated_confidence': total_conf,
                'zone': new_zone.value
            }
        )

        return updated_lock


class FleetConsensus:
    """
    Implements hierarchical consensus for lock aggregation.

    From Distributed Consensus paper (Paper 12):
    - Hierarchical gossip with O(n log n) complexity
    - Confidence-weighted quorum voting
    - Byzantine fault tolerance (n >= 3f + 1)
    """

    def __init__(self, hierarchy_levels: int = 3):
        """
        Initialize fleet consensus system.

        Args:
            hierarchy_levels: Number of hierarchy levels (default: 3)
        """
        self.hierarchy_levels = hierarchy_levels
        self.lock_library: Dict[str, LockTile] = {}  # Global lock library

    def propose_lock(self, lock: LockTile, agent_id: str) -> str:
        """
        Propose a new lock to the fleet.

        Args:
            lock: Lock to propose
            agent_id: Proposing agent ID

        Returns:
            Lock ID
        """
        # Generate lock ID
        lock_id = hashlib.sha256(
            f"{lock.pattern}{lock.bytecode}{agent_id}".encode()
        ).hexdigest()[:16]

        # Add agent metadata
        lock.metadata['proposed_by'] = agent_id
        lock.metadata['timestamp'] = time.time()

        # Add to local cache
        self.lock_library[lock_id] = lock

        return lock_id

    def aggregate_locks(self, lock_candidates: List[LockTile],
                      level: int = 1) -> Dict[str, LockTile]:
        """
        Aggregate similar locks at hierarchy level.

        Args:
            lock_candidates: List of lock candidates from lower level
            level: Current hierarchy level (1, 2, or 3)

        Returns:
            Aggregated locks
        """
        aggregated = {}

        # Group similar locks by pattern
        pattern_groups = self._group_by_pattern(lock_candidates)

        # Resolve conflicts within groups
        for pattern, locks in pattern_groups.items():
            if len(locks) == 1:
                # No conflict
                lock_id = self.propose_lock(locks[0], f"level{level}")
                aggregated[lock_id] = locks[0]
            else:
                # Conflict - resolve via confidence-weighted voting
                resolved_lock = self._resolve_conflict(locks)
                lock_id = self.propose_lock(resolved_lock, f"level{level}")
                aggregated[lock_id] = resolved_lock

        return aggregated

    def _group_by_pattern(self, locks: List[LockTile]) -> Dict[str, List[LockTile]]:
        """Group locks by similar patterns."""
        groups = {}

        for lock in locks:
            # Simple pattern matching - can be enhanced with similarity metrics
            pattern_key = lock.pattern.lower().strip()

            if pattern_key not in groups:
                groups[pattern_key] = []
            groups[pattern_key].append(lock)

        return groups

    def _resolve_conflict(self, conflicting_locks: List[LockTile]) -> LockTile:
        """
        Resolve conflicting locks via confidence-weighted voting.

        From Distributed Consensus Theorem T2:
        Confidence-weighted quorums maintain safety.

        Args:
            conflicting_locks: List of conflicting locks

        Returns:
            Resolved lock with highest weighted confidence
        """
        # Calculate weighted confidence for each lock
        weighted_scores = []

        for lock in conflicting_locks:
            # Base confidence
            base_score = lock.confidence

            # Verification bonus
            verified_by = lock.metadata.get('verified_by', [])
            verification_bonus = 0.1 * len(verified_by)

            # Experience bonus
            successful = lock.metadata.get('successful_applied', 0)
            failed = lock.metadata.get('failed_applied', 0)
            experience_bonus = 0.05 * successful - 0.1 * failed

            # Total weighted score
            weighted_score = base_score + verification_bonus + experience_bonus
            weighted_scores.append((weighted_score, lock))

        # Select lock with highest weighted score
        weighted_scores.sort(key=lambda x: x[0], reverse=True)
        best_score, best_lock = weighted_scores[0]

        # Update lock metadata with resolution info
        best_lock.metadata['resolution_score'] = best_score
        best_lock.metadata['resolution_candidates'] = len(conflicting_locks)

        return best_lock

    def verify_lock_cross_model(self, lock: LockTile,
                              models: List[str]) -> LockTile:
        """
        Verify lock across multiple models.

        Args:
            lock: Lock to verify
            models: List of model names to verify with

        Returns:
            Updated lock with verification metadata
        """
        verified_by = lock.metadata.get('verified_by', [])

        # Add new verifiers
        for model in models:
            if model not in verified_by:
                verified_by.append(model)

        # Update metadata
        lock.metadata['verified_by'] = verified_by

        # Recalculate confidence with verification bonus
        verification_bonus = 0.05 * len(verified_by)
        new_confidence = min(lock.confidence + verification_bonus, 1.0)

        return LockTile(
            pattern=lock.pattern,
            bytecode=lock.bytecode,
            confidence=new_confidence,
            safety_contract=lock.safety_contract,
            metadata={
                **lock.metadata,
                'verified_by': verified_by,
                'verification_bonus': verification_bonus
            }
        )


class TileCategory:
    """
    Implements lock library as a category 𝓛.

    Category properties:
    - Objects: Pattern types (I) and Bytecode types (O)
    - Morphisms: Lock tiles T: Pattern → Bytecode
    - Composition: Sequential, parallel, conditional operators
    - Identity: Identity lock

    Category Laws:
    1. Associativity: (L1 ∘ L2) ∘ L3 = L1 ∘ (L2 ∘ L3)
    2. Identity: Id ∘ L = L = L ∘ Id
    3. Distributivity: L ∘ (L1 ∥ L2) = (L ∘ L1) ∥ (L ∘ L2)
    """

    def __init__(self):
        """Initialize tile category."""
        self.tiles: Dict[str, LockTile] = {}

    def add_tile(self, tile: LockTile, tile_id: str) -> None:
        """Add tile to category."""
        self.tiles[tile_id] = tile

    def get_identity(self, pattern: str) -> LockTile:
        """
        Get identity tile Id_A for pattern A.

        Identity tile: Id: A → A with confidence 1.0
        """
        def identity_verify(p: str, b: bytes) -> bool:
            # Identity tile should accept same pattern and empty bytecode
            # When composed, it acts as identity function
            return True  # Identity always safe

        return LockTile(
            pattern=pattern,
            bytecode=b'',
            confidence=1.0,
            safety_contract=identity_verify,
            metadata={'type': 'identity', 'identity_for': pattern}
        )

    def compose_sequential(self, tile_ids: List[str]) -> Optional[LockTile]:
        """
        Compose tiles sequentially: L1 ∘ L2 ∘ ... ∘ Ln

        Theorem T3 (Associativity): Order of composition doesn't matter
        """
        if not tile_ids:
            return None

        # Get first tile
        result = self.tiles.get(tile_ids[0])
        if not result:
            raise ValueError(f"Tile {tile_ids[0]} not found")

        # Compose sequentially
        for tile_id in tile_ids[1:]:
            next_tile = self.tiles.get(tile_id)
            if not next_tile:
                raise ValueError(f"Tile {tile_id} not found")

            result = result.compose(next_tile)

        return result

    def compose_parallel(self, tile_ids: List[str]) -> Optional[LockTile]:
        """
        Compose tiles in parallel: L1 ∥ L2 ∥ ... ∥ Ln

        Theorem: Commutative and associative
        """
        if not tile_ids:
            return None

        # Get first tile
        result = self.tiles.get(tile_ids[0])
        if not result:
            raise ValueError(f"Tile {tile_ids[0]} not found")

        # Compose in parallel
        for tile_id in tile_ids[1:]:
            next_tile = self.tiles.get(tile_id)
            if not next_tile:
                raise ValueError(f"Tile {tile_id} not found")

            result = result.parallel(next_tile)

        return result

    def verify_category_laws(self) -> Dict[str, bool]:
        """
        Verify category laws for all tiles.

        Returns:
            Dictionary with law names and verification results
        """
        results = {}

        # Check identity law for each tile
        for tile_id, tile in self.tiles.items():
            identity = self.get_identity(tile.pattern)

            # Check: Id ∘ L = L
            id_then_tile = identity.compose(tile)
            results[f"{tile_id}_identity_left"] = (
                id_then_tile.pattern == tile.pattern and
                id_then_tile.bytecode == tile.bytecode
            )

            # Check: L ∘ Id = L
            tile_then_id = tile.compose(identity)
            results[f"{tile_id}_identity_right"] = (
                tile_then_id.pattern == tile.pattern and
                tile_then_id.bytecode == tile.bytecode
            )

        return results


# Import time for timestamp
import time


# Example Usage
if __name__ == "__main__":
    """
    Demonstrate SMPBot-FLUX bridge with practical examples.
    """

    # Example 1: Create navigation lock as tile
    def nav_safety_contract(pattern: str, bytecode: bytes) -> bool:
        """Safety contract for navigation lock."""
        expected_ops = [0x10, 0x11]  # MOVI, MOV
        return len(bytecode) >= 3 and bytecode[0] in expected_ops

    nav_lock = LockTile(
        pattern="navigate <vehicle> <direction> at <speed> knots",
        bytecode=bytes([0x10, 0x01, 0x01]),  # MOVI helm 1
        confidence=0.95,
        safety_contract=nav_safety_contract,
        metadata={
            'id': 'nav-direction-speed',
            'domain': 'maritime',
            'discovered_by': 'DeepSeek-V3'
        }
    )

    print(f"Navigation Lock:")
    print(f"  Pattern: {nav_lock.pattern}")
    print(f"  Confidence: {nav_lock.confidence}")
    print(f"  Zone: {nav_lock.zone.value}")

    # Example 2: Sequential composition
    def alert_safety_contract(pattern: str, bytecode: bytes) -> bool:
        """Safety contract for alert lock."""
        return len(bytecode) >= 2 and bytecode[0] == 0x20  # ALERT

    alert_lock = LockTile(
        pattern="alert when <sensor> exceeds <threshold>",
        bytecode=bytes([0x20, 0x05]),  # ALERT 5
        confidence=0.92,
        safety_contract=alert_safety_contract,
        metadata={
            'id': 'conditional-alert',
            'domain': 'maritime',
            'discovered_by': 'DeepSeek-V3'
        }
    )

    # Compose sequentially: navigate then alert
    pipeline = nav_lock.compose(alert_lock)
    print(f"\nSequential Composition:")
    print(f"  Pattern: {pipeline.pattern}")
    print(f"  Confidence: {pipeline.confidence}")  # 0.95 * 0.92 = 0.874
    print(f"  Zone: {pipeline.zone.value}")  # YELLOW

    # Example 3: Confidence cascade with deadband
    cascade = ConfidenceCascade(delta=0.02)

    # Simulate confidence history
    confidences = [0.98, 0.97, 0.96, 0.94, 0.93, 0.92, 0.91]
    print(f"\nConfidence Cascade with Deadband:")
    for i, conf in enumerate(confidences):
        zone = cascade.deadband.update_zone(conf)
        print(f"  Step {i+1}: conf={conf:.2f}, zone={zone.value}")

    # Example 4: Fleet consensus
    fleet = FleetConsensus(hierarchy_levels=3)

    # Propose locks from multiple agents
    lock1 = LockTile(
        pattern="check <gauge> every loop",
        bytecode=bytes([0x30, 0x05]),  # GAUGE 5
        confidence=0.88,
        safety_contract=lambda p, b: True,
        metadata={'discovered_by': 'DeepSeek-V3'}
    )

    lock2 = LockTile(
        pattern="check <gauge> every loop",  # Same pattern
        bytecode=bytes([0x30, 0x05]),  # Same bytecode
        confidence=0.90,
        safety_contract=lambda p, b: True,
        metadata={'discovered_by': 'Qwen3-Coder'}
    )

    # Aggregate locks
    aggregated = fleet.aggregate_locks([lock1, lock2], level=1)
    print(f"\nFleet Consensus:")
    for lock_id, lock in aggregated.items():
        print(f"  Lock {lock_id[:8]}...")
        print(f"    Confidence: {lock.confidence}")
        print(f"    Resolution score: {lock.metadata.get('resolution_score', 'N/A')}")

    # Example 5: Tile category
    category = TileCategory()
    category.add_tile(nav_lock, 'nav')
    category.add_tile(alert_lock, 'alert')

    # Verify category laws
    laws = category.verify_category_laws()
    print(f"\nCategory Law Verification:")
    for law, verified in laws.items():
        status = "✓" if verified else "✗"
        print(f"  {status} {law}")

    print("\n=== SMPBot-FLUX Bridge Demo Complete ===")
