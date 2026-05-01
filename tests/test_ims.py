import asyncio
import pytest
from main import RCAPayload, WorkItemStateMachine, AsyncRateLimiter, get_severity_label, get_alert_strategy, P0AlertStrategy, P1AlertStrategy, P2AlertStrategy

class TestRCAValidation:
    def _valid_rca(self, **overrides):
        data = dict(start_time="2025-01-01T10:00:00", end_time="2025-01-01T11:00:00", root_cause_category="Infrastructure", fix_applied="Restarted service.", prevention_steps="Add auto-scaling.")
        data.update(overrides)
        return RCAPayload(**data)

    def test_valid_rca_passes(self):
        self._valid_rca().validate_complete()

    def test_missing_fix_applied_raises(self):
        with pytest.raises(ValueError, match="fix_applied"):
            self._valid_rca(fix_applied="").validate_complete()

    def test_missing_prevention_steps_raises(self):
        with pytest.raises(ValueError, match="prevention_steps"):
            self._valid_rca(prevention_steps="").validate_complete()

    def test_missing_root_cause_category_raises(self):
        with pytest.raises(ValueError, match="root_cause_category"):
            self._valid_rca(root_cause_category="").validate_complete()

    def test_missing_start_time_raises(self):
        with pytest.raises(ValueError, match="start_time"):
            self._valid_rca(start_time="").validate_complete()

    def test_whitespace_only_field_raises(self):
        with pytest.raises(ValueError, match="fix_applied"):
            self._valid_rca(fix_applied="   ").validate_complete()

class TestWorkItemStateMachine:
    def test_open_to_investigating(self):
        sm = WorkItemStateMachine("OPEN")
        assert sm.transition("INVESTIGATING") == "OPEN"
        assert sm.status == "INVESTIGATING"

    def test_investigating_to_resolved(self):
        sm = WorkItemStateMachine("INVESTIGATING")
        sm.transition("RESOLVED")
        assert sm.status == "RESOLVED"

    def test_resolved_to_closed(self):
        sm = WorkItemStateMachine("RESOLVED")
        sm.transition("CLOSED")
        assert sm.status == "CLOSED"

    def test_cannot_skip_states(self):
        with pytest.raises(ValueError, match="Invalid transition"):
            WorkItemStateMachine("OPEN").transition("RESOLVED")

    def test_cannot_reopen_closed(self):
        with pytest.raises(ValueError):
            WorkItemStateMachine("CLOSED").transition("OPEN")

    def test_can_transition_check(self):
        sm = WorkItemStateMachine("OPEN")
        assert sm.can_transition("INVESTIGATING") is True
        assert sm.can_transition("RESOLVED") is False

class TestAlertStrategy:
    def test_rdbms_is_p0(self):
        assert get_severity_label("RDBMS_01") == "P0"

    def test_cache_is_p2(self):
        assert get_severity_label("CACHE_CLUSTER_01") == "P2"

    def test_queue_is_p1(self):
        assert get_severity_label("QUEUE_01") == "P1"

    def test_rdbms_strategy_type(self):
        assert isinstance(get_alert_strategy("RDBMS_PRIMARY"), P0AlertStrategy)

    def test_cache_strategy_type(self):
        assert isinstance(get_alert_strategy("CACHE_CLUSTER_01"), P2AlertStrategy)

    def test_p0_escalates(self):
        assert P0AlertStrategy().alert(1, "RDBMS_01")["escalate"] is True

    def test_p2_no_escalate(self):
        assert P2AlertStrategy().alert(1, "CACHE_01")["escalate"] is False

class TestRateLimiter:
    def test_allows_under_limit(self):
        limiter = AsyncRateLimiter(max_requests=5, window=10)
        loop = asyncio.get_event_loop()
        for _ in range(5):
            assert loop.run_until_complete(limiter.is_limited()) is False

    def test_blocks_over_limit(self):
        limiter = AsyncRateLimiter(max_requests=3, window=10)
        loop = asyncio.get_event_loop()
        for _ in range(3):
            loop.run_until_complete(limiter.is_limited())
        assert loop.run_until_complete(limiter.is_limited()) is True
