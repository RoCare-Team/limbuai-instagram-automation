from .db import get_conn


def find_matching_reply(text: str, table: str) -> str | None:
    """Check an incoming comment/DM text against active rules and return the reply if matched."""
    if not text:
        return None
    text_lower = text.lower()
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT keyword, reply_text, match_type FROM {table} WHERE is_active = 1"
        ).fetchall()
    for row in rows:
        keyword = row["keyword"].lower().strip()
        if row["match_type"] == "exact" and text_lower.strip() == keyword:
            return row["reply_text"]
        if row["match_type"] == "contains" and keyword in text_lower:
            return row["reply_text"]
    return None
