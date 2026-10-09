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

"""
Runs backend tasks using Celery. Allowing for multiple long-running tasks to complete in the background.
Allows the frontend to send tasks and retrieve status later.
"""
import logging
import pathlib
import tempfile

from celery import chain, signals
from celery.worker.consumer import Consumer
import geopandas as gpd
import pandas as pd
import xarray as xr

from eddie import geoserver
from eddie.digitaltwin import retrieve_from_instructions
from eddie.digitaltwin.utils import setup_logging
from eddie.tasks import OnFailureStateTask, app
from src.eddie_antartica.config import EnvVariable
from src.eddie_antartica.run_all import DEFAULT_MODULES_TO_PARAMETERS
from src.eddie_antartica.sea_ice.inputs import main_sea_ice_inputs
from src.eddie_antartica.sea_ice.model import serve_model, sic_gnn_model, sic_to_nc
from src.eddie_antartica.sea_ice.model.sic_data_from_nc import point_series
from src.eddie_antartica.sea_ice.sea_ice_forecast_layer import layer_name

setup_logging()
log = logging.getLogger(__name__)


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
        base_data_parameters = DEFAULT_MODULES_TO_PARAMETERS[retrieve_from_instructions]
        sender.app.send_task("eddie.tasks.add_base_data_to_db", args=[aoi_wkt, base_data_parameters], connection=conn)


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
    serve_model.add_forecast_to_geoserver(nc_path)
    return nc_path.as_posix()


@app.task(base=OnFailureStateTask)
def refresh_sea_ice_forecast() -> None:
    """Fetch this week's inputs, then forecast from them. Beat schedules one task, so this one builds the chain."""
    chain(preprocess_sea_ice_inputs.s(), forecast_sea_ice.s()).delay()


@app.task(base=OnFailureStateTask)
def publish_sea_ice_forecast_week(week: int) -> str:
    """
    Render one week of ``FORECAST_NETCDF_LATEST`` to a GeoTIFF and publish it as that week's GeoServer layer.

    Parameters
    ----------
    week : int
        Forecast week, 1-based.

    Returns
    -------
    str
        The week's date from the forecast's ``time``, ``YYYY-MM-DD``.
    """
    forecast = EnvVariable.FORECAST_NETCDF_LATEST
    with xr.open_dataset(forecast) as dataset:
        date = pd.Timestamp(dataset["time"].values[week - 1]).strftime("%Y-%m-%d")
    # add_gtiff_to_geoserver copies the file into GeoServer's data dir, so the GeoTIFF itself is throwaway.
    with tempfile.TemporaryDirectory() as tmp_dir:
        gtiff = sic_to_nc.nc_to_gtiff(forecast, pathlib.Path(tmp_dir) / f"{layer_name(week)}.tif", week - 1)
        geoserver.add_gtiff_to_geoserver(gtiff, geoserver.Workspaces.STATIC_FILES_WORKSPACE, layer_name(week))
    return date


@app.task(base=OnFailureStateTask)
def sea_ice_forecast_point_series(longitude: float, latitude: float) -> str:
    """
    Chart ``FORECAST_NETCDF_LATEST`` at a point.

    Parameters
    ----------
    longitude : float
        Clicked longitude in degrees.
    latitude : float
        Clicked latitude in degrees.

    Returns
    -------
    str
        The two-column CSV Terria plots: time, then concentration; just the header off the grid.
    """
    return point_series(longitude, latitude, EnvVariable.FORECAST_NETCDF_LATEST).to_csv(index=False)
