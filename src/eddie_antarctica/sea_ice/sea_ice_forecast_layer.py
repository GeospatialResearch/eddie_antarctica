"""
The plain functions behind the sea ice forecast WPS process, kept free of Celery and env vars so they test alone.

Each forecast run publishes every week as its own stable layer (``serve_model``), so the process only reads the
week's date and points Terria at that layer: nothing is drawn per request, and the layer is always the newest forecast.
"""
import json
import pathlib
from typing import Union

import pandas as pd
import xarray as xr

from src.eddie_antarctica.sea_ice.sea_ice_enum import ChartMethod

# The SLD every week's layer is drawn with, already in ``src/static/geo``.
STYLE = "sic_forecast_8w"

# Chart route in ``src/eddie_antarctica/blueprint.py``; Terria appends the GetFeatureInfo query to it.
TIMESERIES_ROUTE = "/sea-ice-forecast-timeseries"

# Form label -> GeoServer ``interpolations`` value; the first entry is the form default. The map is always
# resampled, and nearest neighbour is the closest to the raw cells. Values must stay exact GeoServer values:
# any other string throws in GeoServer instead of drawing.
DISPLAY_LABELS = {"Raw 1° cells": "nearest neighbor", "Smoothed": "bilinear"}

# GeoServer ``interpolations`` from a click -> how the chart reads the forecast; anything else is the route's 400.
CHART_METHODS = {"nearest neighbor": ChartMethod.NEAREST, "bilinear": ChartMethod.LINEAR}


def layer_name(week: int, raw: bool = False) -> str:
    """
    Name the GeoServer layer for one forecast week.

    Parameters
    ----------
    week : int
        Forecast week, 1-based.
    raw : bool
       True for the week's raw layer, the model output as it is; False for the layer drawn smoothed.

    Returns
    -------
    str
        ``sic_forecast_week<week>``, or ``sic_forecast_week<week>_raw``.
    """
    return f"sic_forecast_week{week}{'_raw' if raw else ''}"


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


def catalog_item(week: int, date: str, geoserver_url: str, backend_url: str,
                 interpolation: str = "nearest neighbor") -> str:
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
    interpolation : str
        A ``DISPLAY_LABELS`` value: which week layer to draw, raw or smoothed. Terria sends it with every
        click, so the chart reads the forecast the way the map draws it. Defaults to the raw cells.

    Returns
    -------
    str
        A WMS catalog member, in format ``application/vnd.terriajs.catalog-member+json``.
    """
    return json.dumps({
        "type": "wms",
        "name": f"Sea ice concentration -- week {week} ({date})",
        "url": f"{geoserver_url}/geoserver/static_files/wms",
        "layers": layer_name(week, raw=CHART_METHODS[interpolation] == ChartMethod.NEAREST),
        "styles": STYLE,
        "crs": "EPSG:4326",
        "supportsGetTimeseries": True,
        "getFeatureInfoUrl": f"{backend_url}{TIMESERIES_ROUTE}",
        "getFeatureInfoParameters": {"interpolations": interpolation},
    })
