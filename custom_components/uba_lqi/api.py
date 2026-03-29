"""API client for the Umweltbundesamt air quality API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any

from aiohttp import ClientError, ClientSession

from .const import API_BASE_URLS, API_TIMEOUT_SECONDS, AQI_LABELS_DE, DEFAULT_LANGUAGE

_LOGGER = logging.getLogger(__name__)


class UbaLqiApiError(RuntimeError):
    """Raised when the API request fails."""


@dataclass(slots=True)
class StationMeta:
    station_id: str
    code: str
    name: str
    city: str | None
    synonym: str | None
    first_active: str | None
    last_active: str | None
    longitude: float | None
    latitude: float | None
    network_id: str | None
    station_setting_id: str | None
    station_type_id: str | None
    network_code: str | None
    network_name: str | None
    station_setting_name: str | None
    station_setting_short: str | None
    station_type_name: str | None
    street: str | None
    street_number: str | None
    zip_code: str | None


@dataclass(slots=True)
class ComponentMeta:
    component_id: str
    code: str
    symbol: str | None
    unit: str | None
    name: str | None


@dataclass(slots=True)
class ComponentReading:
    component_id: str
    code: str | None
    name: str | None
    unit: str | None
    value: float | None
    index: int | None
    threshold_progress: float | None


@dataclass(slots=True)
class StationReading:
    station_id: str
    start_time: str
    end_time: str | None
    index: int | None
    label: str | None
    incomplete: int | None
    components: dict[str, ComponentReading]


class UbaLqiApiClient:
    """Async client for the UBA air quality API."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, */*;q=0.8",
            "User-Agent": "HomeAssistant-UBA-LQI/0.1.0",
        }
        last_error: str | None = None

        for base_url in API_BASE_URLS:
            url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=API_TIMEOUT_SECONDS,
                ) as response:
                    text = await response.text()
                    response.raise_for_status()
            except (TimeoutError, ClientError) as err:
                last_error = f"{url}: {err}"
                _LOGGER.debug("Request against %s failed: %s", url, err)
                continue

            try:
                data = json.loads(text)
            except json.JSONDecodeError as err:
                last_error = f"{url}: invalid JSON payload"
                _LOGGER.debug("Invalid JSON from %s: %s / %.300r", url, err, text)
                continue

            if not isinstance(data, dict):
                last_error = f"{url}: unexpected payload type"
                _LOGGER.debug("Unexpected payload type from %s: %s", url, type(data))
                continue
            return data

        raise UbaLqiApiError(last_error or "API request failed")

    async def async_get_airquality_metadata(
        self,
        *,
        lang: str = DEFAULT_LANGUAGE,
        date_from: str,
        date_to: str,
        time_from: int = 1,
        time_to: int = 24,
    ) -> tuple[dict[str, StationMeta], dict[str, ComponentMeta]]:
        payload = await self._get_json(
            "/meta/json",
            {
                "use": "airquality",
                "lang": lang,
                "date_from": date_from,
                "date_to": date_to,
                "time_from": time_from,
                "time_to": time_to,
            },
        )

        stations_raw = _extract_mapping(payload, "stations")
        components_raw = _extract_mapping(payload, "components")
        stations = {str(key): _parse_station_meta(value) for key, value in stations_raw.items()}
        components = {str(key): _parse_component_meta(value) for key, value in components_raw.items()}
        return stations, components

    async def async_get_station_airquality(
        self,
        *,
        station_id: str,
        component_map: dict[str, ComponentMeta],
        lang: str = DEFAULT_LANGUAGE,
        days_back: int = 1,
    ) -> StationReading | None:
        today = date.today()
        date_from = (today - timedelta(days=days_back)).isoformat()
        date_to = today.isoformat()

        payload = await self._get_json(
            "/airquality/json",
            {
                "lang": lang,
                "station": station_id,
                "date_from": date_from,
                "date_to": date_to,
                "time_from": 1,
                "time_to": 24,
            },
        )

        data = _extract_mapping(payload, "data")
        station_payload = data.get(str(station_id))
        if not isinstance(station_payload, dict) or not station_payload:
            return None

        latest_start = max(
            station_payload.keys(),
            key=lambda value: datetime.strptime(value, "%Y-%m-%d %H:%M:%S"),
        )
        latest_record = station_payload[latest_start]
        if not isinstance(latest_record, list):
            return None

        overall_index = _coerce_int(_idx(latest_record, 1))
        incomplete = _coerce_int(_idx(latest_record, 2))
        components: dict[str, ComponentReading] = {}

        for comp_raw in latest_record[3:]:
            if not isinstance(comp_raw, list) or len(comp_raw) < 4:
                continue
            component_id = str(_idx(comp_raw, 0) or "")
            meta = component_map.get(component_id)
            components[component_id] = ComponentReading(
                component_id=component_id,
                code=meta.code if meta else None,
                name=meta.name if meta else None,
                unit=meta.unit if meta else None,
                value=_coerce_float(_idx(comp_raw, 1)),
                index=_coerce_int(_idx(comp_raw, 2)),
                threshold_progress=_coerce_float(_idx(comp_raw, 3)),
            )

        return StationReading(
            station_id=str(station_id),
            start_time=str(latest_start),
            end_time=_coerce_str_or_none(_idx(latest_record, 0)),
            index=overall_index,
            label=AQI_LABELS_DE.get(overall_index),
            incomplete=incomplete,
            components=components,
        )


