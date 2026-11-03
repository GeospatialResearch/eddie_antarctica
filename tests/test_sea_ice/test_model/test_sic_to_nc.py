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
Tests for writing the sea ice forecast and its inputs as CF NetCDF, and the map GeoTIFF.

The model inputs are built on the model's native grid -- latitude ascending, longitude
0..359, cell centres -- and every forecast value encodes its own node and week, so a
mirrored, shifted or wrapped grid produces an obviously wrong number. Values are read back
through the app's own NetCDF reader, the code that serves the chart.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio as rio
import xarray as xr

from src.eddie_antartica.sea_ice.model import sic_data_from_nc, sic_to_nc

LATITUDES = np.array([-43.0, -42.0, -41.0])     # ascending, as the model holds them
LONGITUDES = np.arange(360, dtype="float64")    # 0..359
INPUT_TIMES = pd.date_range("2023-12-04", periods=4, freq="7D")
N_WEEKS = 8


def model_inputs() -> xr.Dataset:
    """
    Build the past-four-weeks dataset the model is run on.

    Returns
    -------
    xarray.Dataset
        Coordinates only: ``time``, ``lat`` and ``lon`` on the model's native grid.
    """
    return xr.Dataset(coords={"time": INPUT_TIMES, "lat": LATITUDES, "lon": LONGITUDES})


def encoded_forecast() -> np.ndarray:
    """
    Build a ``(node, week)`` forecast whose every value encodes its own position.

    Returns
    -------
    numpy.ndarray
        ``week * 0.1 + node * 1e-4``, all within 0..1 so none are masked as flags.
    """
    nodes = np.arange(LATITUDES.size * LONGITUDES.size)
    return np.arange(N_WEEKS)[None, :] * 0.1 + nodes[:, None] * 1e-4


def node(longitude: float, latitude: float) -> int:
    """
    Find the model node holding a 0..359 longitude and a latitude.

    Parameters
    ----------
    longitude : float
        Cell-centre longitude in the model's 0..359 convention.
    latitude : float
        Cell-centre latitude.

    Returns
    -------
    int
        Row of the ``(node, week)`` forecast for that cell.
    """
    return int(np.flatnonzero(LATITUDES == latitude)[0]) * LONGITUDES.size + int(longitude)


def test_forecast_weeks_follow_on_from_the_last_input_week(tmp_path: Path) -> None:
    """Week 1 is valid one week after the last input; the file is named for week 1."""
    path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)

    assert path.name == "sic_forecast_8w_2024-01-01.nc"
    with xr.open_dataset(path) as dataset:
        expected = pd.date_range("2024-01-01", periods=N_WEEKS, freq="7D")
        assert (pd.DatetimeIndex(dataset["time"].values) == expected).all()


def test_chart_returns_the_model_values_for_the_clicked_cell(tmp_path: Path) -> None:
    """Clicks in either longitude convention read the node the model wrote there."""
    path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)

    for click, model_cell in (((10.0, -41.0), (10, -41.0)),
                              ((-10.0, -43.0), (350, -43.0)),
                              ((350.0, -43.0), (350, -43.0)),
                              ((-180.0, -42.0), (180, -42.0))):
        series = sic_data_from_nc.point_series(*click, path)
        expected = encoded_forecast()[node(*model_cell)].astype("float32")
        np.testing.assert_array_equal(series.iloc[:, 1].to_numpy(), expected, err_msg=str(click))
    # Between centres the chart blends as the map draws it, across 180 degrees too: 179.8 is 0.8 of the way to 180.
    blend = 0.2 * encoded_forecast()[node(179, -42.0)] + 0.8 * encoded_forecast()[node(180, -42.0)]
    np.testing.assert_allclose(sic_data_from_nc.point_series(179.8, -42.0, path).iloc[:, 1], blend, rtol=1e-6)


