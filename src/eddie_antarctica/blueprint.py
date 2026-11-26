# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antarctica/blob/master/LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Endpoints this plugin adds to the core Flask app.

The core app owns ``/``, ``/health-check``, ``/terria-catalog.json`` and ``/wps``.
"""
from http.client import BAD_REQUEST, NOT_FOUND, OK, SERVICE_UNAVAILABLE

from flask import Blueprint, Response, current_app, make_response, request, send_from_directory
from rasterio import RasterioIOError

from eddie.check_celery_alive import check_celery_alive

from eddie_antarctica import tasks
from eddie_antarctica.config import EnvVariable
from eddie_antarctica.ice_sheet.ice_data_from_nc import SERIES_COLUMN, VARIABLES, point_series
from eddie_antarctica.sea_ice.model.sic_data_from_raster import sic_forecast_series
from eddie_antarctica.sea_ice.sea_ice_forecast_layer import CHART_METHODS, TIMESERIES_ROUTE
from eddie_antarctica.wms_point import point_from_get_feature_info

blueprint = Blueprint('eddie_antarctica', __name__)

# The forecast raster holds unpublished data, so it lives in DATA_DIR rather than the repo.
FORECAST_RASTER = EnvVariable.DATA_DIR / "sic_forecast_8w_timeseries.tif"


@blueprint.route(TIMESERIES_ROUTE)
@check_celery_alive
def sea_ice_forecast_timeseries() -> Response:
    """
    Return the sea ice forecast for the clicked point, as CSV, for layers the sea_ice_forecast process adds.

    Terria calls this instead of GeoServer for layers marked ``supportsGetTimeseries``, sending a WMS
    GetFeatureInfo-shaped query.
    Supported methods: GET

    Returns
    -------
    Response
        OK carrying ``text/csv``, or BAD_REQUEST if the GetFeatureInfo parameters are missing or malformed, or
        ``interpolations`` names no display mode.
    """
    try:
        longitude, latitude = point_from_get_feature_info(request.args)
        # No interpolations: GeoServer draws its default, nearest neighbour, as raw layers added before it was sent.
        method = CHART_METHODS[request.args.get("interpolations") or "nearest neighbor"]
    except (KeyError, ValueError) as request_error:
        return make_response(f"Invalid GetFeatureInfo request: {request_error}", BAD_REQUEST)
    csv = tasks.sea_ice_forecast_point_series.delay(longitude, latitude, method).get()
    return Response(csv, OK, mimetype="text/csv")


@blueprint.route('/sea-ice-timeseries')
def sea_ice_timeseries() -> Response:
    """
    Return the sea ice concentration forecast for the clicked point, as CSV.

    TerriaJS calls this instead of GeoServer for layers marked with
    ``supportsGetTimeseries``, sending a WMS GetFeatureInfo-shaped query, and charts the
    two-column CSV it gets back: column 1 is the x axis, column 2 the y axis.
    Supported methods: GET

    Deliberately not decorated with ``@check_celery_alive``: this route reads a raster
    directly and never touches Celery, so a down worker should not turn every chart
    click into a 503.

    Returns
    -------
    Response
        The HTTP Response. Expect OK carrying ``text/csv``, or BAD_REQUEST if the
        GetFeatureInfo parameters are missing or malformed.
    """
    try:
        longitude, latitude = point_from_get_feature_info(request.args)
    except (KeyError, ValueError) as request_error:
        return make_response(f"Invalid GetFeatureInfo request: {request_error}", BAD_REQUEST)
    try:
        series = sic_forecast_series(longitude, latitude, FORECAST_RASTER)
    except RasterioIOError:
        current_app.logger.exception("Failed to read sea ice forecast raster")
        return make_response("Forecast raster unavailable", SERVICE_UNAVAILABLE)
    return Response(series.to_csv(index=False), OK, mimetype="text/csv")


@blueprint.route("/ice-timeseries/<variable>")
def ice_timeseries(variable: str) -> Response:
    """
    Return every model run's series for the clicked point of ice_ds.nc, as CSV.

    TerriaJS calls this instead of GeoServer for layers marked with
    ``supportsGetTimeseries``, and charts the CSV: column one is the x axis, the rest
    are series. GeoServer can draw NetCDF but not chart it -- the ncWMS extension that
    would is not installed -- so the pixels come from GeoServer and the chart from here.
    Supported methods: GET

    Deliberately not decorated with ``@check_celery_alive``: this route reads a file
    directly and never touches Celery, so a down worker should not turn every chart
    click into a 503.

    Parameters
    ----------
    variable : str
        Which of ``VARIABLES`` to chart, such as ``thk``.

    Returns
    -------
    Response
        The HTTP Response. Expect OK carrying ``text/csv``; NOT_FOUND for an unknown
        variable; BAD_REQUEST if the GetFeatureInfo parameters are missing or malformed;
        or SERVICE_UNAVAILABLE if the file is missing or unreadable.
    """
    if variable not in VARIABLES:
        return make_response(f"ice_ds.nc holds {sorted(VARIABLES)}, not '{variable}'", NOT_FOUND)
    try:
        longitude, latitude = point_from_get_feature_info(request.args)
    except (KeyError, ValueError) as request_error:
        return make_response(f"Invalid GetFeatureInfo request: {request_error}", BAD_REQUEST)
    try:
        series = point_series(longitude, latitude, variable)
    except (OSError, KeyError):
        current_app.logger.exception(f"Failed to read '{variable}' from the ice sheet model dataset")
        return make_response("Ice sheet model dataset unavailable", SERVICE_UNAVAILABLE)
    return Response(series.to_csv(index_label=SERIES_COLUMN), OK, mimetype="text/csv")


@blueprint.route('/terrain/<path:path>')
def serve_terrain(path: str) -> Response:
    """
    Serve a self-hosted quantized-mesh terrain tile, replacing Cesium Ion terrain.
    Supported methods: GET

    Parameters
    ----------
    path : str
        Path to the requested tile or layer.json, relative to TERRAIN_DIR.

    Returns
    -------
    Response
        The requested file, with quantized-mesh headers set for `.terrain` tiles.
    """
    response = send_from_directory(EnvVariable.TERRAIN_DIR, path)
    # ctb-tile writes .terrain tiles pre-gzip-compressed on disk (no .gz extension) -
    # a generic static response needs an explicit Content-Encoding or Cesium can't decode them.
    if path.endswith(".terrain"):
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Type"] = "application/vnd.quantized-mesh"
    return response


@blueprint.route('/terrain/layer.json')
def terrain_root() -> Response:
    """
    Serve the terrain tileset's layer.json manifest at the conventional root path.
    Supported methods: GET
    Returns
    -------
    Response
        The layer.json manifest.
    """
    return serve_terrain("layer.json")
