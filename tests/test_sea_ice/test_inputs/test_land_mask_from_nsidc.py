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
"""Tests for looking up NSIDC-0780's land and ice shelves, which the smoothed layer and its chart cut out."""
from pathlib import Path

import numpy as np
from pyproj import Transformer
import pytest
from rasterio.enums import Resampling
import xarray as xr

from src.eddie_antartica.sea_ice.inputs import land_mask_from_nsidc

#: Made-up class values: the module must go by the names, whatever numbers a file gives them.
CLASSES = {"ross_sea": 7, "weddell_sea": 8, "land": 40, "fresh_free_water": 42, "ice_on_land": 43,
           "floating_ice_shelf": 44, "ocean_disconnected": 45, "off_earth": 50}

#: The EASE2 South projection the test file is on.
EASE2_SOUTH = "EPSG:6932"

#: Half width of the test grid, in metres: short of 41 S along the axes.
EXTENT = 5_000_000


def nsidc_mask(path: Path, classes: dict = None) -> Path:
    """
    Write a small NSIDC-0780-shaped file: ice sheet to 1500 km from the pole, ice shelf to 1700 km, then sea.

    Beyond 4500 km from the pole is land, so a point just inside the grid's edge is land and one past it is not.

    Parameters
    ----------
    path : Path
        Where to write the file.
    classes : dict
        ``{flag meaning: flag value}``; ``CLASSES`` by default.

    Returns
    -------
    Path
        The written file.
    """
    classes = CLASSES if classes is None else classes
    x = np.arange(-EXTENT, EXTENT + 1, 100_000, dtype="float64")
    y = x[::-1]
    distance = np.hypot(*np.meshgrid(x, y))
    surface = np.select([distance < 1_500_000, distance < 1_700_000, distance > 4_500_000],
                        [CLASSES["ice_on_land"], CLASSES["floating_ice_shelf"], CLASSES["land"]], CLASSES["ross_sea"])
    regions = xr.DataArray(surface.astype("uint8"), dims=("y", "x"), coords={"x": x, "y": y},
                           name=land_mask_from_nsidc.MASK_VARIABLE,
                           attrs={"flag_values": np.array(list(classes.values()), dtype="uint8"),
                                  "flag_meanings": " ".join(classes)})
    regions.rio.write_crs(EASE2_SOUTH).to_dataset().to_netcdf(path)
    return path


def test_not_sea_is_a_georeferenced_grid_that_reprojects_onto_a_lat_lon_grid(tmp_path: Path) -> None:
    """Every not-sea class reads as 1 and the sea as 0, by name whatever numbers the file uses."""
    target = xr.DataArray(np.zeros((3, 2)), dims=("y", "x"),
                          coords={"y": [-89.6, -75.6, -61.6], "x": [0.0, 120.0]}).rio.write_crs("EPSG:4326")

    land = land_mask_from_nsidc.not_sea(nsidc_mask(tmp_path / "nsidc.nc"))

    assert land.rio.crs == EASE2_SOUTH
    assert set(np.unique(land)) == {0, 1}
    ice_sheet, ice_shelf, sea = land.rio.reproject_match(target, resampling=Resampling.nearest).values.tolist()
    assert (ice_sheet, ice_shelf, sea) == ([1, 1], [1, 1], [0, 0])


def test_a_point_is_not_sea_on_land_and_sea_off_the_mask_grid(tmp_path: Path) -> None:
    """A click reads the cell it is in; past the edge of the mask's grid it is sea, not the nearest edge cell."""
    nsidc_path = nsidc_mask(tmp_path / "nsidc.nc")
    to_grid = Transformer.from_crs("EPSG:4326", EASE2_SOUTH, always_xy=True)
    inside, outside = (0.0, -45.0), (0.0, -41.0)
    assert max(map(abs, to_grid.transform(*inside))) < EXTENT
    assert max(map(abs, to_grid.transform(*outside))) > EXTENT + 50_000

    points = [(0.0, -89.0), (-60.0, -60.0), (179.9, -60.0), inside, outside]

    assert [land_mask_from_nsidc.is_not_sea(nsidc_path, *point) for point in points] == [True, False, False, True, False]


def test_a_file_without_a_not_sea_class_is_refused(tmp_path: Path) -> None:
    """A file naming its classes differently stops the run instead of drawing ice shelves as sea."""
    classes = {name: value for name, value in CLASSES.items() if name != "floating_ice_shelf"}

    with pytest.raises(KeyError, match="floating_ice_shelf"):
        land_mask_from_nsidc.not_sea(nsidc_mask(tmp_path / "nsidc.nc", classes))
