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
import re

import pytest
import pathlib



CATALOG_PATH = pathlib.Path(__file__).resolve().parent.parent /  "terriajs" / "catalog.json"
CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "terriajs" / "client_config.json"


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
    assert sea_ice[0]["getFeatureInfoUrl"] == "$BACKEND_URL/sea-ice-timeseries-netcdf"


def test_client_config_points_terrain_at_self_hosted_backend() -> None:
    """client_config.json should serve terrain from the backend, not fall back to Cesium Ion (issue #376)."""
    config = json.loads(CONFIG_PATH.read_text())
    assert config["parameters"]["cesiumTerrainUrl"] == "$BACKEND_URL/terrain"


def test_sea_ice_forecast_process_is_listed() -> None:
    """Terria lists the sea_ice_forecast WPS process, which adds the week's layer itself."""
    catalog = json.loads(CATALOG_PATH.read_text())
    group = [group for group in catalog["catalog"] if group["name"] == "Sea ice forecast"]

    assert group[0]["members"] == [{
        "type": "wps",
        "name": "Sea ice concentration forecast",
        "description": group[0]["members"][0]["description"],
        "url": "$BACKEND_URL/wps",
        "identifier": "sea_ice_forecast",
    }]


def test_every_catalog_style_has_an_sld() -> None:
    """GeoServer names each style after its .sld file (eddie add_style), so a catalog style with no such file renders nothing."""
    styles = set(re.findall(r'\\?"styles\\?": *\\?"([^"\\]+)', CATALOG_PATH.read_text()))
    sld_names = {sld.stem for sld in (CATALOG_PATH.parent.parent / "src" / "static" / "geo").glob("*.sld")}

    assert styles - sld_names == set()


def test_every_backend_link_in_the_catalog_is_a_served_route() -> None:
    """A catalog item pointing at a retired route charts nothing, with no error; read the routes from the source."""
    src = CATALOG_PATH.parent.parent / "src" / "eddie_antartica"
    sources = (src / "app.py").read_text() + (src / "blueprint.py").read_text()
    routes = set(re.findall(r"""\.route\(['"]([^'"]+)['"]""", sources))
    routes.add(re.search(r'TIMESERIES_ROUTE = "([^"]+)"', (src / "sea_ice" / "sea_ice_forecast_layer.py").read_text())[1])
    patterns = [re.compile(re.sub(r"<(?:path:)?\w+>", lambda m: ".+" if "path:" in m[0] else "[^/]+", route) + "$")
                for route in routes]
    links = set(re.findall(r"\$BACKEND_URL(/[^\"\\?]*)", CATALOG_PATH.read_text()))

    assert {link for link in links if not any(p.match(link) for p in patterns)} == set()
