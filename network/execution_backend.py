"""
Execution Backend Abstraction for Network Operations:
Detects host privilege boundaries and abstracts execution across:
  - RootExecutionBackend: Direct root execution (euid == 0)
  - SudoExecutionBackend: Passwordless sudo available
  - UserNamespaceExecutionBackend: Unprivileged user namespace (unshare -rn)
  - UnavailableExecutionBackend: No privileged or containerized execution possible
"""
import os
import subprocess
import shutil
from typing import Dict, Any, List, Optional, Tuple


class ExecutionBackend:
    name: str = "base"

    def is_available(self) -> bool:
        raise NotImplementedError

    def exec_cmd(self, cmd: List[str], namespace: Optional[str] = None) -> Tuple[int, str, str]:
        raise NotImplementedError

    def get_status(self) -> Dict[str, Any]:
        features = self.check_kernel_features()
        return {
            "status": "available" if self.is_available() else "unavailable",
            "backend": self.name,
            "kernel": features
        }

    def check_kernel_features(self) -> Dict[str, bool]:
        """Verify whether CAKE and NetEm are available in the Linux kernel."""
        cake_ok = False
        netem_ok = False
        # Test 1: Check in unshare or directly on lo
        try:
            res = subprocess.run(
                ["unshare", "-rn", "tc", "qdisc", "add", "dev", "lo", "root", "cake"],
                capture_output=True, timeout=2
            )
            cake_ok = (res.returncode == 0)
        except Exception:
            pass

        try:
            res = subprocess.run(
                ["unshare", "-rn", "tc", "qdisc", "add", "dev", "lo", "root", "netem", "delay", "10ms"],
                capture_output=True, timeout=2
            )
            netem_ok = (res.returncode == 0)
        except Exception:
            pass

        # If unshare test failed, check kernel config if accessible
        if not (cake_ok and netem_ok) and os.path.exists("/proc/config.gz"):
            try:
                out = subprocess.check_output("zcat /proc/config.gz 2>/dev/null", shell=True, text=True)
                if "CONFIG_NET_SCH_CAKE=y" in out:
                    cake_ok = True
                if "CONFIG_NET_SCH_NETEM=y" in out:
                    netem_ok = True
            except Exception:
                pass

        return {"cake": cake_ok, "netem": netem_ok}


class RootExecutionBackend(ExecutionBackend):
    name = "root"

    def is_available(self) -> bool:
        return os.geteuid() == 0

    def exec_cmd(self, cmd: List[str], namespace: Optional[str] = None) -> Tuple[int, str, str]:
        full_cmd = []
        if namespace:
            full_cmd = ["ip", "netns", "exec", namespace] + cmd
        else:
            full_cmd = cmd
        try:
            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=5)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)


class SudoExecutionBackend(ExecutionBackend):
    name = "sudo"

    def is_available(self) -> bool:
        if os.geteuid() == 0:
            return True
        try:
            res = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=2)
            return res.returncode == 0
        except Exception:
            return False

    def exec_cmd(self, cmd: List[str], namespace: Optional[str] = None) -> Tuple[int, str, str]:
        full_cmd = ["sudo", "-n"]
        if namespace:
            full_cmd.extend(["ip", "netns", "exec", namespace])
        full_cmd.extend(cmd)
        try:
            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=5)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)


class UserNamespaceExecutionBackend(ExecutionBackend):
    """
    Rootless execution using Linux user and network namespaces (unshare -rn).
    Provides genuine CAP_NET_ADMIN capabilities without host root privileges.
    """
    name = "rootless_userns"

    def is_available(self) -> bool:
        try:
            res = subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=2)
            return res.returncode == 0
        except Exception:
            return False

    def exec_cmd(self, cmd: List[str], namespace: Optional[str] = None) -> Tuple[int, str, str]:
        # If already running with euid == 0 (inside userns), execute directly
        if os.geteuid() == 0:
            full_cmd = cmd if not namespace else ["ip", "netns", "exec", namespace] + cmd
            try:
                res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=5)
                return res.returncode, res.stdout, res.stderr
            except Exception as e:
                return 1, "", str(e)

        # Otherwise execute inside unshare -rn
        full_cmd = ["unshare", "-rn"] + cmd
        try:
            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=5)
            return res.returncode, res.stdout, res.stderr
        except Exception as e:
            return 1, "", str(e)


class UnavailableExecutionBackend(ExecutionBackend):
    name = "unavailable"

    def is_available(self) -> bool:
        return False

    def exec_cmd(self, cmd: List[str], namespace: Optional[str] = None) -> Tuple[int, str, str]:
        return 1, "", "Execution backend is unavailable: Insufficient system privileges and unshare not supported."


_cached_backend = None

def get_execution_backend(force_refresh: bool = False) -> ExecutionBackend:
    global _cached_backend
    if _cached_backend is not None and not force_refresh:
        return _cached_backend

    # 1. Root check
    if os.geteuid() == 0:
        _cached_backend = RootExecutionBackend()
        return _cached_backend

    # 2. Sudo check
    sudo_backend = SudoExecutionBackend()
    if sudo_backend.is_available():
        _cached_backend = sudo_backend
        return _cached_backend

    # 3. User namespace check
    userns_backend = UserNamespaceExecutionBackend()
    if userns_backend.is_available():
        _cached_backend = userns_backend
        return _cached_backend

    # 4. Fallback
    _cached_backend = UnavailableExecutionBackend()
    return _cached_backend


if __name__ == "__main__":
    be = get_execution_backend()
    status = be.get_status()
    print("Execution Backend Detection:")
    print(f"  Backend Name:    {be.name}")
    print(f"  Is Available:    {be.is_available()}")
    print(f"  Status Dict:     {status}")
    assert be.is_available(), "Execution backend must be available"
    print("ExecutionBackend verification: PASS ✅")
