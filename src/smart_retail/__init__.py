"""Smart Retail Checkout application package."""

import logging

__version__ = "1.0.0"

# Library modules stay quiet until the application configures root handlers.
logging.getLogger(__name__).addHandler(logging.NullHandler())
