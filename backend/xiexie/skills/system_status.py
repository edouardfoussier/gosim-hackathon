"""system_status — quick read-only health checks (WiFi, battery, volume).

Three skills bundled in one module because they all share the same
``subprocess`` plumbing and the same one-sentence-spoken-reply shape.
Every check is read-only and never mutates anything — Xiexie just
reports status to the user.

- ``check_wifi``     → "You're connected to <SSID>." / "WiFi is off."
- ``check_battery``  → "Your battery is at 87 %, plugged in and charging."
- ``adjust_volume``  → set / get / mute the macOS output volume
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from .registry import Skill, register


def _run(cmd: list[str], timeout: int = 4) -> tuple[bool, str]:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return out.returncode == 0, (out.stdout or out.stderr).strip()


def _osascript(script: str) -> tuple[bool, str]:
    return _run(["osascript", "-e", script], timeout=4)


# ─────────────────────────────────────────────────────────────────────────────
# check_wifi
# ─────────────────────────────────────────────────────────────────────────────


def _detect_wifi_interface() -> str | None:
    """Return the BSD interface name of the active Wi-Fi card (en0/en1/…).

    macOS Sequoia and later removed the legacy ``airport`` binary, so we
    have to ask ``networksetup -listallhardwareports`` for "Wi-Fi" and
    pull the device after it. Returns None if no Wi-Fi card is found.
    """
    ok, out = _run(["networksetup", "-listallhardwareports"], timeout=4)
    if not ok:
        return None
    # Output blocks look like:
    #   Hardware Port: Wi-Fi
    #   Device: en0
    #   Ethernet Address: …
    match = re.search(
        r"Hardware Port:\s*Wi-?Fi\s*\n\s*Device:\s*(\S+)",
        out,
        re.IGNORECASE,
    )
    return match.group(1) if match else None


def _wifi_run(_args: dict[str, Any]) -> str:
    print("[check_wifi] called", flush=True)

    iface = _detect_wifi_interface() or "en0"

    # Power state — quick early exit when wifi is just off.
    ok, out = _run(["networksetup", "-getairportpower", iface], timeout=4)
    if ok and "Off" in out:
        return "Your WiFi is turned off. Want me to walk you through turning it on?"

    # SSID via networksetup. macOS 14+ may print
    # "You are not associated with an AirPort network." when offline.
    ok, out = _run(["networksetup", "-getairportnetwork", iface], timeout=4)
    if ok and "Current Wi-Fi Network:" in out:
        ssid = out.split("Current Wi-Fi Network:", 1)[1].strip()
        if ssid and ssid.lower() != "you are not associated with an airport network.":
            return f"You're connected to {ssid}."
    if ok and "not associated" in out.lower():
        return "WiFi is on but you're not connected to a network."

    # Final fallback: ipconfig getsummary returns the active SSID on
    # current macOS even when networksetup doesn't.
    ok, out = _run(["ipconfig", "getsummary", iface], timeout=4)
    if ok:
        match = re.search(r"\bSSID\s*:\s*(.+)", out)
        if match:
            return f"You're connected to {match.group(1).strip()}."

    return (
        "I couldn't read the WiFi status — try clicking the WiFi icon in your "
        "menu bar to see what's going on."
    )


# ─────────────────────────────────────────────────────────────────────────────
# check_battery
# ─────────────────────────────────────────────────────────────────────────────


def _battery_run(_args: dict[str, Any]) -> str:
    print("[check_battery] called", flush=True)
    ok, out = _run(["pmset", "-g", "batt"], timeout=3)
    if not ok:
        return f"I couldn't read your battery: {out}"

    # Sample lines from ``pmset -g batt``:
    #   Now drawing from 'Battery Power'
    #    -InternalBattery-0 (id=12345789)	 87%; discharging; 4:13 remaining present: true
    pct_match = re.search(r"(\d+)%", out)
    state_match = re.search(r";\s*(charging|discharging|charged|AC attached)", out, re.IGNORECASE)
    eta_match = re.search(r"(\d+):(\d{2})\s+remaining", out)

    if not pct_match:
        return "Your Mac doesn't seem to have a battery (or I couldn't read it)."

    pct = int(pct_match.group(1))
    state = (state_match.group(1).lower() if state_match else "").strip()

    parts = [f"Your battery is at {pct} %"]
    if state in ("charging", "ac attached"):
        parts.append("plugged in and charging")
    elif state == "charged":
        parts.append("plugged in and fully charged")
    elif state == "discharging":
        parts.append("running on battery")

    sentence = ", ".join(parts) + "."
    if state == "discharging" and eta_match:
        h, m = eta_match.group(1), eta_match.group(2)
        sentence += f" About {h} hours and {m} minutes left."
    return sentence


# ─────────────────────────────────────────────────────────────────────────────
# adjust_volume
# ─────────────────────────────────────────────────────────────────────────────


_VOLUME_WORD = {
    "louder": "+15",
    "much louder": "+30",
    "quieter": "-15",
    "much quieter": "-30",
    "mute": "0",
    "max": "100",
}


def _volume_run(args: dict[str, Any]) -> str:
    raw = str(args.get("amount") or "louder").strip().lower()
    print(f"[adjust_volume] amount={raw!r}", flush=True)

    if raw in _VOLUME_WORD:
        target = _VOLUME_WORD[raw]
    elif raw.lstrip("+-").isdigit():
        target = raw  # already a number, with optional +/- prefix
    else:
        return (
            "I can make it louder, much louder, quieter, much quieter, mute it, "
            "or set it to a specific number — sorry, I didn't understand that."
        )

    if target.startswith("+") or target.startswith("-"):
        # Relative — read current volume and add/subtract.
        ok, current = _osascript("output volume of (get volume settings)")
        if not ok:
            return f"I couldn't read your current volume: {current}"
        try:
            current_n = int(current.strip())
        except ValueError:
            current_n = 50
        delta = int(target)
        new = max(0, min(100, current_n + delta))
    else:
        new = max(0, min(100, int(target)))

    ok, out = _osascript(f"set volume output volume {new}")
    if not ok:
        return f"I couldn't change the volume: {out}"
    if new == 0:
        return "Muted your speakers."
    if new == 100:
        return "Cranked your volume to the max."
    return f"Set the volume to {new}."


# ─────────────────────────────────────────────────────────────────────────────
# Skill registrations
# ─────────────────────────────────────────────────────────────────────────────

register(
    Skill(
        name="check_wifi",
        description=(
            "Tell the user whether they're connected to WiFi and which "
            "network. Use when the user asks if they're 'online', "
            "'connected to the wifi', 'on the internet', or worries that "
            "the wifi is broken."
        ),
        parameters={"type": "object", "properties": {}},
        run=_wifi_run,
        destructive=False,
        tags=["status", "senior"],
    )
)

register(
    Skill(
        name="check_battery",
        description=(
            "Report the user's battery percentage, charging state, and "
            "estimated time remaining. Use when the user asks 'how's my "
            "battery', 'is it charging', 'how much battery do I have left'."
        ),
        parameters={"type": "object", "properties": {}},
        run=_battery_run,
        destructive=False,
        tags=["status", "senior"],
    )
)

register(
    Skill(
        name="adjust_volume",
        description=(
            "Make the speakers louder or quieter, mute, or set a specific "
            "level (0-100). Use when the user says 'make it louder', "
            "'quieter please', 'I can't hear you', 'mute the speakers', "
            "'set volume to fifty'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "amount": {
                    "type": "string",
                    "description": (
                        "One of 'louder', 'much louder', 'quieter', 'much quieter', "
                        "'mute', 'max'; or a 0-100 number; or a relative '+15' / '-10'."
                    ),
                    "default": "louder",
                }
            },
        },
        run=_volume_run,
        destructive=False,
        tags=["accessibility", "senior"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("which", choices=["wifi", "battery", "volume"])
    p.add_argument("--amount", default="louder")
    a = p.parse_args()
    if a.which == "wifi":
        print(_wifi_run({}))
    elif a.which == "battery":
        print(_battery_run({}))
    else:
        print(_volume_run({"amount": a.amount}))
