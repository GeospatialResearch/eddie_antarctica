"""Endpoints and flask configuration for this template example app"""
from http.client import ACCEPTED
import os
import pathlib

from flask import Blueprint, jsonify, make_response, Response

from eddie.check_celery_alive import check_celery_alive
from src.eddie_antartica import tasks

os.environ.pop("Path", None)
# See issue https://github.com/GeospatialResearch/eddie_floodresilience/issues/1 for reason behind disabled QA
from pywps import Service  # pylint: disable=wrong-import-position,wrong-import-order # noqa: E402

blueprint = Blueprint('eddie_antartica', __name__)
processes = [
    # Place any imported PyWPS processes here
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
