"""
Simple keyword-based fallback, agar Laya available na ho.
Yeh ek deterministic, hamesha-kaam-karne-wala backup hai.
"""
import re

def parse_intent_fallback(text: str) -> dict:
    text_lower = text.lower()

    if "video" in text_lower or "call" in text_lower:
        traffic_class = "video_conference"
    elif "game" in text_lower or "gaming" in text_lower:
        traffic_class = "gaming"
    elif "download" in text_lower or "bulk" in text_lower:
        traffic_class = "bulk_download"
    else:
        traffic_class = "other"

    if "priority" in text_lower or "prioritize" in text_lower:
        action = "prioritize"
    elif "slow" in text_lower or "deprioritize" in text_lower or "limit" in text_lower:
        action = "deprioritize"
    elif "normal" in text_lower or "reset" in text_lower:
        action = "reset"
    else:
        action = "none"

    duration_match = re.search(r"(\d+)\s*min", text_lower)
    duration_sec = int(duration_match.group(1)) * 60 if duration_match else 1200

    return {
        "action": action,
        "traffic_class": traffic_class,
        "is_temporary": "min" in text_lower or "next" in text_lower,
        "duration_sec": duration_sec,
        "needs_confirmation": True,  # fallback hamesha confirmation maangta hai (safety)
        "overall_confidence": 0.5,
        "note": "parsed via fallback rules, not Laya"
    }

if __name__ == "__main__":
    import json
    print(json.dumps(parse_intent_fallback("mujhe 20 min video call priority chahiye"), indent=2))
