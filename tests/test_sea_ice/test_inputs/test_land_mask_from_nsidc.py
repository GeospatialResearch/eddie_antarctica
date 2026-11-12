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
"""Tests for converting NSIDC-0780's surface classes, once, into the land fraction the smoothed layers are cut with."""
from pathlib import Path

import numpy as np
from pyproj import Transformer
import pytest
import rasterio as rio
import xarray as xr

from src.eddie_antartica.sea_ice.inputs import land_mask_from_nsidc
from src.eddie_antartica.sea_ice.model import sic_to_nc
from tests.test_sea_ice.test_model.test_sic_to_nc import encoded_forecast, model_inputs

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


def test_ice_sheets_and_shelves_are_land_and_sea_regions_are_sea(tmp_path: Path) -> None:
    """The mask lands on the display grid over the model's rows, 1 on every not-sea class and 0 on sea."""
    out = land_mask_from_nsidc.main(nsidc_mask(tmp_path / "nsidc.nc"), tmp_path / "out" / "sic_land_mask.nc")

    with xr.open_dataset(out, decode_coords="all") as dataset:
        land = dataset["land_sea_mask"].load()
        assert dataset.rio.crs.to_epsg() == 4326
    assert land.shape == (1000, 7200)
    assert (float(land.lat[0]), float(land.lat[-1])) == pytest.approx((-40.525, -90.475))
    assert (float(land.lon[0]), float(land.lon[-1])) == pytest.approx((-179.975, 179.975))
    shelf_lat = -90 + np.degrees(2 * np.arcsin(1_600_000 / (2 * 6_371_007)))
    for lon, lat, expected in ((0, -89.0, 1), (120, shelf_lat, 1), (-60, -60.0, 0), (179.9, -60.0, 0)):
        assert int(land.sel(lon=lon, lat=lat, method="nearest")) == expected, (lon, lat)


def test_outside_the_mask_grid_is_sea(tmp_path: Path) -> None:
    """Points past the edge of the mask's grid are sea, not the nearest edge cell."""
    out = land_mask_from_nsidc.main(nsidc_mask(tmp_path / "nsidc.nc"), tmp_path / "sic_land_mask.nc")

    to_grid = Transformer.from_crs("EPSG:4326", EASE2_SOUTH, always_xy=True)
    inside, outside = (-45.0, 0.0), (-41.0, 0.0)
    assert max(map(abs, to_grid.transform(inside[1], inside[0]))) < EXTENT
    assert max(map(abs, to_grid.transform(outside[1], outside[0]))) > EXTENT + 50_000
    with xr.open_dataset(out) as dataset:
        land = dataset["land_sea_mask"]
        assert int(land.sel(lat=inside[0], lon=inside[1], method="nearest")) == 1
        assert int(land.sel(lat=outside[0], lon=outside[1], method="nearest")) == 0


def test_a_file_without_a_not_sea_class_is_refused(tmp_path: Path) -> None:
    """A file naming its classes differently stops the conversion instead of drawing ice shelves as sea."""
    classes = {name: value for name, value in CLASSES.items() if name != "floating_ice_shelf"}

    with pytest.raises(ValueError, match="floating_ice_shelf"):
        land_mask_from_nsidc.main(nsidc_mask(tmp_path / "nsidc.nc", classes), tmp_path / "sic_land_mask.nc")


def test_the_mask_cuts_the_smoothed_layer(tmp_path: Path) -> None:
    """The written mask is what ``display_gtiff`` reads: its land is blank, the sea past its grid is drawn."""
    out = land_mask_from_nsidc.main(nsidc_mask(tmp_path / "nsidc.nc"), tmp_path / "sic_land_mask.nc")
    nc_path = sic_to_nc.forecast_to_nc(np.full_like(encoded_forecast(), 0.5), model_inputs(), tmp_path)

    with rio.open(sic_to_nc.display_gtiff(nc_path, tmp_path / "display.tif", 0, out)) as raster:
        land, sea = (value[0] for value in raster.sample([(45.0, -42.0), (0.0, -42.0)]))
    assert np.isnan(land)
    assert sea == pytest.approx(0.5)
