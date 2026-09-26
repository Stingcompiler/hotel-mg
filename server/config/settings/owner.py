from ._role import check_role
from .base import *  # noqa: F403
from .base import RUNTIME

SKYTOWERS_ROLE = "owner"
check_role(RUNTIME, SKYTOWERS_ROLE)
# The owner read-only middleware (spec §2) is added in phase B4.
