"""Convert the six .eml fixtures into a single ``xiexie-demo.mbox`` file
that Mail.app can ingest via File → Import Mailboxes.

macOS Mail.app on Sequoia stopped accepting drag-drop of raw .eml from
Finder for most users (the importer needs DNS-resolvable From domains
*and* the right kMDItem content-type, both of which our spoofed scam
fixtures fail). Mbox format bypasses that path entirely — Mail.app's
``Files in mbox format`` import mode reads the messages straight off
disk into "On My Mac → Imports", from where you drag them into your
iCloud Inbox.

Usage::

    cd data/demo/eml
    python3 build_mbox.py

Then:
    1. Mail.app → File → Import Mailboxes…
    2. "Files in mbox format" → Continue
    3. Pick this directory (data/demo/eml/)
    4. Continue → Done
    5. The six messages appear under "On My Mac → Imports →
       xiexie-demo".
    6. Select them all → drag onto your iCloud Inbox in the sidebar.

Re-runnable: deletes any existing xiexie-demo.mbox before writing
(otherwise mailbox.add appends and you'd end up with 12 messages
after a second run).
"""

from __future__ import annotations

import mailbox
import shutil
from pathlib import Path


SRC = Path(__file__).resolve().parent
MBOX_PATH = SRC / "xiexie-demo.mbox"


def main() -> int:
    # ``mailbox.mbox`` creates a directory-style mbox on macOS, which
    # means we have to ``rmtree`` (not just unlink) on re-run.
    if MBOX_PATH.exists():
        if MBOX_PATH.is_dir():
            shutil.rmtree(MBOX_PATH)
        else:
            MBOX_PATH.unlink()

    mbox = mailbox.mbox(str(MBOX_PATH))
    mbox.lock()
    try:
        eml_files = sorted(SRC.glob("[0-9]*.eml"))
        if not eml_files:
            print("no .eml files found at", SRC)
            return 1
        for eml_file in eml_files:
            with open(eml_file, "rb") as f:
                msg = mailbox.mboxMessage(f.read())
            mbox.add(msg)
            print(f"  + {eml_file.name}")
    finally:
        mbox.flush()
        mbox.unlock()

    n = len(list(mbox.iterkeys()))
    print(f"\nwrote {n} message(s) to {MBOX_PATH}")
    print("\nNext: Mail.app → File → Import Mailboxes… → 'Files in mbox format'")
    print(f"         → select {SRC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
