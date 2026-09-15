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
Turn a WMS GetFeatureInfo pixel query into the longitude/latitude it points at.

TerriaJS asks for a time series by sending a GetFeatureInfo-shaped request: a bounding
box, an image size, and the pixel within that image the user clicked. There is no
longitude or latitude in the request, so the backend has to invert the mapping itself.

Two details decide whether the right place is sampled, and getting either wrong samples
somewhere else without erroring:

* ``J`` counts **down** from the top of the image, so latitude is measured from the
  north edge downwards.
* WMS 1.3.0 with ``EPSG:4326`` orders the bounding box **lat,lon** (miny,minx,maxy,maxx).
  WMS 1.1.1, and any version using ``CRS:84``, orders it lon,lat.
"""
from typing import Mapping, Tuple
from rasterio.crs import CRS
from rasterio.warp import transform


LAT_LON_ORDERED_CRS = {
    "EPSG:4326",
    "URN:OGC:DEF:CRS:EPSG::4326",
}


def point_from_get_feature_info(
    params: Mapping[str, str],
) -> Tuple[float, float]:
    """
    Find the longitude and latitude of the pixel a GetFeatureInfo request
    queries.

    The clicked pixel is first calculated in the WMS request CRS. It is
    then transformed to EPSG:4326 so callers always receive longitude and
    latitude in degrees.

    Parameters
    ----------
    params : Mapping[str, str]
        GetFeatureInfo query parameters.

    Returns
    -------
    Tuple[float, float]
        Longitude and latitude in degrees, in EPSG:4326.
    """
    query = {key.lower(): value for key, value in params.items()}

    version = query.get("version", "1.3.0")
    crs = (
        query.get("crs")
        or query.get("srs")
        or "EPSG:4326"
    ).upper()

    bounds = [
        float(value)
        for value in query["bbox"].split(",")
    ]

    if len(bounds) != 4:
        raise ValueError(
            f"BBOX must have four values, got {len(bounds)}"
        )

    # WMS 1.3.0 uses latitude/longitude axis order for EPSG:4326.
    if version.startswith("1.3") and crs in LAT_LON_ORDERED_CRS:
        min_y, min_x, max_y, max_x = bounds
    else:
        min_x, min_y, max_x, max_y = bounds

    width = int(query["width"])
    height = int(query["height"])

    if width <= 0 or height <= 0:
        raise ValueError(
            "WIDTH and HEIGHT must be greater than zero"
        )

    # WMS 1.3.0 uses I/J; WMS 1.1.1 uses X/Y.
    if "i" in query:
        column = int(query["i"])
        row = int(query["j"])
    elif "x" in query:
        column = int(query["x"])
        row = int(query["y"])
    else:
        raise KeyError(
            "I/J (WMS 1.3.0) or X/Y (WMS 1.1.1)"
        )

    if not 0 <= column < width:
        raise ValueError(
            f"Pixel column {column} is outside image width {width}"
        )

    if not 0 <= row < height:
        raise ValueError(
            f"Pixel row {row} is outside image height {height}"
        )

    # Calculate the selected pixel's centre in the request CRS.
    x_coordinate = (
        min_x
        + (column + 0.5) * (max_x - min_x) / width
    )

    # Rows count downwards from the top of the image.
    y_coordinate = (
        max_y
        - (row + 0.5) * (max_y - min_y) / height
    )

    request_crs = CRS.from_user_input(crs)
    output_crs = CRS.from_epsg(4326)

    longitudes, latitudes = transform(
        request_crs,
        output_crs,
        [x_coordinate],
        [y_coordinate],
    )

    longitude = longitudes[0]
    latitude = latitudes[0]

    if not -180.0 <= longitude <= 180.0:
        raise ValueError(
            f"Transformed longitude is outside its valid range: "
            f"{longitude}"
        )

    if not -90.0 <= latitude <= 90.0:
        raise ValueError(
            f"Transformed latitude is outside its valid range: "
            f"{latitude}"
        )

    return longitude, latitude