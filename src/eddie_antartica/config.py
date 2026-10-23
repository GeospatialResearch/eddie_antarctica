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

"""Collection of utils that are used for system and environment configuration."""

import pathlib

from eddie.config import EnvVariable as EnvVarBase


class EnvVariable(EnvVarBase):  # pylint: disable=too-few-public-methods
    """Encapsulates all environment variable fetching, ensuring proper defaults and types."""

    DATA_DIR = pathlib.Path(EnvVarBase._get_env_variable("DATA_DIR"))

    # The forecast raster holds unpublished data, so it lives in DATA_DIR rather than the repo.
    FORECAST_RASTER = pathlib.Path(EnvVarBase._get_env_variable("FORECAST_RASTER"))
    FORECAST_NETCDF = pathlib.Path(EnvVarBase._get_env_variable("FORECAST_NETCDF"))
    FORECAST_NETCDF_LATEST = pathlib.Path(EnvVarBase._get_env_variable("FORECAST_NETCDF_LATEST"))
    ICE_DATASET = pathlib.Path(EnvVarBase._get_env_variable("ICE_DATASET"))

    # Terrain tileset built offline by ctb-tile; served by the /terrain routes in app.py.
    TERRAIN_DIR = pathlib.Path(EnvVarBase._get_env_variable("TERRAIN_DATA_DIR"))

    # Weekly sea ice forecasts, sic_forecast_<weeks>w_<YYYY-MM-DD of week 1>.nc, plus the stable
    # sic_forecast_8w.tif GeoServer copies, written by the Celery task forecast_sea_ice. The chart
    # reads the newest .nc. Own env var, like FORECAST_RASTER_FILE.
    FORECAST_NETCDF_DIR = pathlib.Path(EnvVarBase._get_env_variable("FORECAST_NETCDF_DIR"))

    # Weekly sea ice model inputs, sic_inputs_<YYYY-MM-DD>.nc, written by the Celery beat task
    # preprocess_sea_ice_inputs (inputs.main_sea_ice_inputs). Own env var, like FORECAST_RASTER_FILE.
    SEA_ICE_INPUTS_DIR = pathlib.Path(EnvVarBase._get_env_variable("SEA_ICE_INPUTS_DIR"))

    # The frozen historical day-of-year SIC climatology the model was trained against, copied once from
    # the model's data/historical/sic_climatology.nc. Never recomputed from live data.
    SIC_CLIMATOLOGY = pathlib.Path(EnvVarBase._get_env_variable("SIC_CLIMATOLOGY_FILE"))

    # The sea ice model, kept out of this repo: the scientists' Code/{util,models}, checkpoint, mesh bundle and
    # train_stats.npz (model.sic_gnn_model). Own env var, like FReDT-Smart-Ideas's FLOOD_MODEL_DIR.
    SIC_MODEL_DIR = pathlib.Path(EnvVarBase._get_env_variable("SIC_MODEL_DIR"))

    # Public backend root, for links handed to Terria (getFeatureInfoUrl); the .env values terriajs/entrypoint.sh reads.
    BACKEND_HOST = EnvVarBase._get_env_variable("BACKEND_HOST", default="http://localhost")
    BACKEND_PORT = EnvVarBase._get_env_variable("BACKEND_PORT", default="5000")
