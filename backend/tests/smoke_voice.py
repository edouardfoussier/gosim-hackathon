"""Smoke check: imports + monitor instantiation, no actual mic capture."""

from xiexie.voice import ptt, wake

print("imports ok")
detector = wake.WakeWordDetector()
print("wake detector ready, available:", detector.is_available())
monitor = ptt.PushToTalkMonitor()
print("ptt monitor ready")
