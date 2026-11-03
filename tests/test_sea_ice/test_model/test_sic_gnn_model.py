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
Tests for running the sea ice model and labelling what it returns.

The scientists' code in ``sea_ice/model/gnn/`` is copied in by hand and needs torch, so these tests
replace it, and torch, with stand-ins of the same signatures ``live_forecast.ipynb`` uses. The stand-in
model forecasts, for each node, the lat/lon it read from the inputs folder, so a mislabelled node
shows up as a wrong number at a known click.
"""
import ast
import sys
import types
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.eddie_antartica.sea_ice.model import sic_data_from_nc, sic_gnn_model
from tests.test_sea_ice.test_model.test_sic_to_nc import LATITUDES, LONGITUDES

GNN = "src.eddie_antartica.sea_ice.model.gnn"


def load_train_stats(path: str) -> tuple:
    """
    Stand in for ``gnn.util.data_loader.load_train_stats``.

    Parameters
    ----------
    path : str
        Must be the model directory's ``train_stats.npz``.

    Returns
    -------
    tuple
        Scaler, train means and the meta ``live_forecast.ipynb`` reads.
    """
    assert path.endswith("train_stats.npz")
    return "scaler", {}, {"label": "sea_ice_concentration", "var_order": ["sea_ice_concentration"],
                          "climatology_var": "sic_climatology", "time_resolution": "weekly"}


def prepare_live_window(data_dir: str, *_args: Any, input_size: int, **_kwargs: Any) -> np.ndarray:
    """
    Stand in for ``gnn.util.data_loader.prepare_live_window``: one channel encoding each node's lat/lon.

    Parameters
    ----------
    data_dir : str
        The inputs folder, with a trailing separator as the scientists' loader expects.
    *_args : Any
        Scaler and train means, unused.
    input_size : int
        Must be the model's four-week lookback.
    **_kwargs : Any
        The meta-derived keywords, unused.

    Returns
    -------
    numpy.ndarray
        ``(node, 1)``, nodes latitude-major in the file's own order.
    """
    assert data_dir.endswith(("/", "\\")) and input_size == 4
    with xr.open_dataset(data_dir + "sea_ice_concentration.nc") as inputs:
        lat, lon = inputs.lat.values, inputs.lon.values
    return (((lat[:, None] + 44) * 360 + lon[None, :]).ravel() * 1e-4)[:, None]


class MultiMeshGridARGNN:  # pylint: disable=too-few-public-methods
    """Stand in for ``gnn.models.multi_mesh_grid_ar.MultiMeshGridARGNN``."""

    def __init__(self, bundle_path: str, **_kwargs: Any) -> None:
        """
        Check the bundle is the K5 one.

        Parameters
        ----------
        bundle_path : str
            The mesh bundle.
        **_kwargs : Any
            Channels, activation and processor, unused.
        """
        assert bundle_path.endswith("multi_mesh_bundle_K5.npz")
        self.loaded = False

    def to(self, _device: str) -> "MultiMeshGridARGNN":
        """
        Stay put.

        Parameters
        ----------
        _device : str
            Unused.

        Returns
        -------
        MultiMeshGridARGNN
            Itself.
        """
        return self

    def load_state_dict(self, state: dict) -> None:
        """
        Record that the checkpoint's weights were loaded.

        Parameters
        ----------
        state : dict
            The checkpoint's ``model_state_dict``.
        """
        self.loaded = state == {"w": 1}


def predict_latest(model: MultiMeshGridARGNN, x: np.ndarray, _device: str) -> np.ndarray:
    """
    Stand in for ``gnn.util.inference.predict_latest``: the node's code plus 0.1 per week.

    Parameters
    ----------
    model : MultiMeshGridARGNN
        Must have its weights loaded.
    x : numpy.ndarray
        The live window.
    _device : str
        Unused.

    Returns
    -------
    numpy.ndarray
        ``(node, 8)``.
    """
    assert model.loaded
    return x[:, :1] + np.arange(8)[None, :] * 0.1


@pytest.fixture(name="model_dir")
def fixture_model_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Install the stand-in ``gnn`` modules and ``torch``, and lay out ``SIC_MODEL_DIR``.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Pytest's temporary directory.
    monkeypatch : pytest.MonkeyPatch
        Installs the stand-ins for this test only.

    Returns
    -------
    pathlib.Path
        The model directory, holding an (empty) checkpoint.
    """
    modules = {
        "torch": dict(device=str, cuda=types.SimpleNamespace(is_available=lambda: False),
                      load=lambda path, map_location, weights_only: {
                          "config": {"in_channels": 40, "out_channels": 8}, "model_state_dict": {"w": 1}}),
        GNN: {},
        f"{GNN}.util": {},
        f"{GNN}.models": {},
        f"{GNN}.util.config": dict(LOOKBACK_WEEKS=4),
        f"{GNN}.util.data_loader": dict(load_train_stats=load_train_stats, prepare_live_window=prepare_live_window),
        f"{GNN}.util.inference": dict(predict_latest=predict_latest),
        f"{GNN}.models.multi_mesh_grid_ar": dict(MultiMeshGridARGNN=MultiMeshGridARGNN),
    }
    for name, attributes in modules.items():
        monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(**attributes))
    model_dir = tmp_path / "sic_model"
    model_dir.mkdir()
    (model_dir / sic_gnn_model.CHECKPOINT).touch()
    return model_dir


