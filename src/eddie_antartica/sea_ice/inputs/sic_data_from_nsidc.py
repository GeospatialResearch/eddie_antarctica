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
Fetch NOAA/NSIDC NRT sea ice concentration (G10016_V4) and regrid it onto the model's 1-degree grid.

Ported from the sea ice model's ``dataprocessor`` (``prep_utils`` + notebook 2). The product is
served openly over HTTPS: no Earthdata login. It sits on the same 25 km EPSG:3412 grid as the
historical NSIDC-0051 the model was trained on, so it regrids identically.
"""
import datetime
import logging
from pathlib import Path
import re
from typing import List, Sequence, Tuple
import urllib.request

import numpy as np
import pandas as pd
import pyproj
from scipy.interpolate import griddata
import xarray as xr

from src.eddie_antartica.sea_ice.model.sic_to_nc import MODEL_LAT, MODEL_LON

log = logging.getLogger(__name__)

# ponytail: base URL inferred from the product (dataprocessor config.py not shared); confirm on first run.
#: Daily south-polar files live under ``<base><YYYY>/sic_pss25_YYYYMMDD_<platform>_icdr_v04r00.nc``.
NSIDC_CDR_BASE_URL = "https://noaadata.apps.nsidc.org/NOAA/G10016_V4/south/daily/"
NSIDC_CDR_VAR = "cdr_seaice_conc"
#: 0.25-degree cells per 1-degree cell along each axis.
COARSEN_FACTOR = 4


def _http_listing(url: str) -> List[str]:
    """
    Return the relative hrefs in an Apache autoindex page.

    Parameters
    ----------
    url : str
        The directory URL.

    Returns
    -------
    List[str]
        Sub-directory and file names linked from the page.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        html = response.read().decode("utf-8", "replace")
    return [h for h in re.findall(r'href="([^"?]+)"', html) if not h.startswith("http") and h not in ("../", "/")]


def download_nsidc_cdr(start: datetime.date, end: datetime.date, out_dir: Path) -> List[Path]:
    """
    Download the daily files dated within ``[start, end]``.

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
        The downloaded files, sorted by name (so by date).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    got = []
    for year in range(start.year, end.year + 1):
        year_url = f"{NSIDC_CDR_BASE_URL}{year}/"
        for name in _http_listing(year_url):
            match = re.search(r"_(\d{8})_", name)
            if name.endswith(".nc") and match and start <= pd.to_datetime(match.group(1), format="%Y%m%d") <= end:
                urllib.request.urlretrieve(year_url + name, out_dir / name)
                got.append(out_dir / name)
    log.info("%d NSIDC CDR file(s) for %s..%s", len(got), start.date(), end.date())
    return sorted(got)


def nsidc_file_to_points(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, pd.Timestamp]:
    """
    Read one NRT CDR file as lon/lat/SIC on its polar grid.

    Land / missing cells (NaN) are set to 0, matching the historical SIC grid, so they feed 0
    into the regrid rather than being dropped: dropping them lets the interpolation back-fill
    land with nearby ocean ice.

    Parameters
    ----------
    path : pathlib.Path
        A ``sic_pss25_*.nc`` file.

    Returns
    -------
    Tuple[numpy.ndarray, numpy.ndarray, numpy.ndarray, pandas.Timestamp]
        2D longitude (0..360), latitude and SIC on the polar grid, and the file's day.
    """
    with xr.open_dataset(path) as ds:
        sic = ds[NSIDC_CDR_VAR].isel(time=0).values.astype("float64")
        sic = np.where(np.isnan(sic), 0.0, sic)
        transformer = pyproj.Transformer.from_crs(ds["crs"].attrs.get("proj4text", "EPSG:3412"), "EPSG:4326",
                                                  always_xy=True)
        lon, lat = transformer.transform(*np.meshgrid(ds["x"].values, ds["y"].values))
        day = pd.Timestamp(ds["time"].values[0]).normalize()
    return np.mod(lon, 360.0), lat, sic, day


def regrid_to_1deg(lon: np.ndarray, lat: np.ndarray, sic: np.ndarray, method: str = "linear") -> np.ndarray:
    """
    Regrid polar-grid SIC onto the 1-degree grid the way the training SIC was built.

    Scatter-interpolate onto a 0.25-degree lat/lon grid, then block-mean 4 x 4 down to 1 degree.
    The two steps reproduce the historical SIC to ~0.004, against ~0.013 for a one-step regrid,
    mostly at the ice edge. Holes outside the source hull are filled by nearest neighbour.

    Parameters
    ----------
    lon : numpy.ndarray
        Source longitudes, 0..360.
    lat : numpy.ndarray
        Source latitudes.
    sic : numpy.ndarray
        Source concentration, 0..1.
    method : str
        ``scipy.interpolate.griddata`` method for the interior.

    Returns
    -------
    numpy.ndarray
        ``(50, 360)`` float32, clipped to 0..1.
    """
    points = np.column_stack([lon.ravel(), lat.ravel()])
    fine = np.meshgrid(np.arange(0, 360, 1.0 / COARSEN_FACTOR), np.arange(-90, -40, 1.0 / COARSEN_FACTOR))
    out = griddata(points, sic.ravel(), tuple(fine), method=method)
    if np.isnan(out).any():
        out = np.where(np.isnan(out), griddata(points, sic.ravel(), tuple(fine), method="nearest"), out)
    out = np.clip(out, 0.0, 1.0)
    out = out.reshape(MODEL_LAT.size, COARSEN_FACTOR, MODEL_LON.size, COARSEN_FACTOR).mean(axis=(1, 3))
    return out.astype("float32")


def build_sic_series(files: Sequence[Path]) -> xr.DataArray:
    """
    Regrid NRT CDR files into one daily SIC series.

    Parameters
    ----------
    files : Sequence[pathlib.Path]
        ``sic_pss25_*.nc`` files, one per day.

    Returns
    -------
    xarray.DataArray
        ``sea_ice_concentration(time, lat, lon)`` on the model grid, sorted by time.
    """
    times, grids = [], []
    for path in sorted(files):
        lon, lat, sic, day = nsidc_file_to_points(path)
        grids.append(regrid_to_1deg(lon, lat, sic))
        times.append(day)
    return xr.DataArray(np.stack(grids), dims=("time", "lat", "lon"), name="sea_ice_concentration",
                        coords={"time": times, "lat": MODEL_LAT, "lon": MODEL_LON}).sortby("time")


def daily_sic(start: datetime.date, end: datetime.date, raw_dir: Path) -> xr.DataArray:
    """
    Download and regrid the daily SIC for ``[start, end]``.

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
    xarray.DataArray
        ``sea_ice_concentration(time, lat, lon)`` on the model grid.
    """
    return build_sic_series(download_nsidc_cdr(start, end, raw_dir / "nsidc"))
