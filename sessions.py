from __future__ import annotations

from datetime import datetime, timezone


_last_session = None


def get_current_session() -> dict:
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 8:
        return {"emoji": "🟦", "name": "Asia", "best_action": "Accumulation only"}
    if 8 <= hour < 16:
        return {"emoji": "🟨", "name": "London", "best_action": "Good for entries"}
    return {"emoji": "🟥", "name": "New York", "best_action": "Good for entries"}


def format_session_message(side: str = "") -> str:
    session = get_current_session()
    return f"{session['emoji']} Session: {session['name']}\nBest action: {session['best_action']}"


def check_session_changed():
    global _last_session
    current = get_current_session()["name"]
    if _last_session is None:
        _last_session = current
        return None
    if current != _last_session:
        _last_session = current
        return current
    return None


def format_session_alert(new_session) -> str:
    return f"Session changed: {new_session}"

def is_tradeable_session():
    from datetime import datetime, timezone
    hour = datetime.now(timezone.utc).hour
    return 7 <= hour < 22

