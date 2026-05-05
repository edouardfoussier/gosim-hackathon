"""Skill registry. Importing this module registers all V1 skills."""

from .registry import SKILLS, Skill, register

# eager-import each skill so they self-register on the registry
from . import open_app  # noqa: F401
from . import find_file  # noqa: F401
from . import set_reminder  # noqa: F401
from . import _stubs  # noqa: F401  # read_emails / zoom_text / login_site / daily_brief stubs

__all__ = ["SKILLS", "Skill", "register"]
