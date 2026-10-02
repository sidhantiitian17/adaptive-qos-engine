import subprocess
import time

WANHOST_IFACE = "veth-wan-gw"
NAMESPACE = "wanhost"

def run_cmd(cmd):
    """Command chalao aur output print karo (debugging ke liye)"""
    print(f"[CMD] {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] {result.stderr.strip()}")
    return result

def set_link_conditions(rate_mbit, delay_ms=20, loss_pct=0):
    """
    NetEm ko wanhost ke interface pe apply/update karta hai.
    Ye function 'ISP link ki current quality' set karta hai.
    """
    cmd = (f"sudo ip netns exec {NAMESPACE} tc qdisc show dev {WANHOST_IFACE}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if "netem" in result.stdout:
        # Already netem lagi hai, change karo
        action = "change"
    else:
        # Pehli baar lagao
        action = "add"
    
    cmd = (f"sudo ip netns exec {NAMESPACE} tc qdisc {action} dev {WANHOST_IFACE} "
           f"root netem rate {rate_mbit}mbit delay {delay_ms}ms loss {loss_pct}%")
    run_cmd(cmd)

def show_current_status():
    cmd = f"sudo ip netns exec {NAMESPACE} tc qdisc show dev {WANHOST_IFACE}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    print(result.stdout)

def remove_netem():
    cmd = f"sudo ip netns exec {NAMESPACE} tc qdisc del dev {WANHOST_IFACE} root"
    run_cmd(cmd)

def simulate_bandwidth_drop(from_mbit=100, to_mbit=20, wait_before=10, delay_ms=20):
    """
    PDF ka exact scenario: baseline period ke baad achanak WAN bandwidth drop ho jaati hai.
    """
    print(f"=== Setting baseline: {from_mbit} Mbps ===")
    set_link_conditions(from_mbit, delay_ms)
    show_current_status()
    
    print(f"\n=== Waiting {wait_before}s (baseline period) ===")
    time.sleep(wait_before)
    
    print(f"\n=== DROPPING bandwidth: {from_mbit} -> {to_mbit} Mbps ===")
    set_link_conditions(to_mbit, delay_ms)
    show_current_status()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "drop_test":
        simulate_bandwidth_drop(from_mbit=100, to_mbit=20, wait_before=10)
    elif len(sys.argv) > 1 and sys.argv[1] == "remove":
        remove_netem()
    else:
        rate = int(sys.argv[1]) if len(sys.argv) > 1 else 100
        set_link_conditions(rate)
        show_current_status()
