import subprocess
import re

def get_cake_stats(namespace="gw", iface="veth-gw-wan"):
    cmd = ["sudo", "ip", "netns", "exec", namespace, "tc", "-s", "qdisc", "show", "dev", iface]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout

    stats = {"raw": output}

    bw_match = re.search(r"bandwidth (\S+)", output)
    if bw_match:
        stats["bandwidth"] = bw_match.group(1)

    sent_match = re.search(r"Sent (\d+) bytes (\d+) pkt", output)
    if sent_match:
        stats["sent_bytes"] = int(sent_match.group(1))
        stats["sent_packets"] = int(sent_match.group(2))

    return stats

if __name__ == "__main__":
    stats = get_cake_stats()
    print("Bandwidth:", stats.get("bandwidth"))
    print("Sent bytes:", stats.get("sent_bytes"))
    print("Sent packets:", stats.get("sent_packets"))
