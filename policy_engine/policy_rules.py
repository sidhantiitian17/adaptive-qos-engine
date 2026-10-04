"""
Deterministic, rule-based policy engine.
Combines available link capacity, active flow categories, and optional
temporary user intent to produce an optimal Linux CAKE traffic control configuration
with anti-starvation guarantees.
"""

def decide_policy(available_bandwidth_mbps: float, active_flows: list, user_intent: dict = None) -> dict:
    """
    Inputs:
      available_bandwidth_mbps: estimated WAN capacity
      active_flows: list of dicts [{'flow_id': '...', 'class': '...', 'confidence': ...}]
      user_intent: optional dict {'action': 'prioritize', 'traffic_class': 'video_conference', 'duration_sec': 1200}

    Outputs:
      dict with bandwidth shaping targets, DSCP tier mappings, and anti-starvation parameters.
    """
    if available_bandwidth_mbps is None or available_bandwidth_mbps <= 0:
        available_bandwidth_mbps = 10.0

    # Base shaping rate is 95% of available capacity to keep router queue empty (prevent bufferbloat)
    target_bw = round(available_bandwidth_mbps * 0.95)

    decision = {
        "bandwidth_mbit": target_bw,
        "diffserv_mode": "diffserv4",
        "reasoning": [],
        "starvation_floor_active": False,
        "active_classes": list(set(f.get("class", "unclassified") for f in active_flows)),
        "dscp_mappings": {
            "video_conference": "AF41",
            "gaming": "EF",
            "bulk_download": "CS1",
            "default": "CS0"
        }
    }

    # Anti-Starvation Guard (Constraint C4 & Acceptance Criteria)
    # Total shaping rate cannot drop below 5 Mbps under any circumstance
    if decision["bandwidth_mbit"] < 5:
        decision["bandwidth_mbit"] = 5
        decision["starvation_floor_active"] = True
        decision["reasoning"].append("Applied absolute link safety floor of 5 Mbps to prevent broadband collapse")

    # Minimum guaranteed allocation for bulk traffic
    bulk_floor_mbit = max(2, round(decision["bandwidth_mbit"] * 0.20))
    decision["min_bulk_bandwidth_mbit"] = bulk_floor_mbit
    decision["reasoning"].append(
        f"Guaranteed bulk progress floor: AQE is shaping the link to {decision['bandwidth_mbit']} Mbps and reserving a minimum {bulk_floor_mbit} Mbps policy floor for bulk traffic (20% of the shaped rate)"
    )

    # Flow balancing analysis
    has_video = any(f.get("class") == "video_conference" for f in active_flows)
    has_bulk = any(f.get("class") == "bulk_download" for f in active_flows)
    has_gaming = any(f.get("class") == "gaming" for f in active_flows)

    if has_video and has_bulk:
        decision["reasoning"].append(
            "Video conference + Bulk download active: DiffServ4 Video (AF41) isolated from Bulk (CS1)"
        )
    if has_gaming and has_video:
        decision["reasoning"].append(
            "Gaming + Video active: Gaming mapped to Voice/Interactive tin (EF) for ultra-low latency"
        )

    # Process temporary user intent
    if user_intent and user_intent.get("action") == "prioritize":
        target_class = user_intent.get("traffic_class") or user_intent.get("class")
        duration = user_intent.get("duration_sec", 1200)
        decision["priority_class"] = target_class
        decision["priority_duration_sec"] = duration
        decision["reasoning"].append(
            f"User requested temporary priority for {target_class} ({duration}s). Priority DSCP enforced."
        )

    return decision


if __name__ == "__main__":
    flows = [
        {"flow_id": "f1", "class": "video_conference", "confidence": 0.95},
        {"flow_id": "f2", "class": "bulk_download", "confidence": 0.90},
    ]

    print("=== Test 1: Standard Policy ===")
    res1 = decide_policy(available_bandwidth_mbps=20, active_flows=flows)
    print(res1)
    assert res1["bandwidth_mbit"] == 19
    assert res1["min_bulk_bandwidth_mbit"] >= 2

    print("\n=== Test 2: Low-bandwidth Safety Floor ===")
    res2 = decide_policy(available_bandwidth_mbps=3, active_flows=flows)
    print(res2)
    assert res2["bandwidth_mbit"] == 5
    assert res2["starvation_floor_active"] == True

    print("\n=== Test 3: Temporary User Intent ===")
    intent = {"action": "prioritize", "traffic_class": "video_conference", "duration_sec": 600}
    res3 = decide_policy(available_bandwidth_mbps=20, active_flows=flows, user_intent=intent)
    print(res3)
    assert res3["priority_class"] == "video_conference"
    print("\nPolicy rules & starvation guard verification: PASS ✅")
