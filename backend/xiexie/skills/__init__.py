"""Skill registry. Importing this module registers all V1 skills."""

from .registry import SKILLS, Skill, register

# Tier-A — Scam Shield flagship
from . import read_emails  # noqa: F401
from . import check_url  # noqa: F401
from . import search_scam_intel  # noqa: F401
from . import analyze_email  # noqa: F401
from . import archive_email  # noqa: F401
from . import report_to_family  # noqa: F401

# Tier-B — breadth beats
from . import open_app  # noqa: F401
from . import find_file  # noqa: F401
from . import set_reminder  # noqa: F401
from . import zoom_text  # noqa: F401
from . import play_music  # noqa: F401
from . import system_status  # noqa: F401  # check_wifi / check_battery / adjust_volume
from . import read_screen  # noqa: F401

# Stubs (kept on-brand; logged to unhandled_asks.md)
from . import _stubs  # noqa: F401  # zoom_text / login_site / daily_brief

__all__ = ["SKILLS", "Skill", "register"]
