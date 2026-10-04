# Adaptive QoS Engine: Troubleshooting Guide

## 1. Permission Denied on `ip netns` or `tc`
- **Cause:** Network namespace operations and Linux kernel traffic control require `CAP_NET_ADMIN` or root privileges.
- **Solution:** Run commands with root permissions or assign ambient capabilities to the python binary:
  ```bash
  sudo setcap cap_net_admin,cap_net_raw+ep ./venv/bin/python3
  ```

---

## 2. Stale Sockets or Dangling Namespaces
- **Symptom:** `Address already in use` on port 8000 or `File exists` when creating veth pairs.
- **Solution:** Execute the deterministic environment reset script:
  ```bash
  ./scripts/reset_environment.sh
  ```

---

## 3. SQLite Database Locked
- **Symptom:** `sqlite3.OperationalError: database is locked`
- **Cause:** A background experiment runner crashed while holding an exclusive transaction lock.
- **Solution:** The engine defaults to WAL (Write-Ahead Logging) mode. If a lock persists:
  ```bash
  fuser -k experiments/evidence.db
  python3 -c "import sqlite3; c = sqlite3.connect('experiments/evidence.db'); c.execute('PRAGMA wal_checkpoint(TRUNCATE);')"
  ```

---

## 4. CAKE Module Not Found
- **Symptom:** `RTNETLINK answers: No such file or directory` when applying CAKE qdisc.
- **Cause:** The Linux kernel lacks `sch_cake`.
- **Solution:** Load the kernel module:
  ```bash
  sudo modprobe sch_cake
  ```
  On WSL2, ensure your kernel build includes `CONFIG_NET_SCH_CAKE=m` or `=y`.
