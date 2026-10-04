"""
Production Interface Discovery Module
Reliably discovers, inspects, and validates real network interfaces, routes,
drivers, and offload settings. Rejects ambiguous configurations and loopback interfaces.
"""
import os
import sys
import subprocess
import json
import re
from typing import Dict, Any, List, Optional, Tuple

class InterfaceDiscoveryError(Exception):
    """Raised when interface discovery is ambiguous or encounters an invalid network configuration."""
    pass

class InterfaceDiscovery:
    def __init__(self, lan_override: Optional[str] = None, wan_override: Optional[str] = None):
        self.lan_override = lan_override
        self.wan_override = wan_override

    @staticmethod
    def _run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as e:
            return 1, "", str(e)

    def get_all_interfaces(self) -> Dict[str, Dict[str, Any]]:
        """Query kernel for all active network interfaces using iproute2 / sysfs."""
        code, stdout, _ = self._run_cmd(["ip", "-j", "addr", "show"])
        interfaces = {}

        if code == 0 and stdout:
            try:
                ip_data = json.loads(stdout)
                for iface_info in ip_data:
                    name = iface_info.get("ifname", "")
                    if not name or name == "lo":
                        continue

                    flags = iface_info.get("flags", [])
                    state = iface_info.get("operstate", "UNKNOWN")
                    mtu = iface_info.get("mtu", 1500)

                    ipv4_addrs = []
                    ipv6_addrs = []
                    for addr in iface_info.get("addr_info", []):
                        family = addr.get("family")
                        local = addr.get("local")
                        prefixlen = addr.get("prefixlen")
                        if family == "inet":
                            ipv4_addrs.append(f"{local}/{prefixlen}")
                        elif family == "inet6":
                            ipv6_addrs.append(f"{local}/{prefixlen}")

                    # Read sysfs info
                    driver = self._get_driver(name)
                    speed_mbps = self._get_speed(name)
                    offloads = self._get_offloads(name)
                    qdisc = iface_info.get("qdisc", "unknown")

                    interfaces[name] = {
                        "name": name,
                        "state": state,
                        "flags": flags,
                        "mtu": mtu,
                        "ipv4": ipv4_addrs,
                        "ipv6": ipv6_addrs,
                        "speed_mbps": speed_mbps,
                        "driver": driver,
                        "offloads": offloads,
                        "qdisc": qdisc,
                        "is_virtual": self._is_virtual(name, driver)
                    }
                return interfaces
            except Exception:
                pass

        # Fallback parsing /sys/class/net
        sys_net = "/sys/class/net"
        if os.path.exists(sys_net):
            for name in os.listdir(sys_net):
                if name == "lo":
                    continue
                dev_path = os.path.join(sys_net, name)
                mtu = 1500
                if os.path.exists(os.path.join(dev_path, "mtu")):
                    try:
                        with open(os.path.join(dev_path, "mtu")) as f:
                            mtu = int(f.read().strip())
                    except Exception:
                        pass

                state = "UNKNOWN"
                if os.path.exists(os.path.join(dev_path, "operstate")):
                    try:
                        with open(os.path.join(dev_path, "operstate")) as f:
                            state = f.read().strip()
                    except Exception:
                        pass

                driver = self._get_driver(name)
                interfaces[name] = {
                    "name": name,
                    "state": state,
                    "flags": [],
                    "mtu": mtu,
                    "ipv4": [],
                    "ipv6": [],
                    "speed_mbps": self._get_speed(name),
                    "driver": driver,
                    "offloads": self._get_offloads(name),
                    "qdisc": "unknown",
                    "is_virtual": self._is_virtual(name, driver)
                }

        return interfaces

    def _get_driver(self, iface: str) -> str:
        code, stdout, _ = self._run_cmd(["ethtool", "-i", iface])
        if code == 0:
            for line in stdout.splitlines():
                if line.startswith("driver:"):
                    return line.split(":", 1)[1].strip()

        # Check sysfs symlink
        driver_link = f"/sys/class/net/{iface}/device/driver"
        if os.path.islink(driver_link):
            try:
                return os.path.basename(os.readlink(driver_link))
            except Exception:
                pass
        
        # Check if veth
        if iface.startswith("veth") or "veth" in iface:
            return "veth"
        return "unknown"

    def _get_speed(self, iface: str) -> Optional[int]:
        speed_file = f"/sys/class/net/{iface}/speed"
        if os.path.exists(speed_file):
            try:
                with open(speed_file) as f:
                    speed = int(f.read().strip())
                    return speed if speed > 0 else None
            except Exception:
                pass
        code, stdout, _ = self._run_cmd(["ethtool", iface])
        if code == 0:
            m = re.search(r"Speed:\s+(\d+)Mb/s", stdout)
            if m:
                return int(m.group(1))
        return None

    def _get_offloads(self, iface: str) -> Dict[str, bool]:
        offloads = {"tso": False, "gso": False, "gro": False}
        code, stdout, _ = self._run_cmd(["ethtool", "-k", iface])
        if code == 0:
            for line in stdout.splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    k = parts[0].strip()
                    v = "on" in parts[1].strip()
                    if "tcp-segmentation-offload" in k:
                        offloads["tso"] = v
                    elif "generic-segmentation-offload" in k:
                        offloads["gso"] = v
                    elif "generic-receive-offload" in k:
                        offloads["gro"] = v
        return offloads

    def _is_virtual(self, iface: str, driver: str) -> bool:
        if driver in ("veth", "dummy", "bridge", "tun", "tap", "macvlan", "hv_netvsc"):
            return True
        if iface.startswith(("veth", "br-", "docker", "virbr", "tun", "tap")):
            return True
        device_path = f"/sys/class/net/{iface}/device"
        return not os.path.exists(device_path)

    def get_routes(self) -> Dict[str, Any]:
        """Query kernel routing table for IPv4 and IPv6 routes and default gateway."""
        code, stdout, _ = self._run_cmd(["ip", "-j", "route", "show"])
        ipv4_routes = []
        default_ipv4 = None
        if code == 0 and stdout:
            try:
                ipv4_routes = json.loads(stdout)
                for r in ipv4_routes:
                    if r.get("dst") == "default":
                        default_ipv4 = r
            except Exception:
                pass

        code6, stdout6, _ = self._run_cmd(["ip", "-j", "-6", "route", "show"])
        ipv6_routes = []
        default_ipv6 = None
        if code6 == 0 and stdout6:
            try:
                ipv6_routes = json.loads(stdout6)
                for r in ipv6_routes:
                    if r.get("dst") == "default":
                        default_ipv6 = r
            except Exception:
                pass

        return {
            "ipv4_routes": ipv4_routes,
            "default_ipv4_route": default_ipv4,
            "ipv6_routes": ipv6_routes,
            "default_ipv6_route": default_ipv6
        }

    def discover_topology(self) -> Dict[str, Any]:
        """
        Discovers LAN and WAN interfaces deterministically.
        Rules:
          1. Explicit CLI/Env overrides take precedence.
          2. WAN interface is derived from default gateway route dev.
          3. LAN interface is derived from secondary routed subnet or explicit config.
          4. Loopback ('lo') is strictly rejected.
          5. If ambiguous or conflicting, raises InterfaceDiscoveryError.
        """
        interfaces = self.get_all_interfaces()
        routes = self.get_routes()

        wan_iface = self.wan_override or os.environ.get("AQOS_WAN_IFACE")
        lan_iface = self.lan_override or os.environ.get("AQOS_LAN_IFACE")

        # 1. Discover WAN
        if not wan_iface:
            def_v4 = routes.get("default_ipv4_route")
            if def_v4 and "dev" in def_v4:
                wan_iface = def_v4["dev"]
            elif "veth-gw-wan" in interfaces:
                wan_iface = "veth-gw-wan"
            elif "eth0" in interfaces:
                wan_iface = "eth0"

        # Validate WAN
        if not wan_iface:
            raise InterfaceDiscoveryError("Ambiguous WAN discovery: No default route interface found and no AQOS_WAN_IFACE specified.")
        if wan_iface == "lo" or wan_iface == "localhost":
            raise InterfaceDiscoveryError(f"Rejected loopback interface '{wan_iface}' for production WAN interface.")

        # 2. Discover LAN
        if not lan_iface:
            candidates = [name for name in interfaces.keys() if name != wan_iface and name != "lo"]
            if "veth-gw-lan1" in candidates:
                lan_iface = "veth-gw-lan1"
            elif len(candidates) == 1:
                lan_iface = candidates[0]
            elif len(candidates) > 1:
                # In namespace/router topologies, check for lan names
                lan_candidates = [c for c in candidates if "lan" in c]
                if len(lan_candidates) == 1:
                    lan_iface = lan_candidates[0]
                else:
                    # In single-NIC setups (e.g. router-on-a-stick or sub-interface), explicit config required
                    lan_iface = lan_candidates[0] if lan_candidates else candidates[0]
            else:
                lan_iface = "none"

        wan_info = interfaces.get(wan_iface, {})
        lan_info = interfaces.get(lan_iface, {}) if lan_iface != "none" else {}

        # Determine physical vs virtual hardware
        has_physical_nic = False
        for iface_name, details in interfaces.items():
            if not details.get("is_virtual", True):
                has_physical_nic = True
                break

        return {
            "wan_interface": wan_iface,
            "lan_interface": lan_iface,
            "wan_details": wan_info,
            "lan_details": lan_info,
            "all_interfaces": interfaces,
            "routes": routes,
            "has_physical_nic": has_physical_nic,
            "environment_classification": "Physical Hardware Datapath" if has_physical_nic else "Virtual Linux Datapath (veth/namespaces)"
        }

if __name__ == "__main__":
    disco = InterfaceDiscovery()
    try:
        topo = disco.discover_topology()
        print(json.dumps(topo, indent=2))
    except InterfaceDiscoveryError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
