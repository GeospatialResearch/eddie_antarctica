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
Serve a sea ice concentration forecast point series out of the NetCDF written for issue #35.

The sibling ``sic_data_from_raster`` reads the same forecast out of the multi-band GeoTIFF
that GeoServer publishes. Both exist on purpose: ``serve_static_files`` in ``lib/eddie``
matches ``.tif`` and skips ``.nc``, so the WMS layer cannot move, while the NetCDF is the
model's own output rather than a raster export of it.

Both return the same two columns, so whichever a catalog entry points at, TerriaJS charts
an identical CSV. That is what makes the two routes comparable rather than merely similar.

The CRS is read from the file's ``grid_mapping``, never assumed -- indexing the wrong cell
returns a plausible number instead of an error. In practice ``sic_forecast_to_nc`` always
writes EPSG:4326, so the transform below is an identity; it is there so a regridded file
does not silently sample the wrong place.
"""
import pathlib
from typing import Union

import pandas as pd
from rasterio.crs import CRS
from rasterio.warp import transform
import xarray as xr

from src.eddie_antartica.sea_ice.sic_data_from_raster import TIME_COLUMN, VALUE_COLUMN, _empty_series

#: TerriaJS asks in degrees, WGS 84.
CLICK_CRS = CRS.from_epsg(4326)
VARIABLE = "sic"
#: Matches the GeoTIFF's per-band TIME tags, so the two routes' CSVs agree byte for byte.
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def point_series(longitude: float,
                 latitude: float,
                 source: Union[str, pathlib.Path]) -> pd.DataFrame:
    """
    Extract the forecast time series for the grid cell containing a point.

    Only the one cell is read off disk, so file size costs little.

    Parameters
    ----------
    longitude : float
        Longitude of the clicked point in degrees, in either the -180..180 or 0..360
        convention.
    latitude : float
        Latitude of the clicked point in degrees (EPSG:4326).
    source : Union[str, pathlib.Path]
        Path to the forecast NetCDF. The caller owns its location: the forecast holds
        unpublished data and is not committed to this repository.

    Returns
    -------
    pandas.DataFrame
        Columns ``Time (UTC)`` and ``Sea ice concentration (fraction)``, one row per
        forecast step. Zero rows if the point falls outside the grid.

    Raises
    ------
    OSError
        If the file is missing or unreadable.
    KeyError
        If the file does not hold the forecast variable, or states no CRS.
    """
    with xr.open_dataset(source, decode_coords="all") as dataset:
        data = dataset[VARIABLE]
        grid_crs = CRS.from_user_input(dataset[data.encoding["grid_mapping"]].attrs["crs_wkt"])
        eastings, northings = transform(CLICK_CRS, grid_crs, [longitude], [latitude])
        # Wrap into whichever convention the file uses, so a 0..360 click lands on a
        # -180..180 grid and vice versa.
        west = float(dataset["lon"].min())
        easting = west + (eastings[0] - west) % 360
        # Half a cell, so a click lands in the cell it is inside and a click off the grid
        # raises rather than snapping to the nearest edge.
        tolerance = max(abs(float(dataset[axis].diff(axis).max())) for axis in ("lat", "lon")) / 2
        try:
            cell = data.sel(lon=easting, lat=northings[0], method="nearest", tolerance=tolerance)
        except KeyError:
            return _empty_series()
        timestamps = pd.DatetimeIndex(cell["time"].values).strftime(TIME_FORMAT)
        values = cell.values.astype("float32")

    return pd.DataFrame({TIME_COLUMN: timestamps, VALUE_COLUMN: values})
