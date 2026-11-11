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
Write the sea ice forecast, and the data it is run on, as CF NetCDF on one EPSG:4326 grid.

Uses ``rio.set_spatial_dims`` + ``rio.write_crs`` + ``to_netcdf``, and a GeoTIFF derived from the
written NetCDF with ``rio.to_raster``, so the map and the chart read one grid.

``to_cf_netcdf`` is the contract for every gridded sea ice file: the forecast written here and
the preprocessed NSIDC/ERA5 inputs alike. ``rioxarray`` comes in with ``geocube``.
"""
import pathlib
from typing import Union

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401  # pylint: disable=unused-import  # registers the .rio accessor
import xarray as xr

from src.eddie_antartica.sea_ice.model.sic_data_from_nc import VARIABLE

#: Values above this are NSIDC land/coast/pole-hole flags (251-254), not concentrations.
FLAG_THRESHOLD = 1.0

LAND_FRACTION_THRESHOLD = 0.5

DISPLAY_RESOLUTION = 0.05

#: The model forecasts weekly, continuing on from its last input week.
FORECAST_STEP = pd.Timedelta(weeks=1)

#: The model's 50 x 360 1-degree grid in its native order: latitude ascending, longitude 0..359.
#: Each label is the south-west corner of the 4 x 4 block of 0.25-degree cells averaged into it,
#: as the training data was built (``sic_data_from_nsidc.regrid_to_1deg``, ``sic_data_from_era5.era5_to_1deg``).
MODEL_LAT = np.arange(-90, -40, dtype="float64")
MODEL_LON = np.arange(0, 360, dtype="float64")


def to_cf_netcdf(data: Union[xr.DataArray, xr.Dataset], path: pathlib.Path) -> pathlib.Path:
    """
    Write gridded data as CF-1.8 NetCDF on the shared EPSG:4326 grid.

    Longitude is wrapped to -180..179 and sorted ascending, latitude sorted north first.
    Sorting is by coordinate label, so the data moves with its coordinates whichever
    convention it arrives in.

    Parameters
    ----------
    data : Union[xarray.DataArray, xarray.Dataset]
        Data with ``lat`` and ``lon`` coordinates in degrees (cell centres), longitude in
        either the 0..359 or -180..179 convention.
    path : pathlib.Path
        Where to write the file. Its directory is created if missing.

    Returns
    -------
    pathlib.Path
        The written file.
    """
    data = data.assign_coords(lon=((data.lon + 180) % 360) - 180)
    data = data.sortby("lon").sortby("lat", ascending=False)
    data = (data.rio.set_spatial_dims(x_dim="lon", y_dim="lat")
                .rio.write_crs("EPSG:4326")
                .rio.write_coordinate_system())
    if isinstance(data, xr.DataArray):
        data = data.to_dataset()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Readers pick the newest forecast by name, so write beside it and rename into place once complete.
    # "_temp" breaks the dated-name glob.
    temp_file = path.with_name(f"{path.stem}_temp{path.suffix}")
    data.assign_attrs(Conventions="CF-1.8").to_netcdf(temp_file, engine="netcdf4")
    temp_file.replace(path)
    return path


def forecast_to_nc(forecast: np.ndarray, inputs: xr.Dataset, out_dir: pathlib.Path) -> pathlib.Path:
    """
    Write the model's forecast as ``sic(time, lat, lon)``, dated from the data it was run on.

    Parameters
    ----------
    forecast : numpy.ndarray
        The model output, shape ``(node, week)``: one row per grid cell, latitude-major in
        the order of ``inputs.lat`` and ``inputs.lon``.
    inputs : xarray.Dataset
        The dataset the model was run on, as it was fed to the model. Its ``lat``/``lon``
        order defines the node order, and its last ``time`` is the week the forecast
        follows on from.
    out_dir : pathlib.Path
        Directory to write into.

    Returns
    -------
    pathlib.Path
        ``out_dir / "sic_forecast_<weeks>w_<YYYY-MM-DD of week 1>.nc"``.

    Raises
    ------
    ValueError
        If the forecast has a different number of nodes from the input grid.
    """
    n_weeks = forecast.shape[1]
    times = pd.date_range(pd.Timestamp(inputs.time.values[-1]) + FORECAST_STEP, periods=n_weeks, freq=FORECAST_STEP)
    sic = xr.DataArray(
        forecast.T.reshape(n_weeks, inputs.lat.size, inputs.lon.size).astype("float32"),
        dims=("time", "lat", "lon"),
        coords={"time": times, "lat": inputs.lat.values, "lon": inputs.lon.values},
        name=VARIABLE,
        attrs={"long_name": "Sea ice concentration", "standard_name": "sea_ice_area_fraction", "units": "1"},
    )
    sic = sic.where(sic <= FLAG_THRESHOLD)
    return to_cf_netcdf(sic, out_dir / f"sic_forecast_{n_weeks}w_{times[0]:%Y-%m-%d}.nc")


def nc_to_gtiff(nc_path: pathlib.Path, gtiff_path: pathlib.Path, week: int = -1) -> pathlib.Path:
    """
    Write one week of the forecast as the single-band GeoTIFF GeoServer publishes.

    Parameters
    ----------
    nc_path : pathlib.Path
        A forecast ``sic(time, lat, lon)`` in EPSG:4326, such as ``forecast_to_nc`` writes. Its longitudes
        must span the globe, in either the 0..359 or -180..179 convention, and either latitude order.
    gtiff_path : pathlib.Path
        Where to write the GeoTIFF. Its stem becomes the GeoServer layer name when it is
        published from ``src/static/geo``.
    week : int
        Index into ``time`` of the week to write; the last by default.

    Returns
    -------
    pathlib.Path
        The written GeoTIFF.
    """
    with xr.open_dataset(nc_path, decode_coords="all") as dataset:
        sic = dataset[VARIABLE].isel(time=week)
        # Normalise to -180..180, north up, whatever order the file is in, so GeoServer gets a standard grid.
        sic = sic.assign_coords(lon=((sic.lon + 180) % 360) - 180).sortby("lon").sortby("lat", ascending=False)
        # Copy the edge columns across the 180 line (last one to the far west, first one to the far east),
        # so the smoothing has a neighbour on both sides and draws no line at 180.
        west, east = sic.isel(lon=0), sic.isel(lon=-1)
        sic = xr.concat([east.assign_coords(lon=float(east.lon) - 360), sic,
                         west.assign_coords(lon=float(west.lon) + 360)], dim="lon")
        sic.rio.set_spatial_dims(x_dim="lon", y_dim="lat").rio.write_crs("EPSG:4326").rio.to_raster(
            gtiff_path, compress="LZW")
    return gtiff_path


def _resample(grid: xr.DataArray, lon: np.ndarray, lat: np.ndarray, method: str) -> np.ndarray:
    """
    Interpolate a global ``(lat, lon)`` grid of cell centres onto other cell centres, continuous across 180 degrees.

    Parameters
    ----------
    grid : xarray.DataArray
        Values on a regular global grid, longitude in either the 0..359 or -180..179 convention, either latitude order.
    lon : numpy.ndarray
        Longitudes to interpolate at, within -180..180.
    lat : numpy.ndarray
        Latitudes to interpolate at.
    method : str
        ``xarray`` interpolation: ``"nearest"`` or ``"linear"``.

    Returns
    -------
    numpy.ndarray
        Shape ``(lat, lon)``. The outermost rows are repeated across their outer half cell; beyond that is NaN.
    """
    grid = grid.assign_coords(lon=((grid.lon + 180) % 360) - 180).sortby("lon").sortby("lat").transpose("lat", "lon")
    west, east = grid.isel(lon=0), grid.isel(lon=-1)
    grid = xr.concat([east.assign_coords(lon=float(east.lon) - 360), grid,
                      west.assign_coords(lon=float(west.lon) + 360)], dim="lon")
    south, north = float(grid.lat[0]), float(grid.lat[-1])
    half = float(grid.lat.diff("lat").max()) / 2
    values = grid.interp(lon=lon, lat=np.clip(lat, south, north), method=method).values
    return np.where(((lat >= south - half) & (lat <= north + half))[:, None], values, np.nan)


def display_gtiff(nc_path: pathlib.Path, gtiff_path: pathlib.Path, week: int, land_sea_mask_path: pathlib.Path,
                  smooth: bool) -> pathlib.Path:
    """
    Write one week of the forecast as a ``DISPLAY_RESOLUTION`` GeoTIFF with the land cut out along the coast.

    Parameters
    ----------
    nc_path : pathlib.Path
        A forecast ``sic(time, lat, lon)`` in EPSG:4326, as ``nc_to_gtiff`` takes it.
    gtiff_path : pathlib.Path
        Where to write the GeoTIFF.
    week : int
        Index into ``time`` of the week to write.
    land_sea_mask_path : pathlib.Path
        A ``land_sea_mask(lat, lon)`` land fraction from 0 to 1, with or without a leading ``time``, on a regular
        global grid of any resolution. Latitudes it does not cover are sea.
    smooth : bool
        Blend between the centres of the model's sea cells, instead of giving each pixel its model cell's value.
        Either way a model cell that is land itself draws nothing.

    Returns
    -------
    pathlib.Path
        The written GeoTIFF: -180..180 by the outer edges of the model's rows, NaN where the land fraction
        interpolated onto the pixel is ``LAND_FRACTION_THRESHOLD`` or more.
    """
    with xr.open_dataset(nc_path) as dataset:
        sic = dataset[VARIABLE].isel(time=week).load()
    with xr.open_dataset(land_sea_mask_path) as dataset:
        fraction = dataset["land_sea_mask"]
        fraction = (fraction.isel(time=0) if "time" in fraction.dims else fraction).load()
    sic = sic.assign_coords(lon=((sic.lon + 180) % 360) - 180).sortby("lon").sortby("lat", ascending=False)
    half = float(abs(sic.lat.diff("lat")).max()) / 2
    north, south = float(sic.lat[0]) + half, float(sic.lat[-1]) - half
    lat = north - (np.arange(round((north - south) / DISPLAY_RESOLUTION)) + 0.5) * DISPLAY_RESOLUTION
    lon = -180 + (np.arange(round(360 / DISPLAY_RESOLUTION)) + 0.5) * DISPLAY_RESOLUTION
    land_cells = _resample(fraction, sic.lon.values, sic.lat.values, "linear") >= LAND_FRACTION_THRESHOLD
    sea = sic.notnull() & ~land_cells
    if smooth:
        weight = _resample(sea.astype("float64"), lon, lat, "linear")
        with np.errstate(invalid="ignore", divide="ignore"):
            values = np.where(weight > 0, _resample(sic.where(sea, 0), lon, lat, "linear") / weight, np.nan)
    else:
        values = _resample(sic.where(sea), lon, lat, "nearest")
    values[_resample(fraction, lon, lat, "linear") >= LAND_FRACTION_THRESHOLD] = np.nan
    display = xr.DataArray(values.astype("float32"), dims=("lat", "lon"), coords={"lat": lat, "lon": lon})
    (display.rio.set_spatial_dims(x_dim="lon", y_dim="lat").rio.write_crs("EPSG:4326").rio.write_nodata(np.nan)
            .rio.to_raster(gtiff_path, compress="LZW"))
    return gtiff_path
