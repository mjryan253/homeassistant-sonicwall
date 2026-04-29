"""Constants for sonicwall."""

from logging import Logger, getLogger

LOGGER: Logger = getLogger(__package__)

DOMAIN = "sonicwall"
ATTRIBUTION = "Data provided by SonicWall SonicOS API"

DEFAULT_PORT = 443
DEFAULT_VERIFY_SSL = False
DEFAULT_SCAN_INTERVAL_SECONDS = 30

CONF_VERIFY_SSL = "verify_ssl"
