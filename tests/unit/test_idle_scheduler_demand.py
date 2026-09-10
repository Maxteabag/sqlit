"""Scheduler lifecycle: no polling when empty, and no lost work on restart."""
from unittest.mock import Mock

from sqlit.domains.shell.app.idle_scheduler import IdleScheduler, Priority


class ManualTimer:
    def __init__(self, callback):
        self.callback = callback
        self.stopped = False

    def stop(self):
        self.stopped = True


class TimerApp:
    def __init__(self):
        self.timers = []
        self.log = Mock()

    def set_timer(self, _delay, callback):
        timer = ManualTimer(callback)
        self.timers.append(timer)
        return timer

    def fire(self):
        timer = next(t for t in self.timers if not t.stopped)
        timer.stopped = True
        timer.callback()

    @property
    def pending(self):
        return sum(not t.stopped for t in self.timers)


def test_empty_scheduler_sleeps_and_wakes_for_new_work():
    app = TimerApp()
    scheduler = IdleScheduler(app, idle_threshold_ms=0)
    scheduler.start()
    assert app.pending == 0
    called = []
    scheduler.request_idle_callback(lambda: called.append(1))
    scheduler.request_idle_callback(lambda: called.append(2))
    assert app.pending == 1
    app.fire()
    assert called == [1, 2]
    assert app.pending == 0
    scheduler.request_idle_callback(lambda: called.append(3))
    app.fire()
    assert called == [1, 2, 3]
    assert app.pending == 0


def test_pause_resume_and_stop_start_preserve_pending_jobs():
    app = TimerApp()
    scheduler = IdleScheduler(app, idle_threshold_ms=0)
    called = Mock()
    scheduler.start()
    scheduler.request_idle_callback(called)
    scheduler.pause()
    assert app.pending == 0
    scheduler.resume()
    assert app.pending == 1
    scheduler.stop()
    assert app.pending == 0
    scheduler.start()
    app.fire()
    called.assert_called_once()
    assert app.pending == 0


def test_cancel_last_job_disarms_timer_and_keeps_other_named_jobs():
    app = TimerApp()
    scheduler = IdleScheduler(app, idle_threshold_ms=0)
    scheduler.start()
    called = Mock()
    scheduler.request_idle_callback(called, name="cancel")
    scheduler.request_idle_callback(called, name="keep")
    assert scheduler.cancel_all("cancel") == 1
    assert app.pending == 1
    assert scheduler.cancel_all("keep") == 1
    assert app.pending == 0
    called.assert_not_called()


def test_activity_defers_jobs_and_reentrant_request_does_not_duplicate_timers(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("sqlit.domains.shell.app.idle_scheduler.time.monotonic", lambda: now[0])
    app = TimerApp()
    scheduler = IdleScheduler(app, idle_threshold_ms=500)
    called = []
    scheduler.start()
    scheduler.request_idle_callback(lambda: scheduler.request_idle_callback(lambda: called.append("later")))
    scheduler.request_idle_callback(lambda: called.append("first"), priority=Priority.HIGH)
    app.fire()
    assert called == [] and app.pending == 1
    now[0] += 1
    app.fire()
    assert called == ["first", "later"]
    assert app.pending == 0
