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
Serve a sea ice concentration forecast point series out of the NetCDF written for issue #35.

The sibling ``sic_data_from_raster`` reads the same forecast out of the multi-band GeoTIFF
that GeoServer publishes. Both exist on purpose: ``serve_static_files`` in ``lib/eddie``
matches ``.tif`` and skips ``.nc``, so the WMS layer cannot move, while the NetCDF is the
model's own output rather than a raster export of it.

Both return the same two columns, so whichever a catalog entry points at, TerriaJS charts
an identical CSV. That is what makes the two routes comparable rather than merely similar.

The CRS is read from the file's ``grid_mapping``, never assumed -- indexing the wrong cell
returns a plausible number instead of an error. In practice ``sic_forecast_to_nc`` always
writes EPSG:4326, so the transform below is an identity; it is there so a regridded file
does not silently sample the wrong place.
"""
import pathlib
from typing import Union
import pandas as pd
from src.eddie_antartica.sampling.xarray_cell import sample_cell

VARIABLE = "sic"
#: Matches the GeoTIFF's per-band TIME tags, so the two routes' CSVs agree byte for byte.
TIME_COLUMN = "Time (UTC)"
VALUE_COLUMN = "Sea ice concentration (fraction)"
TIME_DIM = "time"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def point_series(longitude: float,
                 latitude: float,
                 source: Union[str, pathlib.Path]) -> pd.DataFrame:
    """
    Extract the forecast time series for the grid cell containing a point.

    Only the one cell is read off disk, so file size costs little.

    Parameters
    ----------
    longitude : float
        Longitude of the clicked point in degrees, in either the -180..180 or 0..360
        convention.
    latitude : float
        Latitude of the clicked point in degrees (EPSG:4326).
    source : Union[str, pathlib.Path]
        Path to the forecast NetCDF. The caller owns its location: the forecast holds
        unpublished data and is not committed to this repository.

    Returns
    -------
    pandas.DataFrame
        Columns ``Time (UTC)`` and ``Sea ice concentration (fraction)``, one row per
        forecast step. Zero rows if the point falls outside the grid.

    Raises
    ------
    OSError
        If the file is missing or unreadable.
    KeyError
        If the file does not hold the forecast variable, or states no CRS.
    """
    cell = sample_cell(source, VARIABLE, longitude, latitude)
    if cell is None:
        return pd.DataFrame(columns=[TIME_COLUMN, VALUE_COLUMN])

    frame = cell.transpose(TIME_DIM).to_pandas().to_frame(name=VALUE_COLUMN)
    frame.index = pd.to_datetime(frame.index).strftime(TIME_FORMAT)
    frame.index.name = TIME_COLUMN

    return frame
