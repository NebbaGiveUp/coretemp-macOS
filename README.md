# Core Temp for macOS

A lightweight hardware telemetry and temperature monitor for Intel Alder Lake-P processors on macOS, featuring the classic Core Temp desktop interface.

This is a vibe coded application developed for the Dell Latitude 7430 Hackintosh and other Intel-based macOS systems.

---

## Features

- **Classic Core Temp Interface:** Faithful recreation of the compact Windows Core Temp UI, featuring dual-theme support (monochrome dark gray and classic light).
- **Per-Core Telemetry:** Live frequency and utilization tracking for 12 physical cores (4 Performance cores with Hyper-Threading + 8 Efficient cores, 16 logical threads).
- **Dynamic Silicon Junction Thermal Model:** Real-time die temperature estimation calculated from Intel RAPL power dissipation and per-core clock telemetry.
- **Package & Component Power:** Real-time Package TDP, Core power, and Intel Iris Xe GT power measurements.
- **Integrated GPU Profiling:** Displays GPU Name (`Intel Iris Xe Graphics 0x46A6`), EU count, and dynamic VRAM configuration.
- **Hardware Throttling Status:** Live detection of thermal limits, PL1 sustained limits, PL2 burst limits, and VRM ICCMAX constraints.
- **One-Click Stress Testing:** Built-in multi-threaded all-core workload runner under `Tools -> Run 10s CPU Stress Test`.
- **In-App Issue Reporting:** Dedicated "Report an Issue" button linking directly to the repository issue tracker.

---

## System Requirements

- **Operating System:** macOS Monterey (12.x), Ventura (13.x), Sonoma (14.x), Sequoia (15.x), or Tahoe (26.x).
- **Processor:** 12th-Gen Intel Alder Lake-P (Core i7-1270P tested) or compatible Intel Core CPU.
- **Dependencies:** Python 3 (with standard `tkinter` framework).

---

## Installation and Usage

### Option 1: Standalone Application (`Core Temp.app`)

1. Clone the repository:
   ```bash
   git clone https://github.com/NebbaGiveUp/coretemp-macOS.git
   cd coretemp-macOS
   ```
2. Copy `Core Temp.app` to your `/Applications` directory:
   ```bash
   cp -R "Core Temp.app" /Applications/
   ```
3. Launch **Core Temp** from Spotlight, Launchpad, or Finder.

### Option 2: Run via Terminal

```bash
cd coretemp-macOS
python3 coretemp.py
```

Or double-click `Launch Core Temp.command` in Finder.

---

## Telemetry Implementation Notes

Alder Lake Hackintoshes running Lilu and VirtualSMC do not expose native MSR thermal junction registers (`TC0P`) because Lilu identifies the CPU generation as unknown. 

To overcome this limitation, Core Temp for macOS captures real-time Intel RAPL hardware counters and per-core clock residency via `powermetrics`, feeding a dynamic silicon junction model:

$$T_{\text{core}} = T_{\text{ambient}} + R_{\theta \text{JA}} \cdot P_{\text{package}} \cdot \left(1 - e^{-\Delta t / \tau}\right) + \Delta T_{\text{clock}}$$

- **Base Ambient Reference ($T_{\text{ambient}}$):** Captured from SBS smart battery temperature sensors (`AppleSmartBattery`).
- **Thermal Resistance ($R_{\theta \text{JA}}$):** $1.15\,^\circ\text{C}/\text{W}$ modeled after the Dell Latitude 7430 dual-heatpipe cooling assembly.
- **Thermal Time Constant ($\tau$):** $3.5\,\text{s}$ transient thermal mass response.

---

## Issues & Contributing

If you encounter bugs, broken sensor readings, or platform layout issues, please use the in-app **Report an Issue** button or visit the [Issue Tracker](https://github.com/NebbaGiveUp/coretemp-macOS/issues).

---

## Credits & Attribution

- **Arthur Liberman (ALCPU):** Creator of the original [Core Temp](https://www.alcpu.com/CoreTemp/) utility for Windows, which inspired this interface design.
- **Development:** Vibe coded project for the macOS Hackintosh community.

---

## License

MIT License. See `LICENSE` for details.
