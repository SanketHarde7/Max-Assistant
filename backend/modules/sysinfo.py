# Path: backend/modules/sysinfo.py
# Use: Retrieves current CPU, RAM, and OS status.
"""
sysinfo.py — MAX v4.2
System information skill: CPU, RAM, disk usage, battery.
Requires: pip install psutil
"""
import logging
from typing import Optional

logger = logging.getLogger("MAX.SYSINFO")


def get_system_info(detail: str = "all") -> str:
    """
    Returns formatted system status string.
    detail: "all" | "cpu" | "ram" | "disk" | "battery" | "network"
    """
    try:
        import psutil
    except ImportError:
        return "System info needs psutil. Run: pip install psutil"

    parts = []
    d = detail.lower().strip()

    try:
        if d in ("all", "cpu"):
            cpu = psutil.cpu_percent(interval=0.5)
            freq = psutil.cpu_freq()
            cores = psutil.cpu_count(logical=False)
            freq_str = f" @ {freq.current:.0f}MHz" if freq else ""
            parts.append(f"CPU: {cpu:.0f}% ({cores} cores{freq_str})")
    except Exception as e:
        logger.warning(f"CPU info failed: {e}")

    try:
        if d in ("all", "ram"):
            ram = psutil.virtual_memory()
            used_gb = ram.used / 1024 ** 3
            total_gb = ram.total / 1024 ** 3
            parts.append(f"RAM: {ram.percent:.0f}% ({used_gb:.1f}GB / {total_gb:.1f}GB)")
    except Exception as e:
        logger.warning(f"RAM info failed: {e}")

    try:
        if d in ("all", "disk"):
            disk = psutil.disk_usage("/")
            free_gb = disk.free / 1024 ** 3
            total_gb = disk.total / 1024 ** 3
            parts.append(f"Disk: {disk.percent:.0f}% used ({free_gb:.1f}GB free / {total_gb:.1f}GB)")
    except Exception as e:
        logger.warning(f"Disk info failed: {e}")

    try:
        if d in ("all", "battery"):
            battery = psutil.sensors_battery()
            if battery:
                status = "charging ⚡" if battery.power_plugged else "on battery 🔋"
                mins_left = ""
                if not battery.power_plugged and battery.secsleft > 0:
                    mins = battery.secsleft // 60
                    mins_left = f", ~{mins}m left"
                parts.append(f"Battery: {battery.percent:.0f}% ({status}{mins_left})")
    except Exception as e:
        logger.warning(f"Battery info failed: {e}")

    try:
        if d in ("all", "network"):
            net = psutil.net_io_counters()
            sent_mb = net.bytes_sent / 1024 ** 2
            recv_mb = net.bytes_recv / 1024 ** 2
            parts.append(f"Network: ↑{sent_mb:.0f}MB sent, ↓{recv_mb:.0f}MB received")
    except Exception as e:
        logger.warning(f"Network info failed: {e}")

    if not parts:
        return "Could not fetch system info."

    return " | ".join(parts)


def get_top_processes(n: int = 5) -> str:
    """Returns top N CPU-consuming processes."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                procs.append(p.info)
            except Exception:
                pass
        procs.sort(key=lambda x: x.get("cpu_percent", 0), reverse=True)
        lines = [f"Top {n} processes by CPU:"]
        for p in procs[:n]:
            name = p.get("name", "?")[:20]
            cpu  = p.get("cpu_percent", 0)
            ram  = p.get("memory_percent", 0)
            lines.append(f"  {name}: CPU {cpu:.1f}%, RAM {ram:.1f}%")
        return "\n".join(lines)
    except ImportError:
        return "psutil not installed: pip install psutil"
    except Exception as e:
        return f"Process list failed: {e}"
