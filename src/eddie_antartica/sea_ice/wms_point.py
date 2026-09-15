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

# Bounding box axis order is decided by the CRS, not the version alone: CRS:84 is
# lon,lat by definition even when requested at 1.3.0.
LAT_LON_ORDERED_CRS = {"EPSG:4326", "URN:OGC:DEF:CRS:EPSG::4326"}


def point_from_get_feature_info(params: Mapping[str, str]) -> Tuple[float, float]:
    """
    Find the longitude and latitude of the pixel a GetFeatureInfo request queries.

    The returned point is the **centre** of the queried pixel rather than its corner,
    so that it falls unambiguously inside one raster cell.

    Parameters
    ----------
    params : Mapping[str, str]
        The request's query parameters. Names are matched case-insensitively, as the
        WMS specification requires. ``BBOX``, ``WIDTH`` and ``HEIGHT`` are required, as
        is the queried pixel: ``I``/``J`` at WMS 1.3.0, or ``X``/``Y`` at 1.1.1.

    Returns
    -------
    Tuple[float, float]
        Longitude and latitude of the pixel centre, in degrees (EPSG:4326).

    Raises
    ------
    KeyError
        If a required parameter is absent.
    ValueError
        If a parameter is present but not a number, or the bounding box does not have
        four values.
    """
    query = {key.lower(): value for key, value in params.items()}

    version = query.get("version", "1.3.0")
    crs = (query.get("crs") or query.get("srs") or "EPSG:4326").upper()

    bounds = [float(value) for value in query["bbox"].split(",")]
    if len(bounds) != 4:
        raise ValueError(f"BBOX must have four values, got {len(bounds)}")
    if version.startswith("1.3") and crs in LAT_LON_ORDERED_CRS:
        min_lat, min_lon, max_lat, max_lon = bounds
    else:
        min_lon, min_lat, max_lon, max_lat = bounds

    width = int(query["width"])
    height = int(query["height"])
    # WMS 1.3.0 names the queried pixel I/J; 1.1.1 names it X/Y.
    if "i" in query:
        column, row = int(query["i"]), int(query["j"])
    elif "x" in query:
        column, row = int(query["x"]), int(query["y"])
    else:
        raise KeyError("I/J (WMS 1.3.0) or X/Y (WMS 1.1.1)")

    longitude = min_lon + (column + 0.5) * (max_lon - min_lon) / width
    # J is measured downwards from the north edge, hence the subtraction.
    latitude = max_lat - (row + 0.5) * (max_lat - min_lat) / height
    return longitude, latitude
