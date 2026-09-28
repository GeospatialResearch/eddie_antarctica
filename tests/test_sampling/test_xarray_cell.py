# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antartica/blob/master/LICENSE

import unittest
from pathlib import Path

import numpy as np
from rasterio.crs import CRS
from rasterio.warp import transform as warp_transform

from src.eddie_antartica.sampling.xarray_cell import (
    CLICK_CRS,
    sample_cell,
)

VARIABLE = "value"


def _click_for(
    crs: CRS,
    x: float,
    y: float,
):
    """Convert a native CRS coordinate into an EPSG:4326 click."""
    longitudes, latitudes = warp_transform(
        crs,
        CLICK_CRS,
        [x],
        [y],
    )
    return longitudes[0], latitudes[0]


class SampleCellTest(unittest.TestCase):

    def setUp(self) -> None:
        data_dir = Path("tests/test_sampling/data")

        self.projected_path = data_dir / "projected.nc"
        self.geographic_path = data_dir / "geographic.nc"
        self.wrap_path = data_dir / "wrap.nc"
        self.outside_path = data_dir / "outside.nc"

    def test_samples_the_clicked_cell_on_a_projected_grid(self):
        """A click reprojects onto a projected grid and returns the correct cell."""

        expected = [15.0, 31.0]

        longitude, latitude = _click_for(
            CRS.from_epsg(3031),
            100000.0,
            -100000.0,
        )

        cell = sample_cell(
            self.projected_path,
            VARIABLE,
            longitude,
            latitude,
        )

        self.assertIsNotNone(cell)
        self.assertEqual(
            list(cell.values),
            expected,
        )

    def test_samples_the_clicked_cell_on_a_geographic_grid(self):
        """A click on a lon/lat grid samples the correct cell."""

        expected = [10.0, 26.0]

        cell = sample_cell(
            self.geographic_path,
            VARIABLE,
            0.0,
            -60.0,
            x_dim="lon",
            y_dim="lat",
        )

        self.assertIsNotNone(cell)
        self.assertEqual(
            list(cell.values),
            expected,
        )

    def test_longitude_beyond_180_is_wrapped(self):
        """A 0-360 longitude click is wrapped before sampling."""

        wrapped = sample_cell(
            self.wrap_path,
            VARIABLE,
            270.0,
            -60.0,
            x_dim="lon",
            y_dim="lat",
        )

        unwrapped = sample_cell(
            self.wrap_path,
            VARIABLE,
            -90.0,
            -60.0,
            x_dim="lon",
            y_dim="lat",
        )

        self.assertIsNotNone(wrapped)
        self.assertIsNotNone(unwrapped)

        self.assertEqual(
            list(wrapped.values),
            list(unwrapped.values),
        )

    def test_point_outside_grid_returns_none(self):
        """A click outside grid tolerance returns None."""

        longitude, latitude = _click_for(
            CRS.from_epsg(3031),
            1000000.0,
            1000000.0,
        )

        cell = sample_cell(
            self.outside_path,
            VARIABLE,
            longitude,
            latitude,
        )

        self.assertIsNone(cell)


if __name__ == "__main__":
    unittest.main()