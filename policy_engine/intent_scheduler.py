"""
Asynchronous intent expiration scheduler.
Tracks temporary user priority requests and automatically reverts policy
once the requested duration has elapsed.
"""
import time
import threading
from typing import Callable, Optional

class IntentScheduler:
    def __init__(self, default_duration_sec: int = 1200):
        self.default_duration_sec = default_duration_sec
        self.active_intent = None
        self._timer = None
        self._lock = threading.Lock()
        self.history = []

    def schedule_intent(
        self,
        traffic_class: str,
        action: str = "prioritize",
        duration_sec: Optional[int] = None,
        on_expire: Optional[Callable] = None
    ) -> dict:
        """
        Register a temporary user intent and set an auto-expiry timer.
        """
        if duration_sec is None or duration_sec <= 0:
            duration_sec = self.default_duration_sec

        now = time.time()
        intent_record = {
            "traffic_class": traffic_class,
            "action": action,
            "duration_sec": duration_sec,
            "start_time": now,
            "expires_at": now + duration_sec,
            "status": "active"
        }

        with self._lock:
            # Cancel any previously running timer
            if self._timer and self._timer.is_alive():
                self._timer.cancel()

            self.active_intent = intent_record
            self.history.append(dict(intent_record))

            def _expire():
                with self._lock:
                    if self.active_intent and self.active_intent.get("expires_at", 0) <= time.time():
                        print(f"[INTENT SCHEDULER] Intent expired for {traffic_class}. Reverting to default.")
                        self.active_intent["status"] = "expired"
                        expired_copy = dict(self.active_intent)
                        self.active_intent = None
                        if on_expire:
                            try:
                                on_expire(expired_copy)
                            except Exception as e:
                                print(f"[ERROR] Expiration callback failed: {e}")

            self._timer = threading.Timer(duration_sec, _expire)
            self._timer.daemon = True
            self._timer.start()

        return dict(intent_record)

    def get_active_intent(self) -> Optional[dict]:
        """Return active intent if not expired."""
        with self._lock:
            if not self.active_intent:
                return None
            if time.time() >= self.active_intent.get("expires_at", 0):
                self.active_intent = None
                return None
            res = dict(self.active_intent)
            res["remaining_sec"] = max(0, int(res["expires_at"] - time.time()))
            return res

    def is_active(self, traffic_class: Optional[str] = None) -> bool:
        """Check if an intent is currently active (optionally for a specific class)."""
        intent = self.get_active_intent()
        if not intent:
            return False
        if traffic_class:
            return intent.get("traffic_class") == traffic_class
        return True

    def clear(self, on_cancel: Optional[Callable] = None):
        """Manually cancel active intent and revert to baseline."""
        with self._lock:
            if self._timer and self._timer.is_alive():
                self._timer.cancel()
            if self.active_intent:
                self.active_intent["status"] = "cancelled"
                self.active_intent = None
                if on_cancel:
                    try:
                        on_cancel()
                    except Exception as e:
                        print(f"[ERROR] Cancel callback failed: {e}")

    def get_history(self):
        with self._lock:
            return list(self.history)