def default_metadata_window() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=7)).isoformat(), today.isoformat()


def distance_km(latitude_1: float, longitude_1: float, latitude_2: float | None, longitude_2: float | None) -> float:
    if latitude_2 is None or longitude_2 is None:
        return float("inf")
    earth_radius_km = 6371.0088
    lat1 = radians(latitude_1)
    lon1 = radians(longitude_1)
    lat2 = radians(latitude_2)
    lon2 = radians(longitude_2)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(haversine))


def select_nearby_stations(
    stations: dict[str, StationMeta],
    latitude: float,
    longitude: float,
    radius_km: float,
    max_candidates: int,
) -> list[tuple[StationMeta, float]]:
    ranked: list[tuple[StationMeta, float]] = []
    for station in stations.values():
        if station.latitude is None or station.longitude is None:
            continue
        ranked.append((station, distance_km(latitude, longitude, station.latitude, station.longitude)))
    ranked.sort(key=lambda item: (item[1], item[0].name.casefold(), item[0].station_id))
    within_radius = [item for item in ranked if item[1] <= radius_km]
    return within_radius[:max_candidates] if within_radius else ranked[:max_candidates]


def _extract_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    raw = payload.get(key)
    return raw if isinstance(raw, dict) else {}


def _parse_station_meta(raw: Any) -> StationMeta:
    return StationMeta(
        station_id=str(_idx(raw, 0) or ""),
        code=str(_idx(raw, 1) or ""),
        name=str(_idx(raw, 2) or "Unbekannt"),
        city=_coerce_str_or_none(_idx(raw, 3)),
        synonym=_coerce_str_or_none(_idx(raw, 4)),
        first_active=_coerce_str_or_none(_idx(raw, 5)),
        last_active=_coerce_str_or_none(_idx(raw, 6)),
        longitude=_coerce_float(_idx(raw, 7)),
        latitude=_coerce_float(_idx(raw, 8)),
        network_id=_coerce_str_or_none(_idx(raw, 9)),
        station_setting_id=_coerce_str_or_none(_idx(raw, 10)),
        station_type_id=_coerce_str_or_none(_idx(raw, 11)),
        network_code=_coerce_str_or_none(_idx(raw, 12)),
        network_name=_coerce_str_or_none(_idx(raw, 13)),
        station_setting_name=_coerce_str_or_none(_idx(raw, 14)),
        station_setting_short=_coerce_str_or_none(_idx(raw, 15)),
        station_type_name=_coerce_str_or_none(_idx(raw, 16)),
        street=_coerce_str_or_none(_idx(raw, 17)),
        street_number=_coerce_str_or_none(_idx(raw, 18)),
        zip_code=_coerce_str_or_none(_idx(raw, 19)),
    )


def _parse_component_meta(raw: Any) -> ComponentMeta:
    return ComponentMeta(
        component_id=str(_idx(raw, 0) or ""),
        code=str(_idx(raw, 1) or ""),
        symbol=_coerce_str_or_none(_idx(raw, 2)),
        unit=_coerce_str_or_none(_idx(raw, 3)),
        name=_coerce_str_or_none(_idx(raw, 4)),
    )


def _idx(raw: Any, idx: int) -> Any:
    if isinstance(raw, dict):
        return raw.get(str(idx), raw.get(idx))
    if isinstance(raw, list) and idx < len(raw):
        return raw[idx]
    return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_str_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)
