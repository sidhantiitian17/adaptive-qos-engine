"""
NetMatrix-inspired feature extraction: sirf IP total length, TTL,
aur inter-arrival time use karte hain — payload kabhi nahi chhuya jaata.
"""
from scapy.all import sniff, IP
import time
import csv
import sys

def capture_features(iface, duration_sec, label, output_csv, max_packets=500):
    """
    Given interface pe packets capture karo, NetMatrix features nikaalo,
    aur CSV mein likho (label ke saath, training ke liye).
    """
    packets_data = []
    last_time = {}

    def process_packet(pkt):
        if IP in pkt:
            src = pkt[IP].src
            now = time.time()
            inter_arrival = now - last_time.get(src, now)
            last_time[src] = now

            packets_data.append({
                "total_length": pkt[IP].len,
                "ttl": pkt[IP].ttl,
                "inter_arrival_ms": round(inter_arrival * 1000, 3),
                "label": label
            })

    print(f"Capturing on {iface} for {duration_sec}s (label={label})...")
    sniff(iface=iface, prn=process_packet, timeout=duration_sec, store=False,
          count=max_packets)

    # CSV mein append karo
    file_exists = False
    try:
        with open(output_csv, 'r'):
            file_exists = True
    except FileNotFoundError:
        pass

    with open(output_csv, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=["total_length", "ttl", "inter_arrival_ms", "label"])
        if not file_exists:
            writer.writeheader()
        writer.writerows(packets_data)

    print(f"Captured {len(packets_data)} packets, saved to {output_csv}")

if __name__ == "__main__":
    iface = sys.argv[1]
    duration = int(sys.argv[2])
    label = sys.argv[3]
    output = sys.argv[4] if len(sys.argv) > 4 else "training_data.csv"
    capture_features(iface, duration, label, output)
