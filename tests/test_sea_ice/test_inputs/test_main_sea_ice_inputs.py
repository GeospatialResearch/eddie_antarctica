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
Tests for assembling the model's live inputs folder and its conformance with the forecast writer.

Both downloads are replaced with synthetic daily fields already on the 1-degree grid; the
regrids have their own tests. No network.
"""
import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.eddie_antartica.sea_ice.inputs import main_sea_ice_inputs, sic_data_from_era5, sic_data_from_nsidc
from src.eddie_antartica.sea_ice.model import sic_to_nc

LAST_DAY = datetime.date(2025, 6, 30)


def daily(name: str, days: pd.DatetimeIndex, value: float) -> xr.DataArray:
    """
    Build a daily field on the model grid whose value is ``value + day index``.

    Parameters
    ----------
    name : str
        Variable name.
    days : pandas.DatetimeIndex
        The days.
    value : float
        The first day's value.

    Returns
    -------
    xarray.DataArray
        ``(time, lat, lon)``.
    """
    field = (value + np.arange(days.size, dtype="float32"))[:, None, None]
    field = np.broadcast_to(field, (days.size, sic_to_nc.MODEL_LAT.size, sic_to_nc.MODEL_LON.size))
    return xr.DataArray(field, dims=("time", "lat", "lon"), name=name,
                        coords={"time": days, "lat": sic_to_nc.MODEL_LAT, "lon": sic_to_nc.MODEL_LON})


def climatology_file(path: Path) -> Path:
    """
    Write a frozen climatology whose value is ``day_of_year / 1000``.

    Parameters
    ----------
    path : pathlib.Path
        Where to write it.

    Returns
    -------
    pathlib.Path
        The written file.
    """
    doy = np.arange(1, 366)
    field = np.broadcast_to((doy / 1000)[:, None, None], (doy.size, sic_to_nc.MODEL_LAT.size,
                                                          sic_to_nc.MODEL_LON.size))
    xr.Dataset({"sic_climatology": (("day_of_year", "lat", "lon"), field.astype("float32"))},
               coords={"day_of_year": doy, "lat": sic_to_nc.MODEL_LAT, "lon": sic_to_nc.MODEL_LON}
               ).to_netcdf(path)
    return path


@pytest.fixture(name="inputs_dir")
def fixture_inputs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Run ``main`` on 31 days of SIC and 33 days of ERA5 that overlap on 30.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest's temporary directory.
    monkeypatch : pytest.MonkeyPatch
        Replaces the two downloads.

    Returns
    -------
    pathlib.Path
        The written inputs folder.
    """
    sic_days = pd.date_range(end=LAST_DAY, periods=31)
    era5_days = pd.date_range(end=LAST_DAY + datetime.timedelta(days=-1), periods=33)
    monkeypatch.setattr(sic_data_from_nsidc, "daily_sic",
                        lambda start, end, raw_dir: daily("sea_ice_concentration", sic_days, 0.0) / 100)
    monkeypatch.setattr(sic_data_from_era5, "daily_era5", lambda start, end, raw_dir: xr.merge(
        [daily(name, era5_days, 1.0) for name in sic_data_from_era5.ERA5_VARS]))
    return main_sea_ice_inputs.main(tmp_path / "out", climatology_file(tmp_path / "clim.nc"), LAST_DAY)


def test_one_daily_file_per_variable_on_the_model_grid(inputs_dir: Path) -> None:
    """Laid out like the scientists' final_1_degree/: <variable>.nc, latitude ascending, longitude 0..359."""
    assert sorted(path.stem for path in inputs_dir.glob("*.nc")) == sorted(main_sea_ice_inputs.OUTPUT_VARS)
    for name in main_sea_ice_inputs.OUTPUT_VARS:
        with xr.open_dataset(inputs_dir / f"{name}.nc") as inputs:
            assert list(inputs.data_vars) == [name]
            assert inputs[name].dtype == np.float32
            assert inputs[name].dims == ("time", "lat", "lon")
            np.testing.assert_array_equal(inputs.lat, sic_to_nc.MODEL_LAT)
            np.testing.assert_array_equal(inputs.lon, sic_to_nc.MODEL_LON)


def test_days_are_the_most_recent_whole_weeks(inputs_dir: Path) -> None:
    """30 overlapping days keep the last 28, still daily; the folder is named for the last day."""
    assert inputs_dir.name == "sic_inputs_2025-06-29"
    with xr.open_dataset(inputs_dir / "sea_ice_concentration.nc") as inputs:
        np.testing.assert_array_equal(inputs.time, pd.date_range(end="2025-06-29", periods=28))
        # SIC is day_index / 100 over the 31 SIC days; the kept 28 start at index 2.
        np.testing.assert_allclose(inputs["sea_ice_concentration"].isel(lat=0, lon=0), np.arange(2, 30) / 100,
                                   rtol=1e-6)


