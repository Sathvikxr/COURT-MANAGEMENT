"""
NyayaDesk AI Rate Limiting & Cost Control Layer
Enforces per-user, global, and daily cost caps alongside an administrative kill switch.
"""

import os
import time
from collections import deque
from datetime import datetime
from typing import Dict, Optional, Tuple
from app.models import db, AILog, AISetting

class AIRateLimiter:
    """Manages request throttling, cost guardrails, and administrative kill switch."""

    def __init__(self):
        # In-memory sliding window: timestamp deques
        self._user_windows: Dict[int, deque] = {}
        self._global_window: deque = deque()
        self._user_per_min_limit = int(os.environ.get('AI_USER_RATE_LIMIT', 20))
        self._global_per_min_limit = int(os.environ.get('AI_GLOBAL_RATE_LIMIT', 100))

    def is_ai_disabled(self) -> bool:
        """Checks if the administrative kill switch is active."""
        # Check environment override first
        env_flag = os.environ.get('AI_KILL_SWITCH', '').strip().lower()
        if env_flag in ['true', '1', 'yes']:
            return True

        # Check DB setting
        try:
            setting = AISetting.query.filter_by(key='ai_disabled').first()
            if setting and setting.value.strip().lower() in ['true', '1', 'yes']:
                return True
        except Exception:
            pass

        return False

    def set_ai_disabled(self, disabled: bool, user_id: Optional[int] = None) -> bool:
        """Toggles the administrative kill switch."""
        try:
            setting = AISetting.query.filter_by(key='ai_disabled').first()
            val_str = 'true' if disabled else 'false'
            if setting:
                setting.value = val_str
                setting.updated_by = user_id
                setting.updated_at = datetime.utcnow()
            else:
                setting = AISetting(key='ai_disabled', value=val_str, updated_by=user_id)
                db.session.add(setting)
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    def get_daily_cap(self) -> int:
        """Returns the configured daily maximum AI request cap."""
        try:
            setting = AISetting.query.filter_by(key='daily_request_cap').first()
            if setting and setting.value.isdigit():
                return int(setting.value)
        except Exception:
            pass
        return int(os.environ.get('AI_DAILY_REQUEST_CAP', 500))

    def set_daily_cap(self, cap: int, user_id: Optional[int] = None) -> bool:
        """Updates the daily request cap."""
        try:
            setting = AISetting.query.filter_by(key='daily_request_cap').first()
            if setting:
                setting.value = str(cap)
                setting.updated_by = user_id
                setting.updated_at = datetime.utcnow()
            else:
                setting = AISetting(key='daily_request_cap', value=str(cap), updated_by=user_id)
                db.session.add(setting)
            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    def get_today_request_count(self) -> int:
        """Counts total AI requests executed today (since midnight UTC)."""
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            return AILog.query.filter(AILog.created_at >= today_start).count()
        except Exception:
            return 0

    def check_limits(self, user_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Validates whether request can proceed against:
        1. Administrative kill switch
        2. Daily cost/quota cap
        3. Global sliding window (1 min)
        4. Per-user sliding window (1 min)
        Returns (is_allowed, error_reason).
        """
        # 1. Kill Switch
        if self.is_ai_disabled():
            return False, "AI operations are temporarily disabled by Court Administration."

        # 2. Daily Request Cap
        daily_cap = self.get_daily_cap()
        today_count = self.get_today_request_count()
        if today_count >= daily_cap:
            return False, f"Daily AI request quota reached ({today_count}/{daily_cap}). Falling back to offline synthesis."

        now = time.time()
        one_min_ago = now - 60.0

        # 3. Global Sliding Window
        while self._global_window and self._global_window[0] < one_min_ago:
            self._global_window.popleft()

        if len(self._global_window) >= self._global_per_min_limit:
            return False, "Global AI throughput limit exceeded. Please retry in a few seconds."

        # 4. Per-User Sliding Window
        if user_id:
            if user_id not in self._user_windows:
                self._user_windows[user_id] = deque()
            user_deque = self._user_windows[user_id]
            while user_deque and user_deque[0] < one_min_ago:
                user_deque.popleft()

            if len(user_deque) >= self._user_per_min_limit:
                return False, f"User rate limit reached ({self._user_per_min_limit} req/min). Please slow down."

        # Record this request in windows
        self._global_window.append(now)
        if user_id:
            self._user_windows[user_id].append(now)

        return True, None
