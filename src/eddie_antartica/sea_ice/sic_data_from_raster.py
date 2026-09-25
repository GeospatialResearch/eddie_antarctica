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
Read sea ice concentration forecast time series out of a multi-band GeoTIFF.

The forecast raster is produced offline: one band per forecast step, north-up on a
1-degree EPSG:4326 grid, each band tagged with the ISO-8601 timestamp it represents.
This module samples a single point across every band so the backend can serve the
result as the CSV that TerriaJS charts when a user clicks the layer.
"""
import os
from typing import List, Union

import numpy as np
import pandas as pd
import rasterio as rio

TIME_COLUMN = "Time (UTC)"
VALUE_COLUMN = "Sea ice concentration (fraction)"

TIME_TAG = "TIME"


def _band_timestamps(raster: rio.DatasetReader) -> List[str]:
    """
    Read the timestamp each band represents.

    Prefers the band's TIME tag and falls back to its description, so a raster written
    by an older export that only set descriptions still charts correctly.

    Parameters
    ----------
    raster : rasterio.DatasetReader
        An open raster dataset.

    Returns
    -------
    List[str]
        One timestamp per band, in band order. An empty string marks a band that
        carries neither a TIME tag nor a description.
    """
    timestamps = []
    for band in range(1, raster.count + 1):
        tag = raster.tags(band).get(TIME_TAG)
        timestamps.append(tag or raster.descriptions[band - 1] or "")
    return timestamps


def _empty_series() -> pd.DataFrame:
    """
    Build the zero-row frame returned for points outside the raster.

    Returns
    -------
    pandas.DataFrame
        A frame with the expected columns and no rows.
    """
    return pd.DataFrame({TIME_COLUMN: pd.Series(dtype="object"),
                         VALUE_COLUMN: pd.Series(dtype="float32")})


def sic_forecast_series(longitude: float,
                        latitude: float,
                        raster_path: Union[str, os.PathLike]) -> pd.DataFrame:
    """
    Extract the forecast time series for the raster cell containing a point.

    Parameters
    ----------
    longitude : float
        Longitude of the point in degrees, in either the -180..180 or 0..360 convention.
    latitude : float
        Latitude of the point in degrees (EPSG:4326).
    raster_path : Union[str, os.PathLike]
        Path to the multi-band forecast GeoTIFF. The caller owns its location: the raster
        holds unpublished data and is not committed to this repository.

    Returns
    -------
    pandas.DataFrame
        Columns ``Time (UTC)`` and ``Sea ice concentration (fraction)``, one row per
        band. Zero rows if the point falls outside the raster extent.

    Raises
    ------
    rasterio.errors.RasterioIOError
        If the raster cannot be opened.
    """
    with rio.open(raster_path) as raster:
        bounds = raster.bounds
        longitude = bounds.left + (longitude - bounds.left) % 360
        if not (bounds.left <= longitude <= bounds.right and bounds.bottom <= latitude <= bounds.top):
            return _empty_series()

        values = next(raster.sample([(longitude, latitude)])).astype("float32")
        timestamps = _band_timestamps(raster)
        nodata = raster.nodata

    if nodata is not None and not np.isnan(nodata):
        values = np.where(values == nodata, np.nan, values)

    return pd.DataFrame({TIME_COLUMN: timestamps, VALUE_COLUMN: values})
