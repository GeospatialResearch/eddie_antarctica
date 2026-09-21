# -*- coding: utf-8 -*-
# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antartica/blob/master/LICENSE
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

"""The main web application that serves the Digital Twin to the web through a Rest API."""
from http.client import BAD_REQUEST, NOT_FOUND, OK, SERVICE_UNAVAILABLE
import importlib
import logging

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, make_response, request, send_from_directory
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from rasterio import RasterioIOError

from eddie.check_celery_alive import check_celery_alive
from eddie.digitaltwin.utils import setup_logging
from eddie.discover_plugins import discover_plugins
from eddie.geoserver import get_terria_catalog
from src.eddie_antartica import blueprint as eddie_antartica_blueprint
from src.eddie_antartica.config import EnvVariable
from src.eddie_antartica.sea_ice.sic_data_from_nc import point_series as sic_forecast_point_series
from src.eddie_antartica.sea_ice.sic_data_from_raster import sic_forecast_series
from src.eddie_antartica.wms_point import point_from_get_feature_info
from src.eddie_antartica.ice_sheet.ice_data_from_nc import SERIES_COLUMN, VARIABLES, point_series


setup_logging()

# Initialise flask server object
load_dotenv()
app = Flask(__name__)
CORS(app)

# Serve API documentation
SWAGGER_URL = "/swagger"
API_URL = "/static/api_documentation.yml"
swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={"app_name": "EDDIE (Template)"}
)
app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

# The forecast raster holds unpublished data, so it lives in DATA_DIR rather than the repo.
FORECAST_RASTER = EnvVariable.DATA_DIR / "sic_forecast_8w_timeseries.tif"

eddie_plugins = discover_plugins()
for name, module in eddie_plugins.items():
    importlib.import_module(f"{name}.blueprint")
    app.register_blueprint(module.blueprint.blueprint)

# Flood Resilience specific blueprint
app.register_blueprint(eddie_antartica_blueprint.blueprint)


@app.route('/')
def index() -> Response:
    """
    Ping this endpoint to check that the flask app is running.
    Supported methods: GET

    Returns
    -------
    Response
        The HTTP Response. Expect OK if health check is successful
    """
    return Response("""
    Backend is receiving requests.
    GET /health-check to check if celery workers active.
    GET /swagger to get API documentation.
    """, OK)


@app.route('/health-check')
@check_celery_alive
def health_check() -> Response:
    """
    Ping this endpoint to check that the server is up and running.
    Supported methods: GET

    Returns
    -------
    Response
        The HTTP Response. Expect OK if health check is successful
    """
    return Response("Healthy", OK)


@app.route('/terria-catalog.json')
def terria_catalog() -> Response:
    """
    Return a terria catalog that includes entries for static files and input layers from geoserver.
    Supported methods: GET

    Returns
    -------
    Response
        The HTTP Response. Expect OK if health check is successful
    """
    workspace_groups = get_terria_catalog()["catalog"]
    for workspace_group in workspace_groups:
        workspace_group["isOpen"] = False
    nested_catalog = {"catalog": [{
        "type": "group",
        "name": "Intermediate Layers",
        "isOpen": False,
        "members": workspace_groups,
    }]}
    return make_response(jsonify(nested_catalog), OK)


@app.route('/sea-ice-timeseries')
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
        app.logger.exception("Failed to read sea ice forecast raster")
        return make_response("Forecast raster unavailable", SERVICE_UNAVAILABLE)
    return Response(series.to_csv(index=False), OK, mimetype="text/csv")


@app.route('/sea-ice-timeseries-netcdf')
def sea_ice_timeseries_netcdf() -> Response:
    """
    Return the sea ice concentration forecast for the clicked point, as CSV, from the NetCDF.

    Same data and same two columns as ``/sea-ice-timeseries``, read from the model's own
    NetCDF output rather than from the GeoTIFF exported for GeoServer (issue #35). Both
    routes exist because ``serve_static_files`` publishes ``.tif`` and skips ``.nc``, so
    the WMS layer stays a GeoTIFF while the chart can read the source file.
    Supported methods: GET

    Deliberately not decorated with ``@check_celery_alive``: this route reads a file
    directly and never touches Celery, so a down worker should not turn every chart
    click into a 503.

    Returns
    -------
    Response
        The HTTP Response. Expect OK carrying ``text/csv``; BAD_REQUEST if the
        GetFeatureInfo parameters are missing or malformed; or SERVICE_UNAVAILABLE if the
        file is missing or unreadable.
    """
    try:
        longitude, latitude = point_from_get_feature_info(request.args)
    except (KeyError, ValueError) as request_error:
        return make_response(f"Invalid GetFeatureInfo request: {request_error}", BAD_REQUEST)
    try:
        series = sic_forecast_point_series(longitude, latitude, EnvVariable.FORECAST_NETCDF)
    except (OSError, KeyError):
        app.logger.exception("Failed to read the sea ice forecast NetCDF")
        return make_response("Forecast NetCDF unavailable", SERVICE_UNAVAILABLE)
    return Response(series.to_csv(index=False), OK, mimetype="text/csv")


@app.route("/ice-timeseries/<variable>")
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
        app.logger.exception(f"Failed to read '{variable}' from the ice sheet model dataset")
        return make_response("Ice sheet model dataset unavailable", SERVICE_UNAVAILABLE)
    return Response(series.to_csv(index_label=SERIES_COLUMN), OK, mimetype="text/csv")


@app.route('/terrain/<path:path>')
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
    # a generic static response needs an explicit Content-Encoding or Cesium can't decode them.
    if path.endswith(".terrain"):
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Type"] = "application/vnd.quantized-mesh"
    return response


@app.route('/terrain/layer.json')
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


# Development server
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

# Production server
if __name__ != '__main__':
    # Set gunicorn loggers to work with flask
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
