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


"""Tests for the /sea-ice-timeseries endpoint that feeds the TerriaJS chart."""
import pandas as pd
import pytest

# The Flask app imports the eddie framework, which is only installed once the lib/eddie
# submodule is initialised. Skip rather than fail where it is not.
pytest.importorskip("eddie", reason="lib/eddie submodule is not installed")

from src.eddie_antartica import app as app_module  # noqa: E402  pylint: disable=wrong-import-position

QUERY = ("/sea-ice-timeseries?SERVICE=WMS&REQUEST=GetFeatureInfo&VERSION=1.3.0"
         "&CRS=EPSG:4326&BBOX=-90,-180,-40,180&WIDTH=360&HEIGHT=50&I=0&J=0")


def test_serves_the_clicked_point_as_two_column_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pixel becomes a lon/lat, and the frame becomes the CSV Terria charts."""
    sampled = {}

    def _record(longitude: float, latitude: float, raster_path: object) -> pd.DataFrame:
        sampled["point"] = (longitude, latitude)
        sampled["raster"] = raster_path
        return pd.DataFrame({"Time (UTC)": ["2023-01-01T00:00:00Z", "2023-01-08T00:00:00Z"],
                             "Sea ice concentration (fraction)": [0.5, 0.25]})



    monkeypatch.setattr(app_module, "sic_forecast_series", _record)
    response = app_module.app.test_client().get(QUERY)

    assert sampled["point"] == (-179.5, -40.5)
    assert sampled["raster"] == app_module.FORECAST_RASTER
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert response.get_data(as_text=True).splitlines() == [
        "Time (UTC),Sea ice concentration (fraction)",
        "2023-01-01T00:00:00Z,0.5",
        "2023-01-08T00:00:00Z,0.25",
    ]


def test_malformed_request_is_a_bad_request() -> None:
    """A query with no pixel index is a 400, not a 500."""
    response = app_module.app.test_client().get(
        "/sea-ice-timeseries?BBOX=-90,-180,-40,180&WIDTH=360&HEIGHT=50")
    assert response.status_code == 400