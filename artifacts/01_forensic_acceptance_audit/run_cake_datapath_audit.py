import os
import sys
import time
import socket
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if os.geteuid() != 0:
    subprocess.run(["unshare", "-rn", sys.executable, __file__] + sys.argv[1:])
    sys.exit(0)

# Bring up lo
subprocess.run(["ip", "link", "set", "dev", "lo", "up"], check=True)

# 1. State BEFORE
before_qdisc = subprocess.check_output(["tc", "-s", "qdisc", "show", "dev", "lo"], text=True)
before_links = subprocess.check_output(["ip", "link", "show"], text=True)
before_routes = subprocess.check_output(["ip", "route", "show"], text=True)

with open("audit_artifacts/kernel_state_before.txt", "w") as f:
    f.write("=== KERNEL STATE BEFORE CAKE ENFORCEMENT ===\n")
    f.write(f"EUID: {os.geteuid()}\n")
    f.write(f"PID: {os.getpid()}\n\n")
    f.write("--- IP LINKS ---\n" + before_links + "\n")
    f.write("--- IP ROUTES ---\n" + before_routes + "\n")
    f.write("--- TC QDISC SHOW ---\n" + before_qdisc + "\n")

# 2. Apply CAKE DiffServ4 with 18Mbit
subprocess.run(["tc", "qdisc", "add", "dev", "lo", "root", "cake", "bandwidth", "18mbit", "diffserv4"], check=True)

during_qdisc = subprocess.check_output(["tc", "-s", "qdisc", "show", "dev", "lo"], text=True)
with open("audit_artifacts/kernel_state_during.txt", "w") as f:
    f.write("=== KERNEL STATE DURING (AFTER CAKE APPLIED, BEFORE TRAFFIC) ===\n")
    f.write(during_qdisc + "\n")

# 3. Transmit DSCP-tagged traffic
# Voice/Gaming EF (TOS 0xB8) -> Voice tin
s_voice = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s_voice.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0xB8)
for _ in range(20):
    s_voice.sendto(b"VOICE_EF_" + b"A"*150, ("127.0.0.1", 7001))

# Video AF41 (TOS 0x88) -> Video tin
s_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s_video.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0x88)
for _ in range(30):
    s_video.sendto(b"VIDEO_AF41_" + b"B"*300, ("127.0.0.1", 7002))

# Bulk CS1 (TOS 0x20) -> Bulk tin
s_bulk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s_bulk.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 0x20)
for _ in range(50):
    s_bulk.sendto(b"BULK_CS1_" + b"C"*1200, ("127.0.0.1", 7003))

time.sleep(0.2)

# 4. State AFTER
after_qdisc = subprocess.check_output(["tc", "-s", "qdisc", "show", "dev", "lo"], text=True)
with open("audit_artifacts/kernel_state_after.txt", "w") as f:
    f.write("=== KERNEL STATE AFTER REAL DSCP TRAFFIC ===\n")
    f.write(after_qdisc + "\n")

with open("audit_artifacts/tc_qdisc_evidence.txt", "w") as f:
    f.write("=== TC QDISC FORENSIC EVIDENCE ===\n")
    f.write("Interface: lo (User Namespace Private Datapath)\n")
    f.write("Qdisc Configured: CAKE bandwidth 18Mbit diffserv4\n\n")
    f.write("Detailed Kernel Statistics:\n")
    f.write(after_qdisc + "\n")

print("CAKE Datapath forensic audit complete.")
