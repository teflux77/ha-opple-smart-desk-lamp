"""Constants for the Huawei HiLink cloud (MQTT) integration."""

from typing import Final

DOMAIN: Final = "huawei_hilink_cloud"
PLATFORMS: Final = ["light"]

MIN_COLOR_TEMP_KELVIN: Final = 2700
MAX_COLOR_TEMP_KELVIN: Final = 5700

SERVICE_SWITCH: Final = "switch"
SERVICE_BRIGHTNESS: Final = "brightness"
SERVICE_BACKLIGHT: Final = "backlight"
SERVICE_CCT: Final = "cct"
SERVICE_STUDY_MODE: Final = "studyMode"
SERVICE_LIGHT_MODE: Final = "lightMode"
SERVICE_NIGHT_SWITCH: Final = "nightSwitch"

SIGNAL_DEVICE_UPDATE: Final = f"{DOMAIN}_device_update_{{device_id}}"
