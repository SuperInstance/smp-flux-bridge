"""Tests for DeadbandZoneManager hysteresis logic."""

import pytest
from lock_tile import DeadbandZoneManager, ConfidenceZone


class TestDeadbandInit:
    """Tests for DeadbandZoneManager initialization."""

    def test_default_delta(self):
        dm = DeadbandZoneManager()
        assert dm.delta == 0.02

    def test_custom_delta(self):
        dm = DeadbandZoneManager(delta=0.05)
        assert dm.delta == 0.05

    def test_default_boundaries(self):
        """Floating-point: 0.95 - 0.02 != 0.93 exactly."""
        dm = DeadbandZoneManager()
        assert dm.green_lower == pytest.approx(0.93)
        assert dm.green_upper == pytest.approx(0.97)
        assert dm.red_lower == pytest.approx(0.73)
        assert dm.red_upper == pytest.approx(0.77)

    def test_custom_boundaries(self):
        dm = DeadbandZoneManager(green_threshold=0.90, red_threshold=0.70)
        assert dm.green_lower == pytest.approx(0.88)
        assert dm.green_upper == pytest.approx(0.92)
        assert dm.red_lower == pytest.approx(0.68)
        assert dm.red_upper == pytest.approx(0.72)

    def test_initial_zone_is_green(self):
        dm = DeadbandZoneManager()
        assert dm.current_zone == ConfidenceZone.GREEN


class TestDeadbandGreenZone:
    """Tests for zone transitions starting from GREEN."""

    def test_stay_green_high_confidence(self):
        dm = DeadbandZoneManager()
        assert dm.update_zone(0.99) == ConfidenceZone.GREEN

    def test_stay_green_in_deadband(self):
        """Confidence 0.94 is in deadband [0.93, 0.97] - should stay GREEN."""
        dm = DeadbandZoneManager()
        assert dm.update_zone(0.94) == ConfidenceZone.GREEN

    def test_green_to_yellow_below_deadband(self):
        """0.92 is clearly below green_lower (0.93), should transition."""
        dm = DeadbandZoneManager()
        assert dm.update_zone(0.92) == ConfidenceZone.YELLOW

    def test_green_to_yellow_far_below(self):
        dm = DeadbandZoneManager()
        assert dm.update_zone(0.85) == ConfidenceZone.YELLOW

    def test_green_to_red_via_yellow(self):
        dm = DeadbandZoneManager()
        assert dm.update_zone(0.50) == ConfidenceZone.YELLOW  # First stops at YELLOW
        assert dm.update_zone(0.70) == ConfidenceZone.RED


class TestDeadbandYellowZone:
    """Tests for zone transitions from YELLOW."""

    def _yellow_manager(self):
        dm = DeadbandZoneManager()
        dm.update_zone(0.90)  # Force to YELLOW
        return dm

    def test_stay_yellow_mid(self):
        dm = self._yellow_manager()
        assert dm.update_zone(0.85) == ConfidenceZone.YELLOW

    def test_stay_yellow_in_green_deadband(self):
        """At 0.96, still in deadband [0.93, 0.97], stay YELLOW."""
        dm = self._yellow_manager()
        assert dm.update_zone(0.96) == ConfidenceZone.YELLOW

    def test_yellow_to_green_above_deadband(self):
        """At 0.98, above green_upper (0.97), transition to GREEN."""
        dm = self._yellow_manager()
        assert dm.update_zone(0.98) == ConfidenceZone.GREEN

    def test_stay_yellow_in_red_deadband(self):
        """At 0.74, in deadband [0.73, 0.77], stay YELLOW."""
        dm = self._yellow_manager()
        assert dm.update_zone(0.74) == ConfidenceZone.YELLOW

    def test_yellow_to_red_below_deadband(self):
        """At 0.72, below red_lower (0.73), transition to RED."""
        dm = self._yellow_manager()
        assert dm.update_zone(0.72) == ConfidenceZone.RED

    def test_yellow_to_red_far_below(self):
        dm = self._yellow_manager()
        assert dm.update_zone(0.50) == ConfidenceZone.RED


class TestDeadbandRedZone:
    """Tests for zone transitions from RED."""

    def _red_manager(self):
        dm = DeadbandZoneManager()
        dm.update_zone(0.90)  # -> YELLOW
        dm.update_zone(0.50)  # -> RED
        return dm

    def test_stay_red_low(self):
        dm = self._red_manager()
        assert dm.update_zone(0.20) == ConfidenceZone.RED

    def test_stay_red_in_deadband(self):
        """At 0.75, in deadband [0.73, 0.77], stay RED."""
        dm = self._red_manager()
        assert dm.update_zone(0.75) == ConfidenceZone.RED

    def test_red_to_yellow_above_deadband(self):
        """At 0.78, above red_upper (0.77), transition to YELLOW."""
        dm = self._red_manager()
        assert dm.update_zone(0.78) == ConfidenceZone.YELLOW

    def test_red_to_yellow_far_above(self):
        dm = self._red_manager()
        assert dm.update_zone(0.90) == ConfidenceZone.YELLOW


class TestDeadbandOscillationPrevention:
    """Tests verifying that deadband prevents zone oscillation."""

    def test_no_oscillation_around_green_yellow(self):
        """Confidence oscillating around 0.95 should not cause rapid zone changes."""
        dm = DeadbandZoneManager()
        zones = []
        values = [0.96, 0.94, 0.96, 0.94, 0.96, 0.94]
        for v in values:
            zones.append(dm.update_zone(v))
        # Should stay GREEN the entire time (within deadband)
        assert all(z == ConfidenceZone.GREEN for z in zones)

    def test_no_oscillation_around_yellow_red(self):
        """Confidence oscillating around 0.75 should not cause rapid zone changes."""
        dm = DeadbandZoneManager()
        dm.update_zone(0.80)  # -> YELLOW
        zones = []
        values = [0.76, 0.74, 0.76, 0.74, 0.76, 0.74]
        for v in values:
            zones.append(dm.update_zone(v))
        # Should stay YELLOW the entire time
        assert all(z == ConfidenceZone.YELLOW for z in zones)

    def test_previous_confidence_tracking(self):
        dm = DeadbandZoneManager()
        dm.update_zone(0.98)
        assert dm.previous_confidence == 0.98
        dm.update_zone(0.85)
        assert dm.previous_confidence == 0.85


class TestInDeadband:
    """Tests for the in_deadband method."""

    def test_in_green_deadband_center(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.95, 'green') is True

    def test_in_green_deadband_lower(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.93, 'green') is True

    def test_in_green_deadband_upper(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.97, 'green') is True

    def test_outside_green_deadband_below(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.92, 'green') is False

    def test_outside_green_deadband_above(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.98, 'green') is False

    def test_in_red_deadband_center(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.75, 'red') is True

    def test_in_red_deadband_lower(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.73, 'red') is True

    def test_in_red_deadband_upper(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.77, 'red') is True

    def test_outside_red_deadband_below(self):
        dm = DeadbandZoneManager()
        assert dm.in_deadband(0.72, 'red') is False

    def test_unknown_boundary_raises(self):
        dm = DeadbandZoneManager()
        with pytest.raises(ValueError, match="Unknown boundary"):
            dm.in_deadband(0.95, 'orange')
