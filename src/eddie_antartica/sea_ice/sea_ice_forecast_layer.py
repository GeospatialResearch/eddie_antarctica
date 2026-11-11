"""
The plain functions behind the sea ice forecast WPS process, kept free of Celery and env vars so they test alone.

Each forecast run publishes every week as its own stable layer (``serve_model``), so the process only reads the
week's date and points Terria at that layer: nothing is drawn per request, and the layer is always the newest forecast.
"""
import json
import pathlib
import re
from typing import Optional, Union

import pandas as pd
import xarray as xr

#: The SLD every week's layer is drawn with, already in ``src/static/geo``.
STYLE = "sic_forecast_8w"

#: Chart route in ``src/eddie_antartica/blueprint.py``; Terria appends the GetFeatureInfo query to it.
TIMESERIES_ROUTE = "/sea-ice-forecast-timeseries"

#: Name of the display dropdown on the sea_ice_forecast process form.
DISPLAY_NAME = "Display"

#: GeoServer ``interpolations`` value -> (form label, chart method). The first entry is the default.
#: None sends no ``interpolations`` at all, so GeoServer draws the cells as they are. Any other key must stay an
#: exact GeoServer value: any other string throws in GeoServer instead of drawing.
DISPLAY_MODES = {
    None: ("Raw 1° cells", "nearest"),
    "bilinear": ("Smoothed", "linear"),
}

#: Form label -> GeoServer ``interpolations`` value, in the same order.
DISPLAY_LABELS = {label: interpolation for interpolation, (label, _) in DISPLAY_MODES.items()}


def layer_name(week: int) -> str:
    """
    Name the GeoServer layer for one forecast week.

    Parameters
    ----------
    week : int
        Forecast week, 1-based.

    Returns
    -------
    str
        ``sic_forecast_week<week>``.
    """
    return f"sic_forecast_week{week}"


def layer_week(layers: Optional[str]) -> Optional[int]:
    """
    Read the forecast week back from a ``layer_name``, as a click's GetFeatureInfo ``layers`` sends it.

    Parameters
    ----------
    layers : Optional[str]
        The ``layers`` value of the click.

    Returns
    -------
    Optional[int]
        The 1-based week, or None if ``layers`` is not one week's layer.
    """
    week = re.fullmatch(r"sic_forecast_week([1-9][0-9]*)", layers or "")
    return int(week[1]) if week else None


def week_date(forecast: Union[str, pathlib.Path], week: int) -> str:
    """
    Read one forecast week's date, for the layer's title.

    Parameters
    ----------
    forecast : Union[str, pathlib.Path]
        A forecast NetCDF with a ``time`` coordinate, one step per week.
    week : int
        Forecast week, 1-based.

    Returns
    -------
    str
        The week's date, ``YYYY-MM-DD``.
    """
    with xr.open_dataset(forecast) as dataset:
        return pd.Timestamp(dataset["time"].values[week - 1]).strftime("%Y-%m-%d")


def chart_method(interpolation: Optional[str]) -> str:
    """
    Find the chart method for the map's display mode, so a click charts what the map draws.

    Parameters
    ----------
    interpolation : Optional[str]
        The ``interpolations`` value Terria sends with the click. Absent or empty charts the clicked cell, as the
        raw display sends none.

    Returns
    -------
    str
        The ``xarray`` interpolation method: ``"nearest"`` or ``"linear"``.

    Raises
    ------
    KeyError
        If the value has no chart mode, such as GeoServer's ``bicubic``.
    """
    return DISPLAY_MODES[interpolation or None][1]


def catalog_item(week: int, date: str, geoserver_url: str, backend_url: str,
                 interpolation: Optional[str] = next(iter(DISPLAY_MODES))) -> str:
    """
    Build the Terria catalog member JSON for one published forecast week.

    Parameters
    ----------
    week : int
        Forecast week, 1-based.
    date : str
        The week's date from the forecast's ``time``, ``YYYY-MM-DD``.
    geoserver_url : str
        Public GeoServer root, e.g. ``http://localhost:8088``.
    backend_url : str
        Public backend root, e.g. ``http://localhost:5000``.
    interpolation : Optional[str]
        A ``DISPLAY_MODES`` key: how GeoServer draws the layer. Terria sends it with every click too, so the chart
        follows the map. None sets no interpolation on the layer. Defaults to the first mode.

    Returns
    -------
    str
        A WMS catalog member, in format ``application/vnd.terriajs.catalog-member+json``.
    """
    parameters = {"parameters": {"interpolations": interpolation}} if interpolation else {}
    return json.dumps({
        "type": "wms",
        "name": f"Sea ice concentration -- week {week} ({date})",
        "url": f"{geoserver_url}/geoserver/static_files/wms",
        "layers": layer_name(week),
        "styles": STYLE,
        "crs": "EPSG:4326",
        "supportsGetTimeseries": True,
        "getFeatureInfoUrl": f"{backend_url}{TIMESERIES_ROUTE}",
        **parameters,
    })
