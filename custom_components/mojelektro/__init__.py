import logging
import voluptuous as vol
from datetime import timedelta

import homeassistant.helpers.config_validation as cv
from homeassistant.components.recorder.statistics import statistic_during_period
from homeassistant.helpers.event import track_time_interval

from .moj_elektro_api import MojElektroApi

"""Example Load Platform integration."""
DOMAIN = 'mojelektro'

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(hours=24)

CONF_METER_ID = 'meter_id'

ACCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_METER_ID): cv.string
    }
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: ACCOUNT_SCHEMA}, extra=vol.ALLOW_EXTRA)

def setup(hass, config):
    _LOGGER.info("SETUP...")
    """Your controller/hub specific code."""
    # Data that you want to share with your platforms
    hass.data[DOMAIN] = {  }

    conf = config.get(DOMAIN)

    api = MojElektroApi(conf.get(CONF_METER_ID), hass)

    def refresh(event_time):
        """Refresh"""
        _LOGGER.debug("Refreshing...")
        api.updateData()

    refresh(0)

    track_time_interval(hass, refresh, SCAN_INTERVAL)

    return True
