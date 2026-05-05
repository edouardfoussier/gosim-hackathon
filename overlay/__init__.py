"""Xiexie native macOS overlay — always-on-top warning glyph.

Runs as a small standalone PyQt6 process alongside the FastAPI backend.
Listens on ``ws://localhost:8787/ws`` for ``{"type": "alert", ...}`` events
and surfaces a click-through floating glyph over any active app.
"""

__version__ = "0.1.0"
