"""Platform for sensor integration."""
from homeassistant.const import DEVICE_CLASS_ENERGY
from homeassistant.const import ENERGY_KILO_WATT_HOUR
from homeassistant.helpers.entity import Entity, generate_entity_id
from homeassistant.components.sensor import ENTITY_ID_FORMAT

from . import DOMAIN, CONF_METER_ID

from random import randint
import logging

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""
    # We only want this platform to be set up via discovery.
    if discovery_info is None:
        return

    meter_id = discovery_info[CONF_METER_ID]

    add_entities([Mojelektro("15min_output", hass, meter_id)])
    add_entities([Mojelektro("15min_input", hass, meter_id)])


class Mojelektro(Entity):
    """Representation of a sensor."""

    type = None

    def __init__(self, type, hass, meter_id):
        """Initialize the sensor."""
        super().__init__()

        self._state = None
        self.type = type
        self.entity_id = generate_entity_id(ENTITY_ID_FORMAT, DOMAIN + "_" + type, hass=hass)
        self._unique_id = "{}-{}".format(meter_id, self.entity_id)

    @property
    def unique_id(self):
        """Return a unique ID."""
        return self._unique_id

    @property
    def name(self):
        """Return the name of the sensor."""
        return "MojElektro " + self.type

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return ENERGY_KILO_WATT_HOUR

    @property
    def device_class(self):
        """Return the device class."""
        return DEVICE_CLASS_ENERGY

    def update(self):
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        self._state = self.hass.data[DOMAIN].get(self.type)
