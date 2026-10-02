# Custom WSL2 Kernel Build (CAKE + NetEm support)

The stock WSL2 kernel does not ship `sch_cake` or `sch_netem`. Steps to build
a custom kernel with both enabled:

```bash
sudo apt install -y build-essential flex bison libssl-dev libelf-dev \
    dwarves bc python3 python3-pip libncurses-dev git

git clone https://github.com/microsoft/WSL2-Linux-Kernel.git --depth 1
cd WSL2-Linux-Kernel
cp Microsoft/config-wsl .config

make menuconfig
# Navigate: Networking support -> Networking options -> QoS and/or fair queueing
# Enable (press Y, not M, for built-in):
#   Common Applications Kept Enhanced (CAKE)
#   Network emulator (NETEM)
# Save and Exit

make -j$(nproc)
cp vmlinux /mnt/c/Users/<WindowsUsername>/wsl2-kernel-cake
```

Create/edit `C:\Users\<WindowsUsername>\.wslconfig`:
```ini
[wsl2]
kernel=C:\\Users\\<WindowsUsername>\\wsl2-kernel-cake
```

Restart WSL2:
```powershell
wsl --shutdown
wsl
```

Verify:
```bash
uname -r
sudo tc qdisc add dev lo root cake
sudo tc qdisc del dev lo root
sudo tc qdisc add dev lo root netem delay 10ms
sudo tc qdisc del dev lo root
```
Both should succeed without "Specified qdisc kind is unknown" errors.
