# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/eddie_antartica/blob/master/LICENSE

"""Tests for reading sea ice concentration forecast time series out of a GeoTIFF."""
import json
import unittest
from pathlib import Path

from src.eddie_antartica.sea_ice import sic_data_from_raster

DATA_DIR = Path(__file__).parent / "data"
TIME = "Time (UTC)"
VALUES = "Sea ice concentration (fraction)"


class TestSICDataFromRaster(unittest.TestCase):
    """Tests for sea ice concentration time-series extraction."""

    def setUp(self) -> None:
        self.times = (DATA_DIR / "forecast_times.txt").read_text().split()
        features = json.loads((DATA_DIR / "clicks.geojson").read_text())["features"]
        self.clicks = {
            feature["properties"]["name"]: (*feature["geometry"]["coordinates"], feature["properties"]["expected"])
            for feature in features
        }

    def _series(self, name, tif="forecast.tif"):
        """Sample a named click point from a data-directory GeoTIFF; return the series and its expected values."""
        longitude, latitude, expected = self.clicks[name]
        return sic_data_from_raster.sic_forecast_series(longitude, latitude, DATA_DIR / tif), expected

    def test_samples_the_clicked_cell_across_every_band(self) -> None:
        """The correct cell is read from every raster band."""
        for name in ("first_cell", "last_cell", "interior", "western_edge"):
            with self.subTest(name):
                series, expected = self._series(name)
                self.assertEqual(list(series.columns), [TIME, VALUES])
                self.assertEqual(list(series[TIME]), self.times)
                self.assertEqual(list(series[VALUES]), expected)

    def test_longitude_beyond_180_is_wrapped(self) -> None:
        """A 0-360 longitude is wrapped into -180..180 before sampling."""
        series, expected = self._series("wrapped")
        self.assertEqual(list(series[VALUES]), expected)

    def test_point_outside_extent_returns_empty_frame(self) -> None:
        """A click outside the raster returns an empty frame with headers."""
        series, _ = self._series("outside")
        self.assertTrue(series.empty)
        self.assertEqual(list(series.columns), [TIME, VALUES])

    def test_explicit_nodata_becomes_nan(self) -> None:
        """A sentinel nodata value becomes NaN."""
        series, _ = self._series("first_cell", "nodata.tif")
        self.assertTrue(series[VALUES].isna().all())

    def test_band_without_time_tag_falls_back_to_description(self) -> None:
        """A band with no TIME tag uses its description instead."""
        series, _ = self._series("first_cell", "described.tif")
        self.assertEqual(list(series[TIME]), (DATA_DIR / "described_time.txt").read_text().split())


if __name__ == "__main__":
    unittest.main()