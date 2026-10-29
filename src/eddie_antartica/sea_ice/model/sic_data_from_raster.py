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
from typing import List, Optional, Union

import numpy as np
import pandas as pd
import rasterio as rio
import xarray as xr

TIME_COLUMN = "Time (UTC)"
VALUE_COLUMN = "Sea ice concentration (fraction)"
#: Below this the map's style draws nothing ("Open water" in ``sic_forecast_8w.sld``), so the chart reads 0 too.
OPEN_WATER = 0.01

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


def bilinear_series(grid: xr.DataArray, longitude: float, latitude: float) -> Optional[np.ndarray]:
    """
    Blend the four cell centres around a point, as the map's bilinear interpolation draws it.

    The catalog draws the forecast with ``"interpolations": "bilinear"``, so a near-zero cell beside an icy one
    is drawn as trace ice. Charting only the clicked cell put a 0 under that colour.

    Parameters
    ----------
    grid : xarray.DataArray
        The forecast, with ``lon`` and ``lat`` cell-centre coordinates in degrees and one leading step dimension.
    longitude : float
        Longitude of the point in degrees, in either the -180..180 or 0..360 convention.
    latitude : float
        Latitude of the point in degrees.

    Returns
    -------
    Optional[numpy.ndarray]
        One float32 value per step, or None if the point falls outside the grid.
    """
    lons, lats = grid["lon"], grid["lat"]
    half_lon = abs(float(lons.diff("lon").max())) / 2
    half_lat = abs(float(lats.diff("lat").max())) / 2
    # Wrapped from the grid's western *edge*, not the westernmost cell centre: a click in the western half of the
    # first cell is legitimately west of that centre, and wrapping about it would throw the click 360 degrees off.
    west = float(lons.min()) - half_lon
    if float(lons.max()) + half_lon - west > 360 - half_lon:
        # A global grid has no western edge. Wrap about its westernmost column instead, repeated one turn east as
        # sic_to_nc.nc_to_gtiff repeats it for the map, so a click near 180 degrees blends across it.
        west += half_lon
        if float(lons.max()) < west + 360 - half_lon:
            grid = xr.concat([grid, grid.sel(lon=west).assign_coords(lon=west + 360)], dim="lon")
            lons = grid["lon"]
    longitude = west + (longitude - west) % 360
    inside_lon = west <= longitude <= float(lons.max()) + half_lon
    inside_lat = float(lats.min()) - half_lat <= latitude <= float(lats.max()) + half_lat
    if not (inside_lon and inside_lat):
        return None
    # The map repeats the edge cell across the grid's outermost half cell, so clamp onto the outermost centres.
    point = {"lon": np.clip(longitude, float(lons.min()), float(lons.max())),
             "lat": np.clip(latitude, float(lats.min()), float(lats.max()))}
    # Land is NaN, and a plain linear interp is NaN if any neighbour is, so blend only the neighbours with data:
    # interpolate the values with NaN as 0 and a 0/1 data mask alike, then divide.
    grid = grid.sortby("lat")
    weight = grid.notnull().astype("float64").interp(point).values
    blend = grid.fillna(0).interp(point).values
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(weight > 0, blend / weight, np.nan).astype("float32")


def sic_forecast_series(longitude: float,
                        latitude: float,
                        raster_path: Union[str, os.PathLike]) -> pd.DataFrame:
    """
    Extract the forecast time series at a point, blended from the cells around it as the map draws it.

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
        transform = raster.transform
        grid = xr.DataArray(
            raster.read(masked=True).filled(np.nan).astype("float32"),
            dims=("band", "lat", "lon"),
            coords={"lon": transform.c + transform.a * (np.arange(raster.width) + 0.5),
                    "lat": transform.f + transform.e * (np.arange(raster.height) + 0.5)})
        timestamps = _band_timestamps(raster)
    values = bilinear_series(grid, longitude, latitude)
    if values is None:
        return _empty_series()
    return pd.DataFrame({TIME_COLUMN: timestamps, VALUE_COLUMN: np.where(values < OPEN_WATER, 0, values)})