def test_land_and_pole_hole_flags_become_missing(tmp_path: Path) -> None:
    """Values above 1 are NSIDC flags, not concentrations."""
    forecast = encoded_forecast()
    forecast[node(10, -41.0)] = 254
    path = sic_to_nc.forecast_to_nc(forecast, model_inputs(), tmp_path)

    assert sic_data_from_nc.point_series(10.0, -41.0, path).iloc[:, 1].isna().all()


def test_geotiff_is_the_last_week_with_the_antimeridian_column_repeated(tmp_path: Path) -> None:
    """The map shows week 8, in EPSG:4326, with no gap between 179.5 and 180."""
    nc_path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)
    tif_path = sic_to_nc.nc_to_gtiff(nc_path, tmp_path / "sic_forecast_8w.tif")

    week8 = encoded_forecast()[:, -1].astype("float32")
    with rio.open(tif_path) as raster:
        assert raster.crs.to_epsg() == 4326
        assert (raster.width, raster.height) == (361, 3)
        assert np.isnan(raster.nodata)                   # flags and land render transparent
        pixels = [value[0] for value in raster.sample([(10.0, -41.0), (-180.0, -42.0), (179.8, -42.0)])]
    assert pixels == [week8[node(10, -41.0)], week8[node(180, -42.0)], week8[node(180, -42.0)]]


def test_inputs_in_either_longitude_convention_write_the_same_grid(tmp_path: Path) -> None:
    """A preprocessed dataset on 0..359 or -180..179 is stored identically."""
    values = np.random.default_rng(0).uniform(0, 1, (LATITUDES.size, LONGITUDES.size)).astype("float32")
    native = xr.Dataset({"sic": (("lat", "lon"), values)}, coords={"lat": LATITUDES, "lon": LONGITUDES})
    wrapped = native.assign_coords(lon=((native.lon + 180) % 360) - 180)

    with xr.open_dataset(sic_to_nc.to_cf_netcdf(native, tmp_path / "a.nc"), decode_coords="all") as first, \
            xr.open_dataset(sic_to_nc.to_cf_netcdf(wrapped, tmp_path / "b.nc"), decode_coords="all") as second:
        xr.testing.assert_identical(first, second)
        assert first.attrs["Conventions"] == "CF-1.8"
        assert first.rio.crs.to_epsg() == 4326
        assert float(first.lat[0]) > float(first.lat[-1])                 # north first
        assert (float(first.lon[0]), float(first.lon[-1])) == (-180.0, 179.0)


def test_geotiff_can_be_any_week(tmp_path: Path) -> None:
    """The WPS process asks for one week by its 0-based index into ``time``."""
    nc_path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)
    tif_path = sic_to_nc.nc_to_gtiff(nc_path, tmp_path / "week3.tif", week=2)

    week3 = encoded_forecast()[:, 2].astype("float32")
    with rio.open(tif_path) as raster:
        assert next(raster.sample([(10.0, -41.0)]))[0] == week3[node(10, -41.0)]


def test_geotiff_from_a_native_order_file_is_north_up_on_minus_180_to_180(tmp_path: Path) -> None:
    """A file kept in the model's own order (lat ascending, lon 0..359) still maps onto EPSG:4326 bounds."""
    nc_path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)
    with xr.open_dataset(nc_path, decode_coords="all") as dataset:
        native = dataset.assign_coords(lon=dataset.lon % 360).sortby("lon").sortby("lat").load()
    native.to_netcdf(tmp_path / "native.nc")
    tif_path = sic_to_nc.nc_to_gtiff(tmp_path / "native.nc", tmp_path / "native.tif")

    week8 = encoded_forecast()[:, -1].astype("float32")
    with rio.open(tif_path) as raster:
        assert raster.transform.e < 0                                      # north up
        assert raster.bounds.left == -180.5                                 # the -180 column, centred on its label
        pixels = [value[0] for value in raster.sample([(10.0, -41.0), (-10.0, -43.0)])]
    assert pixels == [week8[node(10, -41.0)], week8[node(350, -43.0)]]
