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

"""Tests for turning a raw CDS ERA5 download into daily fields on the model's 1-degree grid."""
import datetime
from pathlib import Path
import zipfile

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.eddie_antartica.sea_ice.inputs import sic_data_from_era5
from src.eddie_antartica.sea_ice.model import sic_to_nc

# Two days at two hours each: enough to tell a daily mean from a daily sum.
HOURS = pd.to_datetime(["2025-06-01T00", "2025-06-01T12", "2025-06-02T00", "2025-06-02T12"])
LATITUDES = np.arange(-40, -90.25, -0.25)        # CDS order: north first
LONGITUDES = np.arange(0, 360, 0.25)


def stream(name: str, values: np.ndarray) -> xr.Dataset:
    """
    Build one inner CDS file: a single short-named variable on ``valid_time``.

    Parameters
    ----------
    name : str
        The CDS short name.
    values : numpy.ndarray
        One value per hour, broadcast over the grid.

    Returns
    -------
    xarray.Dataset
        The variable on ``valid_time``, ``latitude``, ``longitude``.
    """
    field = np.broadcast_to(values[:, None, None], (HOURS.size, LATITUDES.size, LONGITUDES.size))
    return xr.Dataset({name: (("valid_time", "latitude", "longitude"), field.astype("float32"))},
                      coords={"valid_time": HOURS, "latitude": LATITUDES, "longitude": LONGITUDES})


def cds_zip(directory: Path) -> Path:
    """
    Write a CDS-style download: a ZIP named ``.nc`` holding an instant and an accumulated file.

    Parameters
    ----------
    directory : pathlib.Path
        Where to write it.

    Returns
    -------
    pathlib.Path
        The ZIP.
    """
    stream("t2m", np.array([250.0, 260.0, 270.0, 280.0])).to_netcdf(directory / "instant.nc")
    stream("tp", np.full(HOURS.size, 0.001)).to_netcdf(directory / "accum.nc")
    path = directory / "era5_202506.nc"
    with zipfile.ZipFile(path, "w") as archive:
        archive.write(directory / "instant.nc", "data_stream-oper_stepType-instant.nc")
        archive.write(directory / "accum.nc", "data_stream-oper_stepType-accum.nc")
    return path


def test_cds_zip_becomes_daily_long_named_fields_on_the_model_grid(tmp_path: Path) -> None:
    """Instant fields are daily means, precipitation a daily sum, on 50 x 360 at midnight."""
    era5 = sic_data_from_era5.build_era5_series([cds_zip(tmp_path)])
    np.testing.assert_array_equal(era5.lat, sic_to_nc.MODEL_LAT)
    np.testing.assert_array_equal(era5.lon, sic_to_nc.MODEL_LON)
    np.testing.assert_array_equal(era5.time, pd.to_datetime(["2025-06-01", "2025-06-02"]))
    np.testing.assert_allclose(era5["2m_temperature"].isel(lat=0, lon=0), [255.0, 275.0])
    np.testing.assert_allclose(era5["total_precipitation"].isel(lat=0, lon=0), [0.002, 0.002])



def test_months_with_different_history_notes_still_join(tmp_path: Path) -> None:
    """Each CDS month carries its own ``history`` attribute; joining two months must not trip over it."""
    paths = []
    for month, history in (("2025-06-30", "converted 04:27"), ("2025-07-01", "converted 04:38")):
        month_ds = stream("t2m", np.full(HOURS.size, 260.0)).assign_coords(
            valid_time=pd.date_range(month, periods=HOURS.size, freq="6h")).assign_attrs(history=history)
        paths.append(tmp_path / f"era5_{month}.nc")
        month_ds.to_netcdf(paths[-1])

    era5 = sic_data_from_era5.build_era5_series(paths)

    np.testing.assert_array_equal(era5.time, pd.to_datetime(["2025-06-30", "2025-07-01"]))

class FakeCds:
    """Stands in for ``cdsapi.Client``: records each request and writes a dummy file."""

    requests: list = []

    def retrieve(self, _dataset: str, request: dict, target: str) -> None:
        """
        Record the request's month and days, and write the target.

        Parameters
        ----------
        _dataset : str
            The CDS dataset name.
        request : dict
            The CDS request.
        target : str
            Where to write the download.
        """
        FakeCds.requests.append((request["month"], request["day"][0], request["day"][-1]))
        Path(target).write_bytes(b"era5")


def test_finished_months_are_fetched_whole_once_and_kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A finished month is downloaded whole and reused; the month still running is fetched up to the last day."""
    monkeypatch.setattr(sic_data_from_era5.cdsapi, "Client", FakeCds)
    FakeCds.requests = []

    sic_data_from_era5.download_era5(datetime.date(2025, 5, 27), datetime.date(2025, 7, 1), tmp_path)
    assert FakeCds.requests == [("05", "01", "31"), ("06", "01", "30"), ("07", "01", "01")]

    FakeCds.requests = []
    got = sic_data_from_era5.download_era5(datetime.date(2025, 6, 3), datetime.date(2025, 7, 8), tmp_path)
    assert FakeCds.requests == [("07", "01", "08")]
    assert [p.name for p in got] == ["era5_20250601-30.nc", "era5_20250701-08.nc"]
    # The superseded part of July is gone; finished months stay.
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "era5_20250501-31.nc", "era5_20250601-30.nc", "era5_20250701-08.nc"]
