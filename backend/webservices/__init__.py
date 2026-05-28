"""webservices package: grouped API and JSON endpoints."""

from . import notifications  # re-export for convenience
from . import offers
from . import whatsapp
from . import api as api_pkg

__all__ = ["notifications", "offers", "whatsapp", "api_pkg"]
