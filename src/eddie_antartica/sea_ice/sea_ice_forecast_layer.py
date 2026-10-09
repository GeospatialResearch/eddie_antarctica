"""
The plain functions behind the sea ice forecast WPS process, kept free of Celery and env vars so they test alone.

One forecast file, never renewed, is served: each week gets its own stable layer, so rerunning the process for
a week replaces that layer rather than adding another.
"""
import json

#: The SLD every week's layer is drawn with, already in ``src/static/geo``.
STYLE = "sic_forecast_8w"

#: Chart route in ``src/eddie_antartica/blueprint.py``; Terria appends the GetFeatureInfo query to it.
TIMESERIES_ROUTE = "/sea-ice-forecast-timeseries"


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


def catalog_item(week: int, date: str, geoserver_url: str, backend_url: str) -> str:
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

    Returns
    -------
    str
        A WMS catalog member, in format ``application/vnd.terriajs.catalog-member+json``.
    """
    return json.dumps({
        "type": "wms",
        "name": f"Sea ice concentration -- week {week} ({date})",
        "url": f"{geoserver_url}/geoserver/static_files/wms",
        "layers": layer_name(week),
        "styles": STYLE,
        "supportsGetTimeseries": True,
        "getFeatureInfoUrl": f"{backend_url}{TIMESERIES_ROUTE}",
        "parameters": {"interpolations": "bilinear"},
    })
