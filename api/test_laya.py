from laya import Router

router = Router()

state = "mujhe agle 20 minute ke liye video call priority chahiye, baaki sab normal rahe"

questions = {
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

result = router.predict(state, questions)
print("Intent action:", result["answers"]["intent_action"]["choice"],
      "| confidence:", result["answers"]["intent_action"]["confidence"])
print("Traffic class:", result["answers"]["traffic_class"]["choice"],
      "| confidence:", result["answers"]["traffic_class"]["confidence"])
print("Is temporary:", result["answers"]["is_temporary"]["noul"])