def test_anomaly_is_sic_minus_the_frozen_climatology(inputs_dir: Path) -> None:
    """The climatology is looked up by day of year and never recomputed."""
    with xr.open_dataset(inputs_dir / "sea_ice_concentration.nc") as sic, \
            xr.open_dataset(inputs_dir / "sic_climatology.nc") as clim, \
            xr.open_dataset(inputs_dir / "sic_anomaly.nc") as anomaly:
        np.testing.assert_allclose(anomaly["sic_anomaly"],
                                   sic["sea_ice_concentration"] - clim["sic_climatology"], atol=1e-6)
        # 2025-06-02 is day of year 153.
        np.testing.assert_allclose(clim["sic_climatology"].isel(time=0, lat=0, lon=0), 0.153, rtol=1e-5)


def test_forecast_follows_on_from_the_last_input_week(inputs_dir: Path, tmp_path: Path) -> None:
    """The folder's last day dates the forecast's week 1 a week later."""
    with xr.open_dataset(inputs_dir / "sea_ice_concentration.nc") as inputs:
        forecast = np.zeros((inputs.lat.size * inputs.lon.size, 8))
        assert sic_to_nc.forecast_to_nc(forecast, inputs, tmp_path).name == "sic_forecast_8w_2025-07-06.nc"


def test_feb_29_is_dropped_and_leap_years_shift_the_day_of_year(tmp_path: Path) -> None:
    """Ported as-is: after Feb 29 is dropped, a leap year's 1 March looks up day 61, not 60."""
    days = pd.date_range("2024-02-28", "2024-03-01")
    ds = daily("sea_ice_concentration", days, 0.5).to_dataset()
    ds = main_sea_ice_inputs.add_climatology_and_anomaly(ds, climatology_file(tmp_path / "clim.nc"))
    np.testing.assert_array_equal(ds.time, pd.to_datetime(["2024-02-28", "2024-03-01"]))
    np.testing.assert_allclose(ds["sic_climatology"].isel(lat=0, lon=0), [0.059, 0.061], rtol=1e-5)


def test_climatology_is_aligned_by_coordinate_not_position(tmp_path: Path) -> None:
    """A climatology stored south-last on -180..179 still lines up cell for cell."""
    days = pd.date_range("2025-03-01", periods=2)
    where = (sic_to_nc.MODEL_LAT[:, None] + 100) / 1000 + sic_to_nc.MODEL_LON[None, :] / 1e6
    ds = daily("sea_ice_concentration", days, 0.0).to_dataset()
    ds["sea_ice_concentration"] = ds["sea_ice_concentration"] * 0 + where.astype("float32")
    clim = xr.DataArray(np.broadcast_to(where, (365, *where.shape)), dims=("day_of_year", "lat", "lon"),
                        coords={"day_of_year": np.arange(1, 366), "lat": sic_to_nc.MODEL_LAT,
                                "lon": sic_to_nc.MODEL_LON})
    clim = clim.assign_coords(lon=((clim.lon + 180) % 360) - 180).sortby("lon").sortby("lat", ascending=False)
    clim.astype("float32").to_dataset(name="sic_climatology").to_netcdf(tmp_path / "clim.nc")

    ds = main_sea_ice_inputs.add_climatology_and_anomaly(ds, tmp_path / "clim.nc")
    np.testing.assert_allclose(ds["sic_anomaly"], 0, atol=1e-6)


def test_fewer_than_four_whole_weeks_fails_loudly() -> None:
    """The model needs four weeks; a short feed is an error, not a quietly shorter forecast input."""
    ds = daily("sea_ice_concentration", pd.date_range("2025-06-01", periods=27), 0.5).to_dataset()
    with pytest.raises(ValueError, match="3 whole week"):
        main_sea_ice_inputs.whole_weeks(ds)


def test_raw_downloads_are_kept_beside_the_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both downloads go to one persistent ``raw`` folder in the inputs dir, not a throwaway temp dir."""
    raw_dirs = []
    days = pd.date_range(end=LAST_DAY, periods=28)

    def fake_sic(_start: datetime.date, _end: datetime.date, raw_dir: Path) -> xr.DataArray:
        raw_dirs.append(raw_dir)
        return daily("sea_ice_concentration", days, 0.0) / 100

    def fake_era5(_start: datetime.date, _end: datetime.date, raw_dir: Path) -> xr.Dataset:
        raw_dirs.append(raw_dir)
        return xr.merge([daily(name, days, 1.0) for name in sic_data_from_era5.ERA5_VARS])

    monkeypatch.setattr(sic_data_from_nsidc, "daily_sic", fake_sic)
    monkeypatch.setattr(sic_data_from_era5, "daily_era5", fake_era5)
    main_sea_ice_inputs.main(tmp_path / "out", climatology_file(tmp_path / "clim.nc"), LAST_DAY)

    assert raw_dirs == [tmp_path / "out" / "raw"] * 2
