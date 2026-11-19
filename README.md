# Core Temp for macOS

A lightweight hardware telemetry and temperature monitor for Intel Alder Lake-P processors on macOS, styled after the classic Windows Core Temp utility.

Tested on **Dell Latitude 7430** (Intel Core i7-1270P) running macOS Tahoe (26.x) and Sequoia (15.x).

---

## Features

- **Classic UI:** Compact desktop interface with dual-theme support (Dark and Classic Light).
- **Per-Core Telemetry:** Live frequency and utilization tracking for 4 Performance cores (8 threads) and 8 Efficient cores (16 logical threads total).
- **Thermal Modeling:** Real-time junction temperature estimation using Intel RAPL power dissipation and per-core clock residency.
- **Power Monitoring:** Real-time Package TDP, Core power, and Intel Iris Xe GT power draw.
- **GPU Profiling:** Reports GPU device name (`Intel Iris Xe Graphics 0x46A6`), EU count, and dynamic VRAM allocation.
- **Throttle Detection:** Live flags for thermal throttling, PL1/PL2 power limits, and VRM current limits.
- **Stress Test:** Built-in multi-threaded CPU stress benchmark (`Tools -> Run 10s CPU Stress Test`).

---

## System Requirements

- **OS:** macOS 12 Monterey or later (tested on macOS 15 Sequoia and macOS 26 Tahoe).
- **CPU:** 12th-Gen Intel Core (Alder Lake-P / i7-1270P) or compatible Intel processor.
- **Runtime:** Python 3 with `tkinter` (included with macOS command line tools / Homebrew).

---

## Installation & Running

### Application Bundle

```bash
git clone https://github.com/NebbaGiveUp/coretemp-macOS.git
cp -R "coretemp-macOS/Core Temp.app" /Applications/
```

Launch **Core Temp** from `/Applications`, Spotlight, or Launchpad.

### Terminal

```bash
cd coretemp-macOS
python3 coretemp.py
```

Alternatively, run `Launch Core Temp.command` in Finder.

---

## Telemetry Implementation

On Alder Lake Hackintoshes, Lilu and VirtualSMC do not expose native MSR thermal junction registers (`TC0P`) due to unmatched CPU generation IDs.

Core Temp calculates per-core temperatures by reading Intel RAPL energy counters and frequency residency from `powermetrics`, applying a transient thermal resistance model calibrated to the cooling assembly of the Dell Latitude 7430:

- **Ambient Reference:** Battery thermal sensor (`AppleSmartBattery`).
- **Thermal Resistance ($R_{\theta\text{JA}}$):** $1.15\,^\circ\text{C}/\text{W}$.
- **Thermal Time Constant ($\tau$):** $3.5\,\text{s}$.

---

## Credits

- **Arthur Liberman (ALCPU):** Creator of the original [Core Temp](https://www.alcpu.com/CoreTemp/) for Windows.

---

## License

MIT License.