def inputs_dir(tmp_path: Path, land: dict = None) -> Path:
    """
    Write the two inputs files the forecast step reads, laid out as step 1 writes them.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Directory to write into.
    land : dict
        ``{(lat, lon): land fraction}`` for ``land_sea_mask.nc``; every other cell is sea (0).

    Returns
    -------
    pathlib.Path
        ``sic_inputs_2023-12-31/``, four weeks of days, latitude ascending, longitude 0..359.
    """
    days = pd.date_range(end="2023-12-31", periods=28)
    values = np.zeros((days.size, LATITUDES.size, LONGITUDES.size), dtype="float32")
    folder = tmp_path / "sic_inputs_2023-12-31"
    folder.mkdir()
    coords = {"time": days, "lat": LATITUDES, "lon": LONGITUDES}
    xr.Dataset({"sea_ice_concentration": (("time", "lat", "lon"), values)}, coords=coords
               ).to_netcdf(folder / "sea_ice_concentration.nc")
    lsm = xr.DataArray(values.copy(), dims=("time", "lat", "lon"), coords=coords, name="land_sea_mask")
    for (lat, lon), fraction in (land or {}).items():
        lsm.loc[{"lat": lat, "lon": lon}] = fraction
    lsm.to_dataset().to_netcdf(folder / "land_sea_mask.nc")
    return folder


def test_forecast_is_dated_and_charts_the_node_the_model_returned(model_dir: Path, tmp_path: Path) -> None:
    """
    Week 1 follows the inputs' last day, and every click reads back the node the model wrote there.

    179.8 lies between the 179 and 180 nodes, so it charts their blend; the encoding is linear in longitude.
    """
    nc_path = sic_gnn_model.main(inputs_dir(tmp_path), model_dir, tmp_path / "forecasts")

    assert nc_path.name == "sic_forecast_8w_2024-01-07.nc"
    for click, (lon, lat) in (((170.0, -41.0), (170, -41)), ((-150.0, -43.0), (210, -43)),
                              ((0.0, -42.0), (0, -42)), ((179.8, -42.0), (179.8, -42))):
        expected = ((lat + 44) * 360 + lon) * 1e-4 + np.arange(8) * 0.1
        np.testing.assert_allclose(sic_data_from_nc.point_series(*click, nc_path).iloc[:, 1], expected,
                                   rtol=1e-6, err_msg=str(click))



def test_land_cells_keep_the_models_forecast(model_dir: Path, tmp_path: Path) -> None:
    """The scientists' model does not mask land and neither does the forecast file: land cells chart the model's value."""
    land = {(-42, 170): 1.0, (-42, 171): 0.9, (-42, 172): 0.5}
    nc_path = sic_gnn_model.main(inputs_dir(tmp_path, land), model_dir, tmp_path / "forecasts")

    for lon in (170, 171, 172, 173):
        expected = (2 * 360 + lon) * 1e-4 + np.arange(8) * 0.1
        np.testing.assert_allclose(sic_data_from_nc.point_series(float(lon), -42.0, nc_path).iloc[:, 1], expected,
                                   rtol=1e-6, err_msg=str(lon))


def test_a_forecast_being_written_is_never_the_newest(model_dir: Path, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """The chart and WPS pick the newest file by name, so the forecast is written under a temp name and renamed."""
    out_dir, inputs = tmp_path / "forecasts", inputs_dir(tmp_path)
    seen_while_writing = []
    to_netcdf = xr.Dataset.to_netcdf

    def watched_to_netcdf(dataset: xr.Dataset, path: Path, *args: Any, **kwargs: Any) -> None:
        seen_while_writing.append(sic_data_from_nc.latest_forecast(out_dir))
        to_netcdf(dataset, path, *args, **kwargs)
        seen_while_writing.append(sic_data_from_nc.latest_forecast(out_dir))

    monkeypatch.setattr(xr.Dataset, "to_netcdf", watched_to_netcdf)
    nc_path = sic_gnn_model.main(inputs, model_dir, out_dir)

    assert seen_while_writing == [None, None]
    assert [p.name for p in out_dir.iterdir()] == [nc_path.name]

def test_missing_checkpoint_says_where(tmp_path: Path) -> None:
    """A wrong SIC_MODEL_DIR fails before torch is touched, naming the path."""
    with pytest.raises(FileNotFoundError, match="nowhere"):
        sic_gnn_model.run_sic_model(inputs_dir(tmp_path), tmp_path / "nowhere")


def test_the_model_code_imports_itself_by_full_package_path() -> None:
    """
    ``gnn/`` imports itself as ``util.*`` / ``models.*`` in the scientists' notebooks, which only works from their ``Code/``.

    Read with ``ast`` so the check needs neither torch nor the real model.
    """
    gnn_dir = Path(sic_gnn_model.__file__).parent / "gnn"
    bare = [f"{path.relative_to(gnn_dir)}:{node.lineno} {node.module}"
            for path in sorted(gnn_dir.rglob("*.py"))
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in ("util", "models")]
    assert not bare
