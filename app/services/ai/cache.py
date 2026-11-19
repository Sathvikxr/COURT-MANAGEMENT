"""
NyayaDesk AI Response Caching Layer
Stores and retrieves prompt responses in the SQLite ai_response_cache table with TTL.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from app.models import db, AICache

def compute_cache_key(feature: str, prompt: str, system_instruction: Optional[str] = None, model: str = "") -> str:
    """
    Computes a deterministic SHA-256 hash identifying the prompt and context.
    """
    hasher = hashlib.sha256()
    hasher.update(feature.strip().encode('utf-8'))
    hasher.update((system_instruction or "").strip().encode('utf-8'))
    hasher.update(prompt.strip().encode('utf-8'))
    hasher.update(model.strip().encode('utf-8'))
    return hasher.hexdigest()

get_prompt_hash = compute_cache_key


class AICacheManager:
    """Handles response caching with TTL to eliminate redundant queries."""

    @staticmethod
    def get(cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves cached response if valid and unexpired.
        Returns deserialized JSON dict or None.
        """
        try:
            cached = AICache.query.filter_by(cache_key=cache_key).first()
            if not cached:
                return None

            now = datetime.utcnow()
            if cached.expires_at < now:
                # Expired - remove from DB
                db.session.delete(cached)
                db.session.commit()
                return None

            return json.loads(cached.response_json)
        except Exception:
            return None

    @staticmethod
    def set(
        cache_key: str,
        feature: str,
        provider: str,
        model: str,
        response_data: Dict[str, Any],
        ttl_seconds: int = 3600
    ) -> bool:
        """
        Stores serialized response in the SQLite cache.
        """
        try:
            now = datetime.utcnow()
            expires_at = now + timedelta(seconds=ttl_seconds)
            serialized = json.dumps(response_data)

            existing = AICache.query.filter_by(cache_key=cache_key).first()
            if existing:
                existing.response_json = serialized
                existing.provider = provider
                existing.model = model
                existing.expires_at = expires_at
                existing.created_at = now
            else:
                entry = AICache(
                    cache_key=cache_key,
                    feature=feature,
                    provider=provider,
                    model=model,
                    response_json=serialized,
                    expires_at=expires_at,
                    created_at=now
                )
                db.session.add(entry)

            db.session.commit()
            return True
        except Exception:
            db.session.rollback()
            return False

    @staticmethod
    def clear_expired() -> int:
        """Removes all expired cache rows."""
        try:
            now = datetime.utcnow()
            deleted = AICache.query.filter(AICache.expires_at < now).delete()
            db.session.commit()
            return deleted
        except Exception:
            db.session.rollback()
            return 0
