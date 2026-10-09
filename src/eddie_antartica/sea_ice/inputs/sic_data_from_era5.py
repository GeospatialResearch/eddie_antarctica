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
Fetch hourly ERA5 (ERA5T) from the Copernicus CDS and reduce it to daily fields on the model's 1-degree grid.

Ported from the sea ice model's ``dataprocessor`` (``prep_utils`` + notebook 1). ``cdsapi``
reads its credentials from ``CDSAPI_URL`` / ``CDSAPI_KEY`` (``api_keys.env``) or ``~/.cdsapirc``.
"""
import calendar
import datetime
import logging
from pathlib import Path
from typing import Iterator, List, Sequence, Tuple
import zipfile

import cdsapi
import numpy as np
import xarray as xr

from src.eddie_antartica.sea_ice.model.sic_to_nc import MODEL_LAT, MODEL_LON

log = logging.getLogger(__name__)

CDS_DATASET = "reanalysis-era5-single-levels"
# ponytail: area inferred (dataprocessor config.py not shared); confirm. [North, West, South, East].
CDS_AREA = [-40, -180, -90, 180]
CDS_GRID = [0.25, 0.25]
#: CDS short name -> the long name the model's variables use.
ERA5_CDS_RENAME = {
    "u10": "10m_u_component_of_wind",
    "v10": "10m_v_component_of_wind",
    "t2m": "2m_temperature",
    "msl": "mean_sea_level_pressure",
    "tp": "total_precipitation",
    "sst": "sea_surface_temperature",
    "lsm": "land_sea_mask",
}
ERA5_VARS = list(ERA5_CDS_RENAME.values())
#: Accumulated fields: summed over the day. Everything else is a daily mean.
ERA5_SUM_VARS = ["total_precipitation"]
#: 0.25-degree cells per 1-degree cell along each axis.
COARSEN_FACTOR = 4


def _months_between(start: datetime.date, end: datetime.date) -> Iterator[Tuple[int, int]]:
    """
    Yield each ``(year, month)`` from ``start``'s month to ``end``'s, inclusive.

    Parameters
    ----------
    start : datetime.date
        First day.
    end : datetime.date
        Last day.

    Yields
    ------
    Tuple[int, int]
        Year and month.
    """
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def download_era5(start: datetime.date, end: datetime.date, out_dir: Path) -> List[Path]:
    """
    Download hourly ERA5 for ``[start, end]``, one CDS request per calendar month.

    Unlike the notebook, an existing month file is never reused: last week's file for this
    month holds only the days available then.

    Parameters
    ----------
    start : datetime.date
        First day, inclusive.
    end : datetime.date
        Last day, inclusive.
    out_dir : pathlib.Path
        Where to write them. Created if missing.

    Returns
    -------
    List[pathlib.Path]
        One ``era5_YYYYMM.nc`` per month. The new CDS delivers each as a ZIP despite the name.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    paths = []
    for year, month in _months_between(start, end):
        days = [d for d in range(1, calendar.monthrange(year, month)[1] + 1)
                if start <= datetime.date(year, month, d) <= end]
        target = out_dir / f"era5_{year}{month:02d}.nc"
        log.info("Requesting ERA5 %d-%02d days %d..%d", year, month, days[0], days[-1])
        client.retrieve(CDS_DATASET, {
            "product_type": "reanalysis",
            "variable": ERA5_VARS,
            "year": str(year), "month": f"{month:02d}",
            "day": [f"{d:02d}" for d in days],
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": CDS_AREA,
            "grid": CDS_GRID,
            "format": "netcdf",
        }, str(target))
        paths.append(target)
    return paths


def _inner_files(files: Sequence[Path]) -> List[Path]:
    """
    Extract CDS ZIPs (instant + accumulated NetCDFs) beside themselves; plain NetCDFs pass through.

    Parameters
    ----------
    files : Sequence[pathlib.Path]
        Downloaded files.

    Returns
    -------
    List[pathlib.Path]
        The NetCDFs to open.
    """
    out = []
    for path in sorted(files):
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                archive.extractall(path.parent / path.stem)
            out += sorted((path.parent / path.stem).glob("*.nc"))
        else:
            out.append(path)
    return out


