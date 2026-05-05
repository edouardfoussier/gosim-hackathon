"""Entry script wrapped by PyInstaller into ``xiexie-overlay``.

The overlay package's ``__main__`` already implements the full CLI;
this trampoline just re-exports it so PyInstaller has a concrete
``.py`` file to freeze (it can't freeze ``-m overlay`` directly).
"""

from __future__ import annotations

import sys

from overlay.__main__ import main


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
