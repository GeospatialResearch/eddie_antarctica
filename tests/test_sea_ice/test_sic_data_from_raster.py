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


"""Tests for reading sea ice concentration forecast time series out of a GeoTIFF."""
import math
from pathlib import Path
from typing import List

import numpy as np
import rasterio as rio
from rasterio.transform import from_origin

from src.eddie_antartica.sea_ice import sic_data_from_raster

# The fixture mirrors the real forecast grid: 1-degree cells, EPSG:4326, north-up, and
# edge-registered, so WEST/NORTH are cell edges and the full-size raster spans exactly
# -180..180 and -90..-40. Centre-registering it would shift every cell half a degree and
# put the south edge at -90.5, which is not a latitude that exists.
N_BANDS, N_LAT, N_LON = 3, 4, 8
WEST, NORTH = -180.0, -40.0
LON0, LAT0 = WEST + 0.5, NORTH - 0.5  # Centre of the north-west cell.
TIMES = ["2023-01-01T00:00:00Z", "2023-01-08T00:00:00Z", "2023-01-15T00:00:00Z"]
VALUES = "Sea ice concentration (fraction)"


def _write_fixture(path: Path, values: np.ndarray, times: List[str], nodata: float = math.nan) -> Path:
    """
    Write a north-up EPSG:4326 GeoTIFF with one TIME-tagged band per timestep.

    Parameters
    ----------
    path : Path
        Destination file path.
    values : numpy.ndarray
        Array of shape (band, row, col) to write.
    times : List[str]
        ISO-8601 timestamp for each band, written as the band's TIME tag.
    nodata : float
        Nodata value recorded in the file header.

    Returns
    -------
    Path
        The path that was written.
    """
    with rio.open(path, "w", driver="GTiff", height=values.shape[1], width=values.shape[2],
                  count=values.shape[0], dtype="float32", crs="EPSG:4326",
                  transform=from_origin(WEST, NORTH, 1, 1), nodata=nodata) as dst:
        for band, timestamp in enumerate(times, start=1):
            dst.write(values[band - 1].astype("float32"), band)
            dst.update_tags(band, TIME=timestamp)
    return path


def _forecast_tif(tmp_path: Path) -> Path:
    """
    Build a raster whose every cell value encodes its own position.

    Cell value is ``band * 100 + row * 10 + col``, so an indexing mistake produces an
    obviously wrong number rather than a plausible one.

    Parameters
    ----------
    tmp_path : Path
        Pytest per-test temporary directory.

    Returns
    -------
    Path
        Path to the written GeoTIFF.
    """
    values = np.empty((N_BANDS, N_LAT, N_LON), dtype="float32")
    for band in range(N_BANDS):
        for row in range(N_LAT):
            for col in range(N_LON):
                values[band, row, col] = (band + 1) * 100 + row * 10 + col
    return _write_fixture(tmp_path / "forecast.tif", values, TIMES)


def test_samples_the_clicked_cell_across_every_band(tmp_path: Path) -> None:
    """The right cell is read from every band, in the two-column shape Terria charts."""
    tif = _forecast_tif(tmp_path)
    series = sic_data_from_raster.sic_forecast_series(LON0, LAT0, tif)

    assert list(series.columns) == ["Time (UTC)", VALUES]
    assert list(series["Time (UTC)"]) == TIMES
    # North-west cell centre is row 0, column 0 of each band.
    assert list(series[VALUES]) == [100.0, 200.0, 300.0]
    # South-east cell centre is the final row and column.
    corner = sic_data_from_raster.sic_forecast_series(WEST + N_LON - 0.5, NORTH - N_LAT + 0.5, tif)
    last = (N_LAT - 1) * 10 + (N_LON - 1)
    assert list(corner[VALUES]) == [100.0 + last, 200.0 + last, 300.0 + last]
    # An interior point picks the cell containing it, not a neighbour.
    assert sic_data_from_raster.sic_forecast_series(-177.9, -41.9, tif)[VALUES].iloc[0] == 112.0
    # The -180 edge is inside the raster, not outside it.
    assert sic_data_from_raster.sic_forecast_series(WEST, LAT0, tif)[VALUES].iloc[0] == 100.0


def test_longitude_beyond_180_is_wrapped(tmp_path: Path) -> None:
    """A 0-360 longitude is wrapped into -180..180 before sampling."""
    tif = _forecast_tif(tmp_path)
    wrapped = sic_data_from_raster.sic_forecast_series(183.0, LAT0, tif)
    assert list(wrapped[VALUES]) == list(sic_data_from_raster.sic_forecast_series(-177.0, LAT0, tif)[VALUES])


def test_point_outside_extent_returns_empty_frame(tmp_path: Path) -> None:
    """A click off the raster yields headers with no rows rather than an error."""
    series = sic_data_from_raster.sic_forecast_series(0.0, 0.0, _forecast_tif(tmp_path))
    assert series.empty
    assert list(series.columns) == ["Time (UTC)", VALUES]


def test_explicit_nodata_becomes_nan(tmp_path: Path) -> None:
    """A sentinel nodata value becomes NaN so the chart shows a gap."""
    values = np.full((1, N_LAT, N_LON), -9999.0, dtype="float32")
    path = _write_fixture(tmp_path / "nodata.tif", values, TIMES[:1], nodata=-9999.0)
    assert sic_data_from_raster.sic_forecast_series(LON0, LAT0, path)[VALUES].isna().all()


def test_band_without_time_tag_falls_back_to_description(tmp_path: Path) -> None:
    """A band with no TIME tag uses its description instead."""
    path = tmp_path / "described.tif"
    with rio.open(path, "w", driver="GTiff", height=N_LAT, width=N_LON, count=1, dtype="float32",
                  crs="EPSG:4326", transform=from_origin(WEST, NORTH, 1, 1), nodata=math.nan) as dst:
        dst.write(np.zeros((N_LAT, N_LON), dtype="float32"), 1)
        dst.set_band_description(1, "2023-03-01")
    series = sic_data_from_raster.sic_forecast_series(LON0, LAT0, path)
    assert list(series["Time (UTC)"]) == ["2023-03-01"]