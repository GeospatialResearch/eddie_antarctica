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
Sample a single grid cell out of an xarray-openable dataset.
This could be used for Zarr sources later.
"""
import pathlib
from typing import Optional, Union

import xarray as xr
from rasterio.crs import CRS
from rasterio.warp import transform

CLICK_CRS = CRS.from_epsg(4326)


def sample_cell(source: Union[str, pathlib.Path],  # pylint: disable=too-many-arguments
                variable: str,
                longitude: float,
                latitude: float,
                x_dim: str = "x",
                y_dim: str = "y") -> Optional[xr.DataArray]:
    """
    Read the grid cell containing a point, across whatever other dimensions it has.

    Only the one cell is read off disk, so file size costs little. The CRS is read from
    the variable's ``grid_mapping``, never assumed -- indexing the wrong cell returns a
    plausible number instead of an error.

    Parameters
    ----------
    source : Union[str, pathlib.Path]
        Path to the dataset, opened with ``xarray.open_dataset``.
    variable : str
        Name of the data variable to sample.
    longitude : float
        Longitude of the point in degrees (EPSG:4326).
    latitude : float
        Latitude of the point in degrees (EPSG:4326).
    x_dim : str
        Name of the grid's easting/longitude dimension.
    y_dim : str
        Name of the grid's northing/latitude dimension.

    Returns
    -------
    Optional[xarray.DataArray]
        The cell, with every other dimension intact and already loaded into memory.
        ``None`` if the point falls outside the grid.

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
        easting, northing = eastings[0], northings[0]
        if grid_crs.is_geographic:
            west = float(dataset[x_dim].min())
            easting = west + (easting - west) % 360
        tolerance = max(abs(float(dataset[dim].diff(dim).max())) for dim in (x_dim, y_dim)) / 2
        try:
            return data.sel({x_dim: easting, y_dim: northing}, method="nearest", tolerance=tolerance).load()
        except KeyError:
            return None
