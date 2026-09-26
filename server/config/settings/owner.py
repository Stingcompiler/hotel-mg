from ._role import check_role
from .base import *  # noqa: F403
from .base import RUNTIME

SKYTOWERS_ROLE = "owner"
check_role(RUNTIME, SKYTOWERS_ROLE)
# apps.core.middleware.OwnerReadOnlyMiddleware refuses every write outside auth/ and owner/ (spec §2).
