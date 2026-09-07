# Copyright © 2021-2026 Geospatial Research Institute Toi Hangarau
# LICENSE: https://github.com/GeospatialResearch/Digital-Twins/blob/master/LICENSE
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



"""" Basic UI test on Terria's Frontend"""
import json

import pytest
import pathlib



CATALOG_PATH = pathlib.Path(__file__).resolve().parent.parent /  "terriajs" / "catalog.json"


def test_catalog_check_home_coords() -> None:
    """terriajs/catalog.json should be pointing towards the Ross Sea bounding box."""
    # flags changes in the home coordinates

    catalog = json.loads(CATALOG_PATH.read_text())

    assert catalog["homeCamera"] == {
        "west": 151.04,
        "south": -78.60,
        "east": 172.98,
        "north": -76.45
    }

def test_sea_ice_layer_opts_into_the_timeseries_chart() -> None:
    """The sea ice layer carries the two properties that make Terria chart it."""
    catalog = json.loads(CATALOG_PATH.read_text())
    members = catalog["catalog"][0]["members"]

    sea_ice = [member for member in members if member.get("layers") == "sic_forecast_8w"]

    assert len(sea_ice) == 1
    assert sea_ice[0]["supportsGetTimeseries"] is True
    assert sea_ice[0]["getFeatureInfoUrl"] == "$BACKEND_URL/sea-ice-timeseries"


