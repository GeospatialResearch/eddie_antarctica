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
Build the sea ice model's weekly inputs from live NSIDC + ERA5: one CF NetCDF via ``sic_to_nc.to_cf_netcdf``.

Ported from the sea ice model's ``dataprocessor`` notebook 3, with one change: the model only
ever sees weekly means (it ran ``coarsen(time=7)`` on the daily feed), so the weekly mean is
taken here and nothing daily is stored. **Whatever feeds the model must therefore skip its own
``coarsen(time=7)``**: coarsening weekly data again silently produces 7-week means.

A week is labelled by its **last day**, so ``sic_to_nc.forecast_to_nc`` (last input ``time`` +
7 days) labels forecast weeks by their last day too.

``to_cf_netcdf`` stores latitude north first and longitude -180..179. The model's nodes are
latitude ascending, longitude 0..359. Re-sort before reshaping to nodes, and pass that same
dataset to ``forecast_to_nc``; a wrong order mirrors the map with no error::

    model_input = inputs.assign_coords(lon=inputs.lon % 360).sortby("lon").sortby("lat")
"""
import datetime
import logging
from pathlib import Path
import tempfile
from typing import Optional

import numpy as np
import xarray as xr

from src.eddie_antartica.sea_ice.inputs import sic_data_from_era5, sic_data_from_nsidc
from src.eddie_antartica.sea_ice.model.sic_to_nc import to_cf_netcdf

log = logging.getLogger(__name__)

#: ERA5T trails real time by about five days; the NRT CDR by one to two.
ERA5_LATENCY_DAYS = 5
NSIDC_LATENCY_DAYS = 2
# ponytail: dataprocessor config.py not shared; 35 days leaves a week of slack over the 4 weeks the model needs.
LIVE_WINDOW_DAYS = 35
#: The model forecasts from the last four weeks.
MIN_WEEKS = 4
OUTPUT_VARS = ["sea_ice_concentration", *sic_data_from_era5.ERA5_VARS, "sic_climatology", "sic_anomaly"]


def add_climatology_and_anomaly(ds: xr.Dataset, climatology_file: Path) -> xr.Dataset:
    """
    Drop Feb 29 and attach the frozen day-of-year climatology and ``sic_anomaly = SIC - climatology``.

    The climatology is the historical one the model was trained against, reused verbatim and never
    recomputed from live data. Day of year is ``dt.dayofyear`` folded onto 1..365, as in training,
    so in a leap year every day after February looks up the next day's climatology.

    Parameters
    ----------
    ds : xarray.Dataset
        Daily ``sea_ice_concentration(time, lat, lon)``.
    climatology_file : pathlib.Path
        The historical ``sic_climatology.nc``: ``sic_climatology`` on ``day_of_year`` (or on a
        ``time`` axis whose first 365 steps are one year).

    Returns
    -------
    xarray.Dataset
        ``ds`` without Feb 29, plus ``sic_climatology`` and ``sic_anomaly`` (float32).
    """
    ds = ds.sel(time=~((ds["time"].dt.month == 2) & (ds["time"].dt.day == 29)))
    with xr.open_dataset(climatology_file) as clim_ds:
        clim = clim_ds["sic_climatology"]
        if "day_of_year" not in clim.coords:
            clim = clim.assign_coords(day_of_year=((clim["time"].dt.dayofyear - 1) % 365) + 1)
        clim = clim.groupby("day_of_year").first().transpose("day_of_year", "lat", "lon").load()
    clim = clim.assign_coords(lon=clim.lon % 360).sel(lat=ds.lat, lon=ds.lon)  # by coordinate, not position
    doy = ((ds["time"].dt.dayofyear - 1) % 365) + 1
    ds["sic_climatology"] = (("time", "lat", "lon"), clim.sel(day_of_year=doy).values.astype("float32"))
    ds["sic_anomaly"] = (ds["sea_ice_concentration"] - ds["sic_climatology"]).astype("float32")
    return ds


def to_weekly(ds: xr.Dataset) -> xr.Dataset:
    """
    Trim to the most recent whole weeks and take each week's mean, labelled by its last day.

    Trimming from the old end matches the model's ``coarsen(time=7)`` on the trimmed daily feed,
    whatever gaps (Feb 29, a missing NRT or ERA5 day) left the window short.

    Parameters
    ----------
    ds : xarray.Dataset
        Daily data on ``time``.

    Returns
    -------
    xarray.Dataset
        Weekly means, at least ``MIN_WEEKS`` of them.

    Raises
    ------
    ValueError
        If fewer than ``MIN_WEEKS`` whole weeks are available.
    """
    n_days = ds.sizes["time"]
    keep = n_days // 7 * 7
    if keep < MIN_WEEKS * 7:
        raise ValueError(f"Only {keep // 7} whole week(s) of overlapping NSIDC/ERA5 days; the model needs "
                         f"{MIN_WEEKS}. Widen LIVE_WINDOW_DAYS or check for gaps in the downloads.")
    ds = ds.isel(time=slice(n_days - keep, None))
    return ds.coarsen(time=7).mean().assign_coords(time=ds["time"].values[6::7])


def main(out_dir: Path, climatology_file: Path, end: Optional[datetime.date] = None) -> Path:
    """
    Fetch the live window of NSIDC + ERA5 and write the weekly model inputs.

    Raw downloads go to a temporary directory, deleted on return.

    Parameters
    ----------
    out_dir : pathlib.Path
        Where to write the inputs file.
    climatology_file : pathlib.Path
        The frozen historical ``sic_climatology.nc``.
    end : Optional[datetime.date]
        The last day to request. Defaults to today minus the ERA5 latency.

    Returns
    -------
    pathlib.Path
        ``out_dir / "sic_inputs_<YYYY-MM-DD of the last week's last day>.nc"``.
    """
    end = end or datetime.date.today() - datetime.timedelta(days=ERA5_LATENCY_DAYS)
    start = end - datetime.timedelta(days=LIVE_WINDOW_DAYS)
    nsidc_end = max(end, datetime.date.today() - datetime.timedelta(days=NSIDC_LATENCY_DAYS))
    with tempfile.TemporaryDirectory() as raw:
        sic = sic_data_from_nsidc.daily_sic(start, nsidc_end, Path(raw))
        era5 = sic_data_from_era5.daily_era5(start, end, Path(raw))
    common = np.intersect1d(sic["time"].values, era5["time"].values)
    ds = sic.sel(time=common).to_dataset(name="sea_ice_concentration")
    for name in sic_data_from_era5.ERA5_VARS:
        ds[name] = era5[name].sel(time=common)
    ds = add_climatology_and_anomaly(ds.transpose("time", "lat", "lon"), climatology_file)
    weekly = to_weekly(ds)[OUTPUT_VARS].astype("float32")
    log.info("Sea ice inputs: %d weeks ending %s", weekly.sizes["time"], str(weekly["time"].values[-1])[:10])
    return to_cf_netcdf(weekly, out_dir / f"sic_inputs_{str(weekly['time'].values[-1])[:10]}.nc")
