"""play_music — control Apple Music.app: play / pause / next / search-and-play.

Senior persona is the demo target — this is the warm "play me some Frank
Sinatra" beat in the pitch. AppleScript talks straight to the macOS
``Music`` application (formerly iTunes) so the user keeps full control
over their library and Apple subscriptions.
"""

from __future__ import annotations

import subprocess
from typing import Any

from .registry import Skill, register


def _osascript(script: str) -> tuple[bool, str]:
    out = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=8
    )
    return out.returncode == 0, (out.stdout or out.stderr).strip()


def _ensure_music_running() -> tuple[bool, str]:
    return _osascript('tell application "Music" to launch')


def _play_pause(action: str) -> tuple[bool, str]:
    verb = {"play": "play", "pause": "pause", "toggle": "playpause"}.get(
        action, "playpause"
    )
    return _osascript(f'tell application "Music" to {verb}')


def _next_track() -> tuple[bool, str]:
    return _osascript('tell application "Music" to next track')


def _previous_track() -> tuple[bool, str]:
    return _osascript('tell application "Music" to previous track')


def _search_and_play(query: str) -> tuple[bool, str]:
    """Search the user's Music library for ``query`` and play the first hit.

    Falls back to a simple ``play`` if no match — better to start *something*
    than to leave Margaret in silence after she asked for music.
    """
    safe = query.replace('"', "'")
    script = f'''
    tell application "Music"
        set theResults to (every track of library playlist 1 whose name contains "{safe}" or artist contains "{safe}" or album contains "{safe}")
        if (count of theResults) > 0 then
            set theTrack to item 1 of theResults
            play theTrack
            return "Playing " & (name of theTrack) & " by " & (artist of theTrack)
        else
            return "NO_MATCH"
        end if
    end tell
    '''
    return _osascript(script)


def run(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "play").strip().lower()
    query = str(args.get("query") or "").strip()
    print(f"[play_music] action={action!r} query={query!r}", flush=True)

    _ensure_music_running()

    if action == "search" and query:
        ok, output = _search_and_play(query)
        if not ok:
            return f"I couldn't reach Music.app: {output}"
        if output == "NO_MATCH":
            # Fall back to plain play so the demo never goes silent.
            _play_pause("play")
            return (
                f"I couldn't find anything matching {query!r} in your library, "
                "so I started whatever was queued up instead."
            )
        return output  # "Playing <track> by <artist>"

    if action == "next":
        ok, output = _next_track()
        return "Skipping to the next track." if ok else f"Couldn't skip: {output}"
    if action == "previous":
        ok, output = _previous_track()
        return "Going back to the previous track." if ok else f"Couldn't go back: {output}"
    if action == "pause":
        ok, output = _play_pause("pause")
        return "Paused the music." if ok else f"Couldn't pause: {output}"
    if action == "toggle":
        ok, output = _play_pause("toggle")
        return "Toggled play / pause." if ok else f"Couldn't toggle: {output}"

    # default — plain play
    ok, output = _play_pause("play")
    return "Playing your music now." if ok else f"Couldn't start Music: {output}"


SKILL = register(
    Skill(
        name="play_music",
        description=(
            "Control Apple Music.app on the user's Mac: play, pause, skip "
            "to the next or previous track, or search the local library "
            "for a song / artist / album and play the first hit. Use when "
            "the user asks to 'play some music', 'play Frank Sinatra', "
            "'pause the music', 'next song', etc."
        ),
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "toggle", "next", "previous", "search"],
                    "default": "play",
                    "description": (
                        "What to do with Music.app. Use 'search' when the user "
                        "names a song / artist / album; combine with the 'query' "
                        "parameter."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Optional search string when action='search'. Matches "
                        "track name, artist, or album in the user's library."
                    ),
                },
            },
        },
        run=run,
        destructive=False,
        tags=["music", "lifestyle", "senior"],
    )
)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--action", default="play")
    p.add_argument("--query", default="")
    a = p.parse_args()
    print(run({"action": a.action, "query": a.query}))
