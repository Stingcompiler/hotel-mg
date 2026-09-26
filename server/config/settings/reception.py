from ._role import check_role
from .base import *  # noqa: F403
from .base import RUNTIME

SKYTOWERS_ROLE = "reception"
check_role(RUNTIME, SKYTOWERS_ROLE)
