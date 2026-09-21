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
Serve an ice sheet model point series out of ice_ds.nc, as the CSV TerriaJS charts.

TerriaJS charts whatever two-or-more column CSV a layer's ``getFeatureInfoUrl`` returns:
column one is the x axis, the rest are series. ``ice_ds.nc`` holds
``(model_condition: 13, time_bce: 20, y, x)``, so one click gives 20 timesteps for each
of 13 model runs -- all of them, because picking one run is a scientific choice this
code is not entitled to make silently.

The grid is projected (metres) and the file states its own CRS in ``spatial_ref``, so a
click has to be reprojected before it means anything. Getting that wrong returns a
plausible number from the wrong place rather than an error, which is what
``test_timeseries.py`` guards.
"""
import pathlib
from typing import Dict, Union

import pandas as pd
import xarray as xr
from rasterio.crs import CRS
from rasterio.warp import transform

ICE_DATASET = pathlib.Path("src/static/geo/ice_ds.nc")

#: TerriaJS asks in degrees, WGS 84.
CLICK_CRS = CRS.from_epsg(4326)

#: What ice_ds.nc holds, and what a chart of each should be called. Units live here
#: because the column headers are taken up by the model run names.
VARIABLES: Dict[str, str] = {"thk": "Ice thickness (m)", "topg": "Bed elevation (m)"}

SERIES_DIM = "time_bce"
SERIES_COLUMN = "Years BCE"


def point_series(longitude: float,
                 latitude: float,
                 variable: str,
                 source: Union[str, pathlib.Path] = ICE_DATASET) -> pd.DataFrame:
    """
    Read every model run's series for the grid cell containing a point.

    Only the one cell is read off disk, so file size costs little.

    Parameters
    ----------
    longitude : float
        Longitude of the clicked point, in degrees (EPSG:4326).
    latitude : float
        Latitude of the clicked point, in degrees (EPSG:4326).
    variable : str
        Which of ``VARIABLES`` to sample.
    source : Union[str, pathlib.Path]
        Path to the NetCDF file. Overridden in tests.

    Returns
    -------
    pandas.DataFrame
        Indexed by ``time_bce``, one column per model run. Empty if the point falls
        outside the grid.

    Raises
    ------
    OSError
        If the file is missing or unreadable.
    KeyError
        If the file does not hold that variable, or states no CRS.
    """
    with xr.open_dataset(source, decode_coords="all") as dataset:
        data = dataset[variable]
        grid_crs = CRS.from_user_input(dataset[data.encoding["grid_mapping"]].attrs["crs_wkt"])
        eastings, northings = transform(CLICK_CRS, grid_crs, [longitude], [latitude])
        # Half a cell, so a click lands in the cell it is inside and a click off the
        # grid raises rather than snapping to the nearest edge.
        tolerance = max(abs(float(dataset[axis].diff(axis).max())) for axis in ("x", "y")) / 2
        try:
            cell = data.sel(x=eastings[0], y=northings[0], method="nearest", tolerance=tolerance)
        except KeyError:
            return pd.DataFrame(index=pd.Index([], name=SERIES_COLUMN))
        frame = cell.transpose(SERIES_DIM, ...).to_pandas()

    frame.columns = [_format_model_condition(column) for column in frame.columns]

    frame.index.name = SERIES_COLUMN
    return frame


def _format_model_condition(condition: object) -> str:
    """Create a compact chart label from a NetCDF model-condition name."""
    return (
        str(condition)
        .removeprefix("ism_")
        .replace("_", " ")
        .replace("hotf", "HF")
        .replace("mv", "MV")
        .replace("fr", "FR")
    )
