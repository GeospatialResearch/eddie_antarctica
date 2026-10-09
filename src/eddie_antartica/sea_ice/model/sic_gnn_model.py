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
Run the sea ice model on the live inputs and write its forecast: steps 2-3 of the weekly pipeline.

The FReDT ``flood_model/bg_flood_model.py`` of this app. The model's code is the scientists'
``SIC_GNN_DT/Code`` (``util/``, ``models/``) copied into ``model/gnn/``; its checkpoint, mesh
bundle and training stats are data, in ``SIC_MODEL_DIR``. It runs in this process exactly as
``live_forecast.ipynb`` runs it. Publishing the result is ``serve_model``'s job.
"""
import os
import pathlib

import numpy as np
import xarray as xr

from src.eddie_antartica.sea_ice.model import sic_to_nc

#: Files in ``SIC_MODEL_DIR``, named as in the scientists' ``data/``.
CHECKPOINT = "SIC_production_checkpoint.pt"
BUNDLE = "multi_mesh_bundle_K5.npz"
TRAIN_STATS = "train_stats.npz"
#: The inputs file whose lat/lon order is the forecast's node order.
LABEL_FILE = "sea_ice_concentration.nc"


def run_sic_model(inputs_dir: pathlib.Path, model_dir: pathlib.Path) -> np.ndarray:
    """
    Forecast eight weeks from the inputs folder with the scientists' code, as ``live_forecast.ipynb`` does.

    Parameters
    ----------
    inputs_dir : pathlib.Path
        A folder written by ``inputs.main_sea_ice_inputs.main``.
    model_dir : pathlib.Path
        ``SIC_MODEL_DIR``: the checkpoint, the K5 bundle and ``train_stats.npz``.

    Returns
    -------
    numpy.ndarray
        ``(node, week)`` forecast, nodes latitude-major in the inputs files' own lat/lon order.

    Raises
    ------
    FileNotFoundError
        If ``model_dir`` holds no checkpoint.
    """
    if not (model_dir / CHECKPOINT).is_file():
        raise FileNotFoundError(f"No sea ice model checkpoint at {model_dir / CHECKPOINT} (check SIC_MODEL_DIR)")
    # Imported here, not at the top: torch is only needed by the worker's weekly run, and gnn/ is the
    # scientists' code, copied in by hand (see docs/plans/sea-ice-model-transfer.md).
    # pylint: disable=import-outside-toplevel,import-error,no-name-in-module
    import torch
    from src.eddie_antartica.sea_ice.model.gnn.util.config import LOOKBACK_WEEKS
    from src.eddie_antartica.sea_ice.model.gnn.util.data_loader import load_train_stats, prepare_live_window
    from src.eddie_antartica.sea_ice.model.gnn.util.inference import predict_latest
    from src.eddie_antartica.sea_ice.model.gnn.models.multi_mesh_grid_ar import MultiMeshGridARGNN
    # pylint: enable=import-outside-toplevel,import-error,no-name-in-module

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    scaler, train_means, meta = load_train_stats(str(model_dir / TRAIN_STATS))
    checkpoint = torch.load(model_dir / CHECKPOINT, map_location=device, weights_only=False)
    config = checkpoint["config"]
    model = MultiMeshGridARGNN(
        in_channels=config["in_channels"], out_channels=config["out_channels"],
        output_activation=config.get("output_activation", "sigmoid"),
        bundle_path=str(model_dir / BUNDLE), processor=config.get("processor", "interaction"),
    ).to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    x = prepare_live_window(
        str(inputs_dir) + os.sep, scaler, train_means,
        var_order=meta["var_order"], label=meta["label"], climatology_var=meta["climatology_var"],
        input_size=LOOKBACK_WEEKS, time_resolution=meta["time_resolution"],
    )
    return predict_latest(model, x, device)


def main(inputs_dir: pathlib.Path, model_dir: pathlib.Path, out_dir: pathlib.Path) -> pathlib.Path:
    """
    Forecast from the newest inputs and write the dated forecast NetCDF.

    Parameters
    ----------
    inputs_dir : pathlib.Path
        The inputs folder ``inputs.main_sea_ice_inputs.main`` wrote.
    model_dir : pathlib.Path
        ``SIC_MODEL_DIR``.
    out_dir : pathlib.Path
        Where dated forecasts are kept (``FORECAST_NETCDF_DIR``); the chart reads the newest.

    Returns
    -------
    pathlib.Path
        ``sic_forecast_<weeks>w_<week 1>.nc``.

    Raises
    ------
    ValueError
        If the forecast does not have one row per cell of the inputs grid.
    """
    forecast = run_sic_model(inputs_dir, model_dir)
    with xr.open_dataset(inputs_dir / LABEL_FILE) as inputs:
        nodes = inputs.lat.size * inputs.lon.size
        if forecast.ndim != 2 or forecast.shape[0] != nodes:
            raise ValueError(f"Forecast has shape {forecast.shape}, expected ({nodes}, week)")
        return sic_to_nc.forecast_to_nc(forecast, inputs, out_dir)
