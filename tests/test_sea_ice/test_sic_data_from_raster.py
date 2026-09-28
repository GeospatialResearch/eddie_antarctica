# tests/test_sea_ice/test_sic_data_from_raster.py
# -*- coding: utf-8 -*-
# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antartica/blob/master/LICENSE

"""Tests for reading sea ice concentration forecast time series out of a GeoTIFF."""

import math
import numpy as np
import rasterio as rio
import tempfile
import unittest
from pathlib import Path
from rasterio.transform import from_origin
from src.eddie_antartica.sea_ice import sic_data_from_raster
from typing import List

N_BANDS, N_LAT, N_LON = 3, 4, 8
WEST, NORTH = -180.0, -40.0
LON0, LAT0 = WEST + 0.5, NORTH - 0.5
TIMES = [
    "2023-01-01T00:00:00Z",
    "2023-01-08T00:00:00Z",
    "2023-01-15T00:00:00Z",
]
VALUES = "Sea ice concentration (fraction)"


def _write_fixture(
        path: Path,
        values: np.ndarray,
        times: List[str],
        nodata: float = math.nan,
) -> Path:
    """Write a north-up EPSG:4326 GeoTIFF with one TIME-tagged band per timestep."""
    with rio.open(
            path,
            "w",
            driver="GTiff",
            height=values.shape[1],
            width=values.shape[2],
            count=values.shape[0],
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(WEST, NORTH, 1, 1),
            nodata=nodata,
    ) as dst:
        for band, timestamp in enumerate(times, start=1):
            dst.write(values[band - 1].astype("float32"), band)
            dst.update_tags(band, TIME=timestamp)

    return path


def _forecast_tif(tmp_path: Path) -> Path:
    """Build a raster whose every cell value encodes its own position."""
    values = np.empty((N_BANDS, N_LAT, N_LON), dtype="float32")

    for band in range(N_BANDS):
        for row in range(N_LAT):
            for col in range(N_LON):
                values[band, row, col] = (
                        (band + 1) * 100 + row * 10 + col
                )

    return _write_fixture(
        tmp_path / "forecast.tif",
        values,
        TIMES,
    )


class TestSICDataFromRaster(unittest.TestCase):
    """Tests for sea ice concentration time-series extraction."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tmp_path = Path(self.temp_dir.name)

    def test_samples_the_clicked_cell_across_every_band(self) -> None:
        """The correct cell is read from every raster band."""
        tif = _forecast_tif(self.tmp_path)

        series = sic_data_from_raster.sic_forecast_series(
            LON0,
            LAT0,
            tif,
        )

        self.assertEqual(
            list(series.columns),
            ["Time (UTC)", VALUES],
        )
        self.assertEqual(
            list(series["Time (UTC)"]),
            TIMES,
        )
        self.assertEqual(
            list(series[VALUES]),
            [100.0, 200.0, 300.0],
        )

        corner = sic_data_from_raster.sic_forecast_series(
            WEST + N_LON - 0.5,
            NORTH - N_LAT + 0.5,
            tif,
        )
        last = (N_LAT - 1) * 10 + (N_LON - 1)

        self.assertEqual(
            list(corner[VALUES]),
            [
                100.0 + last,
                200.0 + last,
                300.0 + last,
            ],
        )

        interior = sic_data_from_raster.sic_forecast_series(
            -177.9,
            -41.9,
            tif,
        )
        self.assertEqual(
            interior[VALUES].iloc[0],
            112.0,
        )

        western_edge = sic_data_from_raster.sic_forecast_series(
            WEST,
            LAT0,
            tif,
        )
        self.assertEqual(
            western_edge[VALUES].iloc[0],
            100.0,
        )

    def test_longitude_beyond_180_is_wrapped(self) -> None:
        """A 0-360 longitude is wrapped into -180..180 before sampling."""
        tif = _forecast_tif(self.tmp_path)

        wrapped = sic_data_from_raster.sic_forecast_series(
            183.0,
            LAT0,
            tif,
        )
        unwrapped = sic_data_from_raster.sic_forecast_series(
            -177.0,
            LAT0,
            tif,
        )

        self.assertEqual(
            list(wrapped[VALUES]),
            list(unwrapped[VALUES]),
        )

    def test_point_outside_extent_returns_empty_frame(self) -> None:
        """A click outside the raster returns an empty frame with headers."""
        tif = _forecast_tif(self.tmp_path)

        series = sic_data_from_raster.sic_forecast_series(
            0.0,
            0.0,
            tif,
        )

        self.assertTrue(series.empty)
        self.assertEqual(
            list(series.columns),
            ["Time (UTC)", VALUES],
        )

    def test_explicit_nodata_becomes_nan(self) -> None:
        """A sentinel nodata value becomes NaN."""
        values = np.full(
            (1, N_LAT, N_LON),
            -9999.0,
            dtype="float32",
        )
        path = _write_fixture(
            self.tmp_path / "nodata.tif",
            values,
            TIMES[:1],
            nodata=-9999.0,
        )

        series = sic_data_from_raster.sic_forecast_series(
            LON0,
            LAT0,
            path,
        )

        self.assertTrue(series[VALUES].isna().all())

    def test_band_without_time_tag_falls_back_to_description(self) -> None:
        """A band with no TIME tag uses its description instead."""
        path = self.tmp_path / "described.tif"

        with rio.open(
                path,
                "w",
                driver="GTiff",
                height=N_LAT,
                width=N_LON,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(WEST, NORTH, 1, 1),
                nodata=math.nan,
        ) as dst:
            dst.write(
                np.zeros((N_LAT, N_LON), dtype="float32"),
                1,
            )
            dst.set_band_description(
                1,
                "2023-03-01",
            )

        series = sic_data_from_raster.sic_forecast_series(
            LON0,
            LAT0,
            path,
        )

        self.assertEqual(
            list(series["Time (UTC)"]),
            ["2023-03-01"],
        )


if __name__ == "__main__":
    unittest.main()
