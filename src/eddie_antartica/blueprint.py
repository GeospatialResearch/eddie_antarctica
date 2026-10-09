"""Endpoints and flask configuration for this template example app"""
from http.client import BAD_REQUEST, OK
import os
import pathlib

from flask import Blueprint, Response, make_response, request

from eddie.check_celery_alive import check_celery_alive

os.environ.pop("Path", None)
# See issue https://github.com/GeospatialResearch/eddie_floodresilience/issues/1 for reason behind disabled QA
from src.eddie_antartica import tasks  # pylint: disable=wrong-import-position # noqa: E402
from src.eddie_antartica.sea_ice.sea_ice_forecast_layer import (  # pylint: disable=wrong-import-position # noqa: E402,E501
    TIMESERIES_ROUTE)
from src.eddie_antartica.sea_ice.sea_ice_forecast_process_service import (  # pylint: disable=wrong-import-position # noqa: E402,E501
    SeaIceForecastProcessService)
from src.eddie_antartica.wms_point import point_from_get_feature_info  # pylint: disable=wrong-import-position # noqa: E402,E501
from pywps import Service  # pylint: disable=wrong-import-position,wrong-import-order # noqa: E402

blueprint = Blueprint('eddie_antartica', __name__)
processes = [
    SeaIceForecastProcessService(),
]

process_descriptor = {process.identifier: process.abstract for process in processes}
service = Service(processes, ['src/pywps.cfg'])
for working_dir in ["workdir", "outputs", "logs"]:
    path = pathlib.Path("./tmp/pywps") / working_dir
    path.mkdir(exist_ok=True, parents=True)


@blueprint.route('/wps', methods=['GET', 'POST'])
@check_celery_alive
def wps() -> Service:
    """
    End point for OGC WebProcessingService spec, allowing clients such as TerriaJS to request processing.

    Returns
    -------
    Service
        The PyWPS WebProcessing Service instance
    """
    return service


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
        OK carrying ``text/csv``, or BAD_REQUEST if the GetFeatureInfo parameters are missing or malformed.
    """
    try:
        longitude, latitude = point_from_get_feature_info(request.args)
    except (KeyError, ValueError) as request_error:
        return make_response(f"Invalid GetFeatureInfo request: {request_error}", BAD_REQUEST)
    csv = tasks.sea_ice_forecast_point_series.delay(longitude, latitude).get()
    return Response(csv, OK, mimetype="text/csv")