def load_era5_raw(path: Path) -> xr.Dataset:
    """
    Open one inner CDS NetCDF with the project's names: ``time``/``lat``/``lon`` and long variable names.

    Latitude ascending, longitude 0..360. Opened lazily.

    Parameters
    ----------
    path : pathlib.Path
        An instant or accumulated NetCDF from a CDS download.

    Returns
    -------
    xarray.Dataset
        The standardised dataset.
    """
    ds = xr.open_dataset(path)
    ds = ds.rename({k: v for k, v in {"latitude": "lat", "longitude": "lon", "valid_time": "time"}.items()
                    if k in ds.variables})
    ds = ds[[v for v in ERA5_CDS_RENAME if v in ds.data_vars]].rename(
        {k: v for k, v in ERA5_CDS_RENAME.items() if k in ds.data_vars})
    ds = ds.sortby("lat")
    if float(ds["lon"].min()) < 0:
        # -180..180 inclusive puts two columns on 0 after wrapping; keep one.
        ds = ds.assign_coords(lon=np.mod(ds["lon"], 360)).drop_duplicates("lon").sortby("lon")
    return ds


def era5_to_1deg(ds: xr.Dataset) -> xr.Dataset:
    """
    Reduce hourly 0.25-degree ERA5 to daily fields on the model's 1-degree grid.

    Accumulated fields (``ERA5_SUM_VARS``) are summed over the UTC day, the rest meaned, matching
    the daily-mean training data. Then 4 x 4 block means, labelled on the model grid.

    Parameters
    ----------
    ds : xarray.Dataset
        Hourly fields from ``load_era5_raw``.

    Returns
    -------
    xarray.Dataset
        Daily fields on ``(time, lat, lon)``, times at midnight.
    """
    ds = ds.sel(lat=slice(-90, -40.25))
    sum_vars = [v for v in ERA5_SUM_VARS if v in ds.data_vars]
    mean_vars = [v for v in ds.data_vars if v not in sum_vars]
    parts = []
    if mean_vars:
        parts.append(ds[mean_vars].resample(time="1D").mean())
    if sum_vars:
        parts.append(ds[sum_vars].resample(time="1D").sum())
    ds = xr.merge(parts).coarsen(lat=COARSEN_FACTOR, lon=COARSEN_FACTOR, boundary="trim").mean()
    ds = ds.isel(lat=slice(0, MODEL_LAT.size), lon=slice(0, MODEL_LON.size))
    return ds.assign_coords(lat=MODEL_LAT, lon=MODEL_LON, time=ds["time"].dt.floor("1D"))


def build_era5_series(files: Sequence[Path]) -> xr.Dataset:
    """
    Turn CDS downloads into one daily dataset on the model grid.

    Each inner file and variable is reduced on its own, so only one variable-month of hourly
    0.25-degree data (~1 GB) is in memory at a time.

    Parameters
    ----------
    files : Sequence[pathlib.Path]
        Downloaded ``era5_YYYYMM.nc`` files.

    Returns
    -------
    xarray.Dataset
        Daily ``ERA5_VARS`` on ``(time, lat, lon)``.
    """
    daily = []
    for path in _inner_files(files):
        with load_era5_raw(path) as ds:
            daily += [era5_to_1deg(ds[[name]]).load() for name in ds.data_vars]
    return xr.combine_by_coords(daily)


def daily_era5(start: datetime.date, end: datetime.date, raw_dir: Path) -> xr.Dataset:
    """
    Download and reduce ERA5 for ``[start, end]``.

    Parameters
    ----------
    start : datetime.date
        First day, inclusive.
    end : datetime.date
        Last day, inclusive.
    raw_dir : pathlib.Path
        Scratch directory for the raw files.

    Returns
    -------
    xarray.Dataset
        Daily ``ERA5_VARS`` on the model grid.
    """
    return build_era5_series(download_era5(start, end, raw_dir / "era5"))
