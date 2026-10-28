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

"""Tests for regridding NSIDC NRT CDR polar-stereographic files onto the model's 1-degree grid."""
from pathlib import Path

import numpy as np
import pytest
import pandas as pd
import xarray as xr

from src.eddie_antartica.sea_ice.inputs import sic_data_from_nsidc
from src.eddie_antartica.sea_ice.model import sic_to_nc

# A coarse 250 km EPSG:3412 grid over the Southern Ocean, enough to cover the model's band.
XY = np.arange(-5_000_000, 5_000_001, 250_000, dtype="float64")


def cdr_file(directory: Path, day: str, sic: np.ndarray) -> Path:
    """
    Write a minimal NRT CDR daily file, shaped like ``sic_pss25_YYYYMMDD_<platform>_icdr_v04r00.nc``.

    Parameters
    ----------
    directory : pathlib.Path
        Where to write it.
    day : str
        ``YYYY-MM-DD``.
    sic : numpy.ndarray
        ``(y, x)`` concentration, 0..1 with NaN for land / missing.

    Returns
    -------
    pathlib.Path
        The written file.
    """
    path = directory / f"sic_pss25_{day.replace('-', '')}_F17_icdr_v04r00.nc"
    xr.Dataset(
        {"cdr_seaice_conc": (("time", "y", "x"), sic[None].astype("float32")),
         "crs": ((), 0, {"proj4text": "+proj=stere +lat_0=-90 +lat_ts=-70 +lon_0=0 +k=1 +x_0=0 +y_0=0 "
                                      "+a=6378273 +rf=298.279411123064 +units=m +no_defs"})},
        coords={"time": [pd.Timestamp(day) + pd.Timedelta(hours=12)], "y": XY[::-1], "x": XY},
    ).to_netcdf(path)
    return path


def test_uniform_ice_regrids_to_the_same_value_on_the_model_grid(tmp_path: Path) -> None:
    """A uniform field survives the regrid unchanged, on 50 x 360 and dated by day."""
    path = cdr_file(tmp_path, "2025-06-01", np.full((XY.size, XY.size), 0.6))
    sic = sic_data_from_nsidc.build_sic_series([path])
    assert sic.dims == ("time", "lat", "lon")
    np.testing.assert_array_equal(sic.lat, sic_to_nc.MODEL_LAT)
    np.testing.assert_array_equal(sic.lon, sic_to_nc.MODEL_LON)
    assert sic.time.values[0] == np.datetime64("2025-06-01")
    np.testing.assert_allclose(sic.values, 0.6, rtol=1e-6)


def test_land_and_missing_cells_count_as_no_ice(tmp_path: Path) -> None:
    """NaN (land / missing) feeds 0 into the regrid instead of being back-filled from nearby ice."""
    path = cdr_file(tmp_path, "2025-06-01", np.full((XY.size, XY.size), np.nan))
    np.testing.assert_array_equal(sic_data_from_nsidc.build_sic_series([path]).values, 0.0)



def test_flag_values_above_one_count_as_no_ice(tmp_path: Path) -> None:
    """Coast / land flags (> 1, e.g. 2.53, 2.54) are no ice, as in the dataprocessor; clipping would make them full ice."""
    path = cdr_file(tmp_path, "2025-06-01", np.full((XY.size, XY.size), 2.54))
    np.testing.assert_array_equal(sic_data_from_nsidc.build_sic_series([path]).values, 0.0)

def test_files_already_downloaded_are_not_fetched_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A rerun reuses the raw files it kept, and only fetches the days it does not have yet."""
    names = ["sic_pss25_20250601_F18_icdr_v04r00.nc", "sic_pss25_20250602_F18_icdr_v04r00.nc"]
    (tmp_path / names[0]).write_bytes(b"kept")
    fetched = []

    def fake_retrieve(url: str, path: Path) -> None:
        fetched.append(url)
        Path(path).write_bytes(b"new")

    monkeypatch.setattr(sic_data_from_nsidc, "_http_listing", lambda url: names)
    monkeypatch.setattr(sic_data_from_nsidc.urllib.request, "urlretrieve", fake_retrieve)

    got = sic_data_from_nsidc.download_nsidc_cdr(pd.Timestamp("2025-06-01"), pd.Timestamp("2025-06-02"), tmp_path)

    assert [url.rsplit("/", 1)[-1] for url in fetched] == [names[1]]
    assert got == [tmp_path / name for name in names]
    assert sorted(p.name for p in tmp_path.iterdir()) == names
