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
Tests for reading sea ice concentration forecast time series out of the NetCDF.

The fixture is built here with plain xarray rather than by the export notebook, so these
assert the reader against an independently written file. A fixture produced by the same
code the reader is paired with would pass even if both shared a wrong assumption.

The GeoTIFF fixture is edge-registered -- ``WEST``/``NORTH`` are cell edges -- while a CF
NetCDF names cell centres, so the centres are derived from the GeoTIFF's own constants.
That is what lets the last test assert the two readers return the same series.
"""
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from rasterio.crs import CRS
import xarray as xr

from src.eddie_antartica.sea_ice.model import sic_data_from_nc, sic_data_from_raster
from tests.test_sea_ice.test_model.test_sic_data_from_raster import (
    N_BANDS, N_LAT, N_LON, NORTH, TIMES, VALUES, WEST, _write_fixture)

#: Cell centres, north first, matching the GeoTIFF's north-up row order.
LATITUDES = NORTH - 0.5 - np.arange(N_LAT, dtype="float64")
LONGITUDES = WEST + 0.5 + np.arange(N_LON, dtype="float64")

#: Centre of the north-west cell.
LON0, LAT0 = float(LONGITUDES[0]), float(LATITUDES[0])


def encoded_values() -> np.ndarray:
    """
    Build a ``(step, lat, lon)`` array whose every cell value encodes its own position.

    Cell value is ``step * 100 + row * 10 + col``, so an indexing mistake produces an
    obviously wrong number rather than a plausible one.

    Returns
    -------
    numpy.ndarray
        Shape ``(N_BANDS, N_LAT, N_LON)``, matching the GeoTIFF fixture's values.
    """
    steps = (np.arange(N_BANDS) + 1) * 100
    return (steps[:, None, None]
            + (np.arange(N_LAT) * 10)[None, :, None]
            + np.arange(N_LON)[None, None, :]).astype("float32")


def forecast_nc(tmp_path: Path, values: np.ndarray = None, times: List[str] = None) -> Path:
    """
    Write a ``(step, lat, lon)`` grid out as the CF NetCDF the reader expects.

    Parameters
    ----------
    tmp_path : Path
        Pytest per-test temporary directory.
    values : numpy.ndarray
        A ``(step, lat, lon)`` grid, or None for the standard encoded fixture.
    times : List[str]
        ISO-8601 timestamp per step, or None for the shared fixture times.

    Returns
    -------
    Path
        Path to the written NetCDF.
    """
    values = encoded_values() if values is None else values
    times = TIMES if times is None else times
    dataset = xr.Dataset(
        {sic_data_from_nc.VARIABLE: (("time", "lat", "lon"), values, {"grid_mapping": "crs"})},
        coords={
            "time": ("time", pd.to_datetime([stamp.removesuffix("Z") for stamp in times])),
            "lat": ("lat", LATITUDES, {"units": "degrees_north", "axis": "Y"}),
            "lon": ("lon", LONGITUDES, {"units": "degrees_east", "axis": "X"}),
            "crs": ((), np.int32(0), {"grid_mapping_name": "latitude_longitude",
                                      "crs_wkt": CRS.from_epsg(4326).to_wkt()}),
        },
    )
    dataset[sic_data_from_nc.VARIABLE].encoding["_FillValue"] = np.float32(np.nan)
    path = tmp_path / "forecast.nc"
    dataset.to_netcdf(path, format="NETCDF4_CLASSIC")
    return path


def test_samples_the_clicked_cell_across_every_step(tmp_path: Path) -> None:
    """The right cell is read from every step, in the two-column shape Terria charts."""
    netcdf = forecast_nc(tmp_path)
    series = sic_data_from_nc.point_series(LON0, LAT0, netcdf)

    assert list(series.columns) == ["Time (UTC)", VALUES]
    assert list(series["Time (UTC)"]) == TIMES
    # North-west cell centre is row 0, column 0 of each step.
    assert list(series[VALUES]) == [100.0, 200.0, 300.0]
    # South-east cell centre is the final row and column.
    corner = sic_data_from_nc.point_series(float(LONGITUDES[-1]), float(LATITUDES[-1]), netcdf)
    last = (N_LAT - 1) * 10 + (N_LON - 1)
    assert list(corner[VALUES]) == [100.0 + last, 200.0 + last, 300.0 + last]
    # An interior point picks the cell containing it, not a neighbour.
    assert sic_data_from_nc.point_series(-177.9, -41.9, netcdf)[VALUES].iloc[0] == 112.0


def test_longitude_beyond_180_is_wrapped(tmp_path: Path) -> None:
    """A 0-360 longitude is wrapped into the convention the file uses before sampling."""
    netcdf = forecast_nc(tmp_path)
    wrapped = sic_data_from_nc.point_series(182.5, LAT0, netcdf)
    assert list(wrapped[VALUES]) == list(sic_data_from_nc.point_series(-177.5, LAT0, netcdf)[VALUES])


def test_click_inside_the_westernmost_cell_is_not_wrapped_off_the_grid(tmp_path: Path) -> None:
    """
    A click west of the westernmost cell *centre* still lands in that cell.

    The wrap is measured from the grid's western edge. Measuring it from ``lon.min()`` --
    a cell centre -- sends anything in that cell's western half a full 360 degrees away,
    off the grid, and the route then returns an empty chart with no error at all.
    """
    netcdf = forecast_nc(tmp_path)
    inside_first_cell = float(LONGITUDES[0]) - 0.4

    series = sic_data_from_nc.point_series(inside_first_cell, LAT0, netcdf)
    assert list(series[VALUES]) == [100.0, 200.0, 300.0]


def test_point_outside_extent_returns_empty_frame(tmp_path: Path) -> None:
    """A click off the grid yields headers with no rows rather than an error."""
    series = sic_data_from_nc.point_series(0.0, 0.0, forecast_nc(tmp_path))
    assert series.empty
    assert list(series.columns) == ["Time (UTC)", VALUES]


def test_missing_values_chart_as_gaps(tmp_path: Path) -> None:
    """A NaN cell reads back as NaN, so the chart shows a gap rather than a zero."""
    values = encoded_values()
    values[:, 0, 0] = np.nan

    assert sic_data_from_nc.point_series(LON0, LAT0, forecast_nc(tmp_path, values))[VALUES].isna().all()


def test_netcdf_and_geotiff_routes_return_the_same_csv(tmp_path: Path) -> None:
    """
    The same forecast charts identically whichever file it is read from.

    This is the assertion that catches a georeferencing mistake: the GeoTIFF is
    edge-registered and the NetCDF names cell centres, so a flipped row order, a half-cell
    offset or a transposed grid makes these two disagree while each on its own still looks
    like a plausible ice map. The probes include the outermost half-cell, where wrapping
    about a cell centre rather than the grid edge silently returned no rows at all.
    """
    values = encoded_values()
    geotiff = _write_fixture(tmp_path / "forecast.tif", values, TIMES)
    netcdf = forecast_nc(tmp_path, values)

    probes = [(LON0, LAT0),
              (-177.9, -41.9),
              (float(LONGITUDES[-1]), float(LATITUDES[-1])),
              (float(LONGITUDES[0]) - 0.4, LAT0),
              (float(LONGITUDES[-1]) + 0.4, LAT0)]
    for longitude, latitude in probes:
        from_raster = sic_data_from_raster.sic_forecast_series(longitude, latitude, geotiff)
        from_netcdf = sic_data_from_nc.point_series(longitude, latitude, netcdf)
        assert from_netcdf.to_csv(index=False) == from_raster.to_csv(index=False), (longitude, latitude)


def test_newest_forecast_is_the_latest_week_1(tmp_path: Path) -> None:
    """ISO dates sort as text; the stable GeoTIFF and other files are not forecasts."""
    assert sic_data_from_nc.latest_forecast(tmp_path) is None
    for name in ("sic_forecast_8w_2024-01-01.nc", "sic_forecast_8w_timeseries.nc", "sic_forecast_8w_2024-01-08.nc",
                 "sic_forecast_8w.tif", "sic_inputs_2024-01-15.nc"):
        (tmp_path / name).touch()

    assert sic_data_from_nc.latest_forecast(tmp_path) == tmp_path / "sic_forecast_8w_2024-01-08.nc"


def test_ice_the_map_does_not_draw_charts_as_open_water(tmp_path: Path) -> None:
    """
    Below 0.01 the map's style draws nothing (``sic_forecast_8w.sld``: "Open water"), so the chart says 0 there too.

    The model's sigmoid never reaches 0, so without this a click on a blank continent charted a faint 0.007 curve.
    0.01 itself is drawn, so it is charted; a missing value stays a gap.
    """
    values = encoded_values()
    values[:, 0, 0] = [0.009, 0.01, np.nan]
    netcdf = forecast_nc(tmp_path, values)
    geotiff = _write_fixture(tmp_path / "forecast.tif", values, TIMES)

    for series in (sic_data_from_nc.point_series(LON0, LAT0, netcdf),
                   sic_data_from_raster.sic_forecast_series(LON0, LAT0, geotiff)):
        np.testing.assert_allclose(series[VALUES], [0.0, 0.01, np.nan], rtol=1e-6)
