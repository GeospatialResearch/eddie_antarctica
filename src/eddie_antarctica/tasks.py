# -*- coding: utf-8 -*-
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

"""
Runs backend tasks using Celery. Allowing for multiple long-running tasks to complete in the background.
Allows the frontend to send tasks and retrieve status later.
"""
import logging
import pathlib

from celery import chain, signals
from celery.schedules import crontab
from celery.worker.consumer import Consumer
import geopandas as gpd

from eddie.digitaltwin import retrieve_from_instructions
from eddie.digitaltwin.utils import setup_logging
from eddie.tasks import OnFailureStateTask, app
from eddie_antarctica.config import EnvVariable
from eddie_antarctica.run_all import DEFAULT_MODULES_TO_PARAMETERS
from eddie_antarctica.sea_ice.inputs import land_mask_from_nsidc, main_sea_ice_inputs
from eddie_antarctica.sea_ice.model import serve_model, sic_gnn_model
from eddie_antarctica.sea_ice.model.sic_data_from_nc import latest_forecast, point_series
from eddie_antarctica.sea_ice.sea_ice_enum import ChartMethod

setup_logging()
log = logging.getLogger(__name__)

# Run by the beat embedded in the worker (-B in celery_worker_entrypoint.sh), Monday 03:00 New Zealand time.
# ERA5T trails real time by about five days, so main_sea_ice_inputs' whole-week trim drops any partial week.
app.conf.timezone = "Pacific/Auckland"
app.conf.beat_schedule = {
    "weekly-sea-ice-forecast": {
        "task": "eddie_antarctica.tasks.refresh_sea_ice_forecast",
        "schedule": crontab(day_of_week="mon", hour=3, minute=0),
    },
}


@signals.worker_ready.connect
def on_startup(sender: Consumer, **_kwargs: None) -> None:  # pylint: disable=missing-param-doc
    """
    Initialise database, runs when Celery instance is ready.

    Parameters
    ----------
    sender : Consumer
        The Celery worker node instance
    """
    with sender.app.connection() as conn:
        # Gather area of interest from file.
        aoi_wkt = gpd.read_file("selected_polygon.geojson").to_crs(4326).geometry[0].wkt
        # Send a task to initialise this area of interest.
        instruction_json_path = DEFAULT_MODULES_TO_PARAMETERS[retrieve_from_instructions]["instruction_json_path"]
        sender.app.send_task("eddie.tasks.add_base_data_to_db", args=[aoi_wkt, instruction_json_path], connection=conn)


@app.task(base=OnFailureStateTask)
def preprocess_sea_ice_inputs() -> str:
    """
    Fetch the latest NSIDC + ERA5 and write the sea ice model's weekly inputs.

    Returns
    -------
    str
        The written ``sic_inputs_<YYYY-MM-DD>/`` folder. A path, not data: Celery passes results as JSON through Redis.
    """
    return main_sea_ice_inputs.main(EnvVariable.SEA_ICE_INPUTS_DIR, EnvVariable.SIC_CLIMATOLOGY).as_posix()


@app.task(base=OnFailureStateTask)
def forecast_sea_ice(inputs_path: str) -> str:
    """
    Run the sea ice model on the inputs, write the forecast and publish its map layer.

    Parameters
    ----------
    inputs_path : str
        The inputs folder ``preprocess_sea_ice_inputs`` returned.

    Returns
    -------
    str
        The written ``sic_forecast_<weeks>w_<week 1>.nc``, which the chart route now reads.
    """
    nc_path = sic_gnn_model.main(pathlib.Path(inputs_path), EnvVariable.SIC_MODEL_DIR, EnvVariable.FORECAST_NETCDF_DIR)
    serve_model.add_forecast_to_geoserver(nc_path, EnvVariable.SIC_MODEL_DIR / land_mask_from_nsidc.FILE_NAME)
    return nc_path.as_posix()


@app.task(base=OnFailureStateTask)
def refresh_sea_ice_forecast() -> None:
    """Fetch this week's inputs, then forecast from them. Beat schedules one task, so this one builds the chain."""
    chain(preprocess_sea_ice_inputs.s(), forecast_sea_ice.s()).delay()


@app.task(base=OnFailureStateTask)
def sea_ice_forecast_point_series(longitude: float, latitude: float,
                                  method: ChartMethod = ChartMethod.LINEAR) -> str:
    """
    Chart the newest forecast at a point: the latest in ``FORECAST_NETCDF_DIR``, else ``FORECAST_NETCDF_LATEST``.

    Parameters
    ----------
    longitude : float
        Clicked longitude in degrees.
    latitude : float
        Clicked latitude in degrees.
    method : ChartMethod
        ``LINEAR`` charts the blend the smoothed map draws, ``NEAREST`` the clicked model cell. A ``LINEAR`` chart
        is empty where the smoothed map cuts out land.

    Returns
    -------
    str
        The two-column CSV Terria plots: time, then concentration; just the header off the grid.
    """
    forecast = latest_forecast(EnvVariable.FORECAST_NETCDF_DIR) or EnvVariable.FORECAST_NETCDF_LATEST
    # Celery's JSON serialiser delivers the member as its plain string value, so restore the member.
    series = point_series(longitude, latitude, forecast, ChartMethod(method),
                          nsidc_path=EnvVariable.SIC_MODEL_DIR / land_mask_from_nsidc.FILE_NAME)
    return series.to_csv(index=False)
