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
Convert the NSIDC-0780 sea ice region mask, once, into the land fraction the smoothed sea ice layers are cut with.

NSIDC-0780 sits on a polar grid. The smoothed layers are drawn on a ``sic_to_nc.DISPLAY_RESOLUTION`` lat/lon grid
over the model's rows, so the mask's nearest cell is looked up once at every pixel centre of that grid and stored
there. The weekly run then reads it with no reprojection. Points outside the mask's grid are sea.

Run once, after downloading the file::

    python -m src.eddie_antartica.sea_ice.inputs.land_mask_from_nsidc <NSIDC-0780 .nc> <SIC_LAND_MASK_FILE>
"""
import logging
from pathlib import Path
import sys

import numpy as np
from pyproj import Transformer
import rioxarray  # noqa: F401  # pylint: disable=unused-import  # registers the .rio accessor
import xarray as xr

from src.eddie_antartica.sea_ice.model import sic_to_nc

log = logging.getLogger(__name__)

#: The Southern Hemisphere surface classes of an NSIDC-0780 file.
MASK_VARIABLE = "sea_ice_region_NASA_surface_mask"

#: Classes that are not sea. NSIDC Special Report 25 counts ice sheets and ice shelves as land.
NOT_SEA = ("land", "fresh_free_water", "ice_on_land", "floating_ice_shelf", "ocean_disconnected")


def main(nsidc_path: Path, out_path: Path) -> Path:
    """
    Write ``land_sea_mask(lat, lon)``, 1 on land and 0 on sea, on the smoothed layers' grid.

    Parameters
    ----------
    nsidc_path : Path
        An NSIDC-0780 ``NSIDC-0780_SeaIceRegions_<grid>-S<resolution>km_v1.0.nc``.
    out_path : Path
        Where to write the mask: ``SIC_LAND_MASK_FILE``.

    Returns
    -------
    Path
        The written mask.

    Raises
    ------
    ValueError
        If the file states no CRS, or names no class this module counts as not sea.
    """
    with xr.open_dataset(nsidc_path, decode_coords="all") as dataset:
        regions = dataset[MASK_VARIABLE].load()
    if regions.rio.crs is None:
        raise ValueError(f"{nsidc_path} states no CRS for {MASK_VARIABLE}")
    classes = dict(zip(str(regions.attrs["flag_meanings"]).split(), np.atleast_1d(regions.attrs["flag_values"])))
    missing = [name for name in NOT_SEA if name not in classes]
    if missing:
        raise ValueError(f"{nsidc_path} {MASK_VARIABLE} has no {', '.join(missing)} class")
    log.info("Not sea: %s. Sea: %s.", ", ".join(NOT_SEA), ", ".join(name for name in classes if name not in NOT_SEA))
    land = regions.isin([classes[name] for name in NOT_SEA])

    step = float(sic_to_nc.MODEL_LAT[1] - sic_to_nc.MODEL_LAT[0])
    lat, lon = sic_to_nc.display_grid(sic_to_nc.MODEL_LAT.max() + step / 2, sic_to_nc.MODEL_LAT.min() - step / 2)
    x, y = Transformer.from_crs("EPSG:4326", regions.rio.crs.to_wkt(), always_xy=True).transform(
        *np.meshgrid(lon, np.maximum(lat, -90)))
    x_cells, y_cells = regions[regions.rio.x_dim], regions[regions.rio.y_dim]
    half_x, half_y = abs(float(x_cells[1] - x_cells[0])) / 2, abs(float(y_cells[1] - y_cells[0])) / 2
    inside = (abs(x - float(x_cells.mean())) <= abs(float(x_cells[-1] - x_cells[0])) / 2 + half_x) & (
        abs(y - float(y_cells.mean())) <= abs(float(y_cells[-1] - y_cells[0])) / 2 + half_y)
    nearest = land.sel({regions.rio.x_dim: xr.DataArray(x, dims=("lat", "lon")),
                        regions.rio.y_dim: xr.DataArray(y, dims=("lat", "lon"))}, method="nearest")
    fraction = xr.DataArray((inside & nearest.values).astype("uint8"), dims=("lat", "lon"),
                            coords={"lat": lat, "lon": lon}, name="land_sea_mask",
                            attrs={"long_name": "Land fraction", "units": "1", "source": nsidc_path.name})
    return sic_to_nc.to_cf_netcdf(fraction, out_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(main(Path(sys.argv[1]), Path(sys.argv[2])))
