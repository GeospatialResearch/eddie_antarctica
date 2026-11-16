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
Read the NSIDC-0780 land and ice shelves, which the smoothed sea ice layer and its chart cut out.

NSIDC-0780 sits on a polar grid. ``not_sea`` returns it as a georeferenced grid, to be reprojected onto whichever grid
needs it with ``rio.reproject_match``.
"""
import functools
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


@functools.lru_cache(maxsize=1)
def not_sea(nsidc_path: Path) -> xr.DataArray:
    """
    Read NSIDC-0780 as a grid of what is land, a lake or an ice shelf, once per worker: the file never changes.

    Parameters
    ----------
    nsidc_path : Path
        An NSIDC-0780 ``NSIDC-0780_SeaIceRegions_<grid>-S<resolution>km_v1.0.nc``.

    Returns
    -------
    xarray.DataArray
        1 where the surface is not sea and 0 where it is, on the file's own grid and CRS. Reprojected onto a grid
        that reaches past the file's, the cells past it are filled, never 1: off the file's grid is sea.

    Raises
    ------
    KeyError
        If the file names no class this module counts as not sea.
    """
    with xr.open_dataset(nsidc_path, decode_coords="all") as dataset:
        regions = dataset[MASK_VARIABLE].load()
    classes = dict(zip(str(regions.attrs["flag_meanings"]).split(), np.atleast_1d(regions.attrs["flag_values"])))
    return regions.isin([classes[name] for name in NOT_SEA]).astype("float32").rio.write_crs(regions.rio.crs)


def is_not_sea(nsidc_path: Path, longitude: float, latitude: float) -> bool:
    """
    Say whether one point is land, a lake or an ice shelf in NSIDC-0780.

    Parameters
    ----------
    nsidc_path : Path
        An NSIDC-0780 file, as ``not_sea`` takes it.
    longitude : float
        Longitude of the point in degrees (EPSG:4326), either convention.
    latitude : float
        Latitude of the point in degrees (EPSG:4326).

    Returns
    -------
    bool
        True if the cell holding the point is not sea. A point off the file's grid is sea.
    """
    land = not_sea(nsidc_path)
    x_dim, y_dim = land.rio.x_dim, land.rio.y_dim
    x, y = Transformer.from_crs("EPSG:4326", land.rio.crs, always_xy=True).transform(longitude, latitude)
    tolerance = max(abs(float(land[dim].diff(dim).max())) for dim in (x_dim, y_dim)) / 2
    try:
        return bool(land.sel({x_dim: x, y_dim: y}, method="nearest", tolerance=tolerance))
    except KeyError:
        return False
