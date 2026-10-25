from tutor import analytics_bridge
from tutor.models import Learner

A = Learner("course-1", "learner-a", "S-aaaaaaaaaa")
B = Learner("course-1", "learner-b", "S-bbbbbbbbbb")


def setup_function():
    analytics_bridge.clear_cache()


def counting_loader(monkeypatch):
    calls = []

    def fake_load(writer, reader, learner, threshold):
        calls.append(learner.learner_id)
        return [f"weak-{learner.learner_id}"]

    monkeypatch.setattr(analytics_bridge, "_load", fake_load)
    return calls


def test_repeat_turns_reuse_the_learners_weak_outcomes(monkeypatch):
    calls = counting_loader(monkeypatch)
    clock = iter([0, 10, 20]).__next__
    assert analytics_bridge.weak_outcomes(None, None, A, now=clock) == ["weak-learner-a"]
    assert analytics_bridge.weak_outcomes(None, None, A, now=clock) == ["weak-learner-a"]
    assert calls == ["learner-a"]


def test_cache_is_per_learner_and_expires(monkeypatch):
    calls = counting_loader(monkeypatch)
    analytics_bridge.weak_outcomes(None, None, A, now=lambda: 0)
    assert analytics_bridge.weak_outcomes(None, None, B, now=lambda: 1) == ["weak-learner-b"]
    analytics_bridge.weak_outcomes(None, None, A, now=lambda: analytics_bridge.TTL_SECONDS + 1)
    assert calls == ["learner-a", "learner-b", "learner-a"]


def test_failures_are_not_cached(monkeypatch):
    attempts = []

    def flaky(writer, reader, learner, threshold):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("analytics down")
        return ["ok"]

    monkeypatch.setattr(analytics_bridge, "_load", flaky)
    try:
        analytics_bridge.weak_outcomes(None, None, A, now=lambda: 0)
    except RuntimeError:
        pass
    assert analytics_bridge.weak_outcomes(None, None, A, now=lambda: 1) == ["ok"]
