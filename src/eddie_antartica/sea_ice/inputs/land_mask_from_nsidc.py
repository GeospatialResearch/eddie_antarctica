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
Look up the NSIDC-0780 land and ice shelves at any points, which the smoothed sea ice layer and its chart cut out.

NSIDC-0780 sits on a polar grid, so each point is projected onto it and takes its nearest cell. Points off its grid
are sea.
"""
from pathlib import Path

import numpy as np
from pyproj import Transformer
import rioxarray  # noqa: F401  # pylint: disable=unused-import  # registers the .rio accessor
import xarray as xr

#: The NSIDC-0780 file, in ``SIC_MODEL_DIR`` with the model's own files.
FILE_NAME = "NSIDC-0780_SeaIceRegions_EASE2-S3.125km_v1.0.nc"

#: The Southern Hemisphere surface classes of an NSIDC-0780 file.
MASK_VARIABLE = "sea_ice_region_NASA_surface_mask"

#: Classes that are not sea. NSIDC Special Report 25 counts ice sheets and ice shelves as land.
NOT_SEA = ("land", "fresh_free_water", "ice_on_land", "floating_ice_shelf", "ocean_disconnected")


def land_at(nsidc_path: Path, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """
    Say which points are land, a lake or an ice shelf in NSIDC-0780.

    Parameters
    ----------
    nsidc_path : Path
        An NSIDC-0780 ``NSIDC-0780_SeaIceRegions_<grid>-S<resolution>km_v1.0.nc``.
    lon : numpy.ndarray
        Longitudes in degrees, either convention.
    lat : numpy.ndarray
        Latitudes in degrees, the same shape as ``lon``. Below -90 counts as the pole.

    Returns
    -------
    numpy.ndarray
        True where the point is not sea, the shape of ``lon``.

    Raises
    ------
    ValueError
        If the file states no CRS, or names no class this module counts as not sea.
    """
    with xr.open_dataset(nsidc_path, decode_coords="all") as dataset:
        regions = dataset[MASK_VARIABLE]
        if regions.rio.crs is None:
            raise ValueError(f"{nsidc_path} states no CRS for {MASK_VARIABLE}")
        classes = dict(zip(str(regions.attrs["flag_meanings"]).split(), np.atleast_1d(regions.attrs["flag_values"])))
        missing = [name for name in NOT_SEA if name not in classes]
        if missing:
            raise ValueError(f"{nsidc_path} {MASK_VARIABLE} has no {', '.join(missing)} class")
        x, y = Transformer.from_crs("EPSG:4326", regions.rio.crs.to_wkt(), always_xy=True).transform(
            lon, np.maximum(lat, -90))
        x_cells, y_cells = regions[regions.rio.x_dim], regions[regions.rio.y_dim]
        half_x, half_y = abs(float(x_cells[1] - x_cells[0])) / 2, abs(float(y_cells[1] - y_cells[0])) / 2
        inside = (abs(x - float(x_cells.mean())) <= abs(float(x_cells[-1] - x_cells[0])) / 2 + half_x) & (
            abs(y - float(y_cells.mean())) <= abs(float(y_cells[-1] - y_cells[0])) / 2 + half_y)
        dims = [f"point_{axis}" for axis in range(np.ndim(lon))]
        nearest = regions.sel({regions.rio.x_dim: xr.DataArray(x, dims=dims),
                               regions.rio.y_dim: xr.DataArray(y, dims=dims)}, method="nearest")
        return inside & nearest.isin([classes[name] for name in NOT_SEA]).values
