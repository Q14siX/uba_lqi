"""Coordinator for the UBA Luftqualitätsindex (LQI) integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ComponentMeta, UbaLqiApiClient, UbaLqiApiError, distance_km
from .const import (
    CONF_COMPONENT_DETAILS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SELECTED_STATIONS,
    CONF_STATION_DETAILS,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class UbaLqiDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetch and cache data from the UBA API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, api: UbaLqiApiClient, config_entry: ConfigEntry) -> None:
        self.api = api
        self.config_entry = config_entry
        self.component_map = {
            str(component_id): ComponentMeta(
                component_id=str(component_id),
                code=str(component.get("code") or ""),
                symbol=component.get("symbol"),
                unit=component.get("unit"),
                name=component.get("name"),
            )
            for component_id, component in self.config.get(CONF_COMPONENT_DETAILS, {}).items()
        }
        update_minutes = self.config.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=int(update_minutes)),
        )

    @property
    def config(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            station_ids = [str(station_id) for station_id in self.config.get(CONF_SELECTED_STATIONS, [])]
            readings = await asyncio.gather(
                *[
                    self.api.async_get_station_airquality(station_id=station_id, component_map=self.component_map)
                    for station_id in station_ids
                ]
            )
        except UbaLqiApiError as err:
            raise UpdateFailed(str(err)) from err

        latitude = float(self.config[CONF_LATITUDE])
        longitude = float(self.config[CONF_LONGITUDE])
        station_details = self.config.get(CONF_STATION_DETAILS, {})

        data: dict[str, dict[str, Any]] = {}
        for station_id, reading in zip(station_ids, readings, strict=False):
            if reading is None:
                continue
            station_info = station_details.get(station_id, {})
            station_lat = station_info.get("latitude")
            station_lon = station_info.get("longitude")
            data[station_id] = {
                "station_id": station_id,
                "index": reading.index,
                "label": reading.label,
                "incomplete": reading.incomplete,
                "start_time": reading.start_time,
                "end_time": reading.end_time,
                "components": {
                    comp_id: {
                        "component_id": comp.component_id,
                        "code": comp.code,
                        "name": comp.name,
                        "unit": comp.unit,
                        "value": comp.value,
                        "index": comp.index,
                        "threshold_progress": comp.threshold_progress,
                    }
                    for comp_id, comp in reading.components.items()
                },
                "distance_km": None if station_lat is None or station_lon is None else round(distance_km(latitude, longitude, float(station_lat), float(station_lon)), 2),
            }
        return data
