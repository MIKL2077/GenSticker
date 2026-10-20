"""Local shared-host monitoring. Writes private state and journal alerts only."""

import json
import logging
import os
from pathlib import Path
import shutil
import time
from .store import root
from .traffic import period, usage


def sample():
    path = root() / "host-monitor.json"
    try:
        old = json.loads(path.read_text())
    except (OSError, ValueError):
        old = {}
    # egress across physical interface only; never sum loopback/Tailscale twice.
    interfaces = [
        p for p in Path("/sys/class/net").iterdir() if (p / "device").exists()
    ]
    total = sum(int((p / "statistics/tx_bytes").read_text()) for p in interfaces)
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    cumulative = (
        old.get("estimated_egress_bytes", 0) if old.get("period") == period() else 0
    )
    if old.get("boot") == boot and old.get("period") == period():
        cumulative += max(0, total - old.get("interface_tx", total))
    mem = {
        line.split(":")[0]: int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.split()[1].isdigit()
    }
    data = {
        "period": period(),
        "sampled": time.time(),
        "boot": boot,
        "interface_tx": total,
        "estimated_egress_bytes": cumulative,
        "api_egress_bytes": usage(),
        "interfaces": [p.name for p in interfaces],
        "free_disk_bytes": shutil.disk_usage(root()).free,
        "available_memory_bytes": mem.get("MemAvailable", 0),
        "load_1m": os.getloadavg()[0],
        "coverage_start": old.get("coverage_start", time.time()),
        "scope": "measured from first sample; not a cloud bill; excludes earlier usage and possibly provider-specific traffic",
    }
    budget = max(1, int(os.getenv("GENSTICKER_HOST_MONTHLY_BYTES", "1500000000000")))
    level = next((n for n in (95, 85, 70, 50) if cumulative >= budget * n / 100), 0)
    alerts = []
    if level > alert_level(old):
        alerts.append(f"host egress estimate reached {level}% of planning budget")
    if data["free_disk_bytes"] < 10 * 1024**3:
        alerts.append("private storage low disk water mark")
    if data["available_memory_bytes"] < 3 * 1024**3:
        alerts.append("shared host available memory below 3 GiB")
    if data["load_1m"] > 3.5:
        alerts.append("shared host load above 3.5")
    data["alert_level"] = level
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)
    for alert in alerts:
        logging.warning(alert)
    print(
        json.dumps(
            {
                "status": "attention" if alerts else "ok",
                "alerts": alerts,
                "period": period(),
            }
        )
    )


def alert_level(old):
    return old.get("alert_level", 0) if old.get("period") == period() else 0


if __name__ == "__main__":
    sample()
