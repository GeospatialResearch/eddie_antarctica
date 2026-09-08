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


"""Tests for turning a WMS GetFeatureInfo pixel query into a longitude/latitude point."""
import pytest

from src.eddie_antartica.sea_ice import wms_point

# A whole-world-south request matching the forecast grid: 1-degree pixels, so every
# expected value is hand-computable as "edge plus half a pixel".
SIZE = {"WIDTH": "360", "HEIGHT": "50"}
BBOX_LAT_LON = "-90,-180,-40,180"  # WMS 1.3.0 + EPSG:4326 orders miny,minx,maxy,maxx.
BBOX_LON_LAT = "-180,-90,180,-40"  # WMS 1.1.1, and CRS:84, order minx,miny,maxx,maxy.


def test_pixel_maps_to_its_own_centre() -> None:
    """I/J address a pixel whose centre is returned, with J counting down from the top."""
    query = {"VERSION": "1.3.0", "CRS": "EPSG:4326", "BBOX": BBOX_LAT_LON, **SIZE}

    assert wms_point.point_from_get_feature_info({**query, "I": "0", "J": "0"}) == (-179.5, -40.5)
    # The last pixel is the south-east cell centre; J increasing moves south.
    assert wms_point.point_from_get_feature_info({**query, "I": "359", "J": "49"}) == (179.5, -89.5)
    # WMS parameter names are case-insensitive.
    lowered = {key.lower(): value for key, value in {**query, "I": "0", "J": "0"}.items()}
    assert wms_point.point_from_get_feature_info(lowered) == (-179.5, -40.5)


def test_bbox_axis_order_follows_the_crs_not_the_version() -> None:
    """EPSG:4326 at 1.3.0 is lat,lon; 1.1.1 and CRS:84 are lon,lat. All name one point."""
    at_130 = {"VERSION": "1.3.0", "CRS": "EPSG:4326", "BBOX": BBOX_LAT_LON, "I": "100", "J": "20", **SIZE}
    at_111 = {"VERSION": "1.1.1", "SRS": "EPSG:4326", "BBOX": BBOX_LON_LAT, "X": "100", "Y": "20", **SIZE}
    crs84 = {"VERSION": "1.3.0", "CRS": "CRS:84", "BBOX": BBOX_LON_LAT, "I": "100", "J": "20", **SIZE}

    expected = (-79.5, -60.5)
    assert wms_point.point_from_get_feature_info(at_130) == expected
    assert wms_point.point_from_get_feature_info(at_111) == expected
    assert wms_point.point_from_get_feature_info(crs84) == expected


def test_malformed_query_is_rejected_rather_than_defaulted() -> None:
    """Missing or non-numeric parameters raise instead of silently sampling somewhere else."""
    query = {"VERSION": "1.3.0", "CRS": "EPSG:4326", "BBOX": BBOX_LAT_LON, "I": "0", "J": "0", **SIZE}

    with pytest.raises(KeyError):
        wms_point.point_from_get_feature_info({key: value for key, value in query.items() if key != "I"})
    with pytest.raises(ValueError):
        wms_point.point_from_get_feature_info({**query, "I": "not-a-number"})
    with pytest.raises(ValueError):
        wms_point.point_from_get_feature_info({**query, "BBOX": "-90,-180"})