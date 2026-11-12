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
import pytest
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
    # Raw, 179.8 is inside the 180 cell, which straddles 180 degrees.
    np.testing.assert_array_equal(sic_data_from_nc.point_series(179.8, -42.0, path, "nearest").iloc[:, 1].to_numpy(),
                                  encoded_forecast()[node(180, -42.0)].astype("float32"))


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
        assert (raster.width, raster.height) == (362, 3)
        assert np.isnan(raster.nodata)                   # flags and land render transparent
        pixels = [value[0] for value in raster.sample([(10.0, -41.0), (-180.0, -42.0), (179.8, -42.0)])]
    assert pixels == [week8[node(10, -41.0)], week8[node(180, -42.0)], week8[node(180, -42.0)]]


def test_geotiff_has_a_cell_on_both_sides_of_the_antimeridian(tmp_path: Path) -> None:
    """Bilinear blends each pixel with its neighbours, so a missing neighbour west of -180 draws a seam at 180."""
    nc_path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)
    tif_path = sic_to_nc.nc_to_gtiff(nc_path, tmp_path / "sic_forecast_8w.tif")

    week8 = encoded_forecast()[:, -1].astype("float32")
    with rio.open(tif_path) as raster:
        assert (raster.bounds.left, raster.bounds.right) == (-181.5, 180.5)
        pixels = [value[0] for value in raster.sample([(-180.8, -42.0), (180.2, -42.0)])]
    assert pixels == [week8[node(179, -42.0)], week8[node(180, -42.0)]]


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
        assert raster.bounds.left == -181.5                                 # the -180 column, centred on its label
        pixels = [value[0] for value in raster.sample([(10.0, -41.0), (-10.0, -43.0)])]
    assert pixels == [week8[node(10, -41.0)], week8[node(350, -43.0)]]


def land_sea_mask(path: Path, step: float, land: np.ndarray, wrapped: bool = False) -> Path:
    """
    Write a ``land_sea_mask.nc`` that is all sea except for some boxes.

    Parameters
    ----------
    path : Path
        Where to write the file.
    step : float
        Resolution of the mask in degrees.
    land : numpy.ndarray
        Rows of ``(west, east, south, north)`` in 0..360 longitudes: mask cells centred inside a box are all land.
    wrapped : bool
        Label longitudes -180..180 and put the north first, instead of 0..360 with the south first.

    Returns
    -------
    Path
        The written file.
    """
    fraction = xr.DataArray(0.0, dims=("lat", "lon"), name="land_sea_mask",
                            coords={"lat": np.arange(-42.5 + step / 2, -40.5, step), "lon": np.arange(0, 360, step)})
    for west, east, south, north in land:
        in_box = (fraction.lon >= west) & (fraction.lon <= east) & (fraction.lat >= south) & (fraction.lat <= north)
        fraction = fraction.where(~in_box, 1.0)
    if wrapped:
        fraction = fraction.assign_coords(lon=((fraction.lon + 180) % 360) - 180).sortby("lat", ascending=False)
    fraction.to_dataset().to_netcdf(path)
    return path


def test_display_geotiff_is_cut_along_a_coast_finer_than_the_model_grid(tmp_path: Path) -> None:
    """The fine grid is cut where the mask is land: a half-land model cell is half drawn, and unmasked rows are sea."""
    nc_path = sic_to_nc.forecast_to_nc(encoded_forecast(), model_inputs(), tmp_path)
    mask_path = land_sea_mask(tmp_path / "land_sea_mask.nc", 0.25,
                              np.array([(9.5, 10.5, -42.5, -41.5), (20.25, 20.5, -42.5, -41.5)]))

    tif_path = sic_to_nc.display_gtiff(nc_path, tmp_path / "display.tif", 7, mask_path)

    week8 = encoded_forecast()[:, -1].astype("float32")
    with rio.open(tif_path) as raster:
        assert raster.crs.to_epsg() == 4326
        assert (raster.count, raster.dtypes[0], raster.compression.name) == (1, "float32", "lzw")
        assert np.isnan(raster.nodata)
        assert (raster.width, raster.height) == (7200, 60)
        np.testing.assert_allclose(raster.bounds, (-180.0, -43.5, 180.0, -40.5))
        np.testing.assert_allclose(raster.res, sic_to_nc.DISPLAY_RESOLUTION)
        points = [(30.025, -41.025), (10.025, -43.025), (10.0, -42.0), (19.8, -42.0), (20.3, -42.0)]
        sea, south_of_the_mask, land, half_sea, half_land = (value[0] for value in raster.sample(points))
    assert sea == pytest.approx(week8[node(30, -41.0)], abs=2e-3)
    assert south_of_the_mask == pytest.approx(week8[node(10, -43.0)], abs=2e-3)
    assert not np.isnan(half_sea)
    assert np.isnan([land, half_land]).all()


def test_a_model_cell_that_is_mostly_land_is_left_out_of_the_blend(tmp_path: Path) -> None:
    """A fine mask is averaged over the model cell, so a strip of sea through the cell's centre does not make it sea."""
    forecast = np.full_like(encoded_forecast(), 0.2)
    forecast[node(10, -42.0)] = 0.9
    nc_path = sic_to_nc.forecast_to_nc(forecast, model_inputs(), tmp_path)
    mask_path = land_sea_mask(tmp_path / "land_sea_mask.nc", 0.25,
                              np.array([(9.5, 9.9, -42.5, -41.5), (10.1, 10.5, -42.5, -41.5)]))

    tif_path = sic_to_nc.display_gtiff(nc_path, tmp_path / "display.tif", 0, mask_path)

    with rio.open(tif_path) as raster:
        strip_of_sea = next(raster.sample([(10.025, -42.025)]))[0]
        assert np.nanmax(raster.read(1)) <= np.float32(0.2) + 1e-6
    assert strip_of_sea == pytest.approx(0.2)


def test_smooth_display_geotiff_blends_sea_cells_only(tmp_path: Path) -> None:
    """A high value the model gives a land cell never reaches the sea around it, and 180 degrees shows no seam."""
    forecast = np.full_like(encoded_forecast(), 0.2)
    forecast[node(179, -41.0)] = 0.1
    forecast[node(10, -42.0)] = 0.9
    nc_path = sic_to_nc.forecast_to_nc(forecast, model_inputs(), tmp_path)
    mask_path = land_sea_mask(tmp_path / "land_sea_mask.nc", 1.0, np.array([(10.0, 10.0, -42.0, -42.0)]),
                              wrapped=True)

    tif_path = sic_to_nc.display_gtiff(nc_path, tmp_path / "smooth.tif", 0, mask_path)

    with rio.open(tif_path) as raster:
        pixels = raster.read(1)
        land, beside_land, west_of_180, east_of_180 = (value[0] for value in raster.sample(
            [(10.0, -42.0), (10.8, -42.0), (179.99, -41.0), (-179.99, -41.0)]))
    assert np.isnan(land)
    assert beside_land == pytest.approx(0.2)
    assert np.nanmax(pixels) <= np.float32(0.2) + 1e-6
    assert np.isnan(pixels).sum() < 21 * 21
    assert west_of_180 == pytest.approx(0.1975, abs=1e-4)
    assert east_of_180 == pytest.approx(0.2)
