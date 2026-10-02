"""
Natural-language -> structured QoS intent. 
Laya ko use karte hain (non-generative, typed decisions), 
confidence-gated — low confidence pe 'needs_confirmation' flag.
"""

CONFIDENCE_THRESHOLD = 0.70

QUESTIONS = {
    "intent_action": {
        "type": "choice",
        "instructions": "What QoS action does the user want?",
        "criteria": {
            "prioritize": "user wants to boost priority of a traffic class",
            "deprioritize": "user wants to reduce priority of a traffic class",
            "reset": "user wants to reset to default policy",
            "none": "no clear QoS action requested"
        }
    },
    "traffic_class": {
        "type": "choice",
        "instructions": "Which traffic class is being referred to?",
        "criteria": {
            "video_conference": "video calls, meetings",
            "gaming": "online games, low latency",
            "bulk_download": "large downloads, updates, backups",
            "other": "anything else"
        }
    },
    "is_temporary": {
        "type": "noul",
        "instructions": "Is this a temporary/time-bound request (not permanent)?"
    }
}

_router = None

def _get_router():
    global _router
    if _router is None:
        from laya import Router
        _router = Router()
    return _router

def parse_intent(text: str) -> dict:
    """
    Returns structured intent dict with confidence scores.
    Low confidence -> flagged for manual confirmation.
    """
    router = _get_router()
    result = router.predict(text, QUESTIONS)

    action = result["answers"]["intent_action"]
    traffic = result["answers"]["traffic_class"]
    temporary = result["answers"]["is_temporary"]

    parsed = {
        "action": action["choice"],
        "action_confidence": action["confidence"],
        "traffic_class": traffic["choice"],
        "traffic_class_confidence": traffic["confidence"],
        "is_temporary": temporary["noul"] > 0.5,
        "duration_sec": 1200,  # default 20 min, could be extracted separately
    }

    min_conf = min(action["confidence"], traffic["confidence"])
    parsed["needs_confirmation"] = min_conf < CONFIDENCE_THRESHOLD
    parsed["overall_confidence"] = round(min_conf, 3)

    return parsed


if __name__ == "__main__":
    import json
    test_cases = [
        "mujhe agle 20 minute ke liye video call priority chahiye",
        "bulk download ko slow kar do, gaming zyada important hai abhi",
        "sab normal kar do"
    ]
    for t in test_cases:
        print(f"\nInput: {t}")
        print(json.dumps(parse_intent(t), indent=2))
