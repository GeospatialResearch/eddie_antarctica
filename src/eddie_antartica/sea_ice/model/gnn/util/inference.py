"""
inference.py — metric-free inference core for the SIC digital twin.

The deployment counterpart of the source project's `util/evaluate.py`: it keeps
ONLY the forward pass and a slim SIC forecast plot — no MAE/RMSE, no ice-mask, no
metric .npz. `run_inference` is copied verbatim from `evaluate.run_inference` so
test-split predictions are bit-identical to the source project's; `predict_latest`
serves the operational single-window ("latest 4 weeks -> next 8 weeks") path.

Target is unscaled (SIC in [0, 1], sigmoid head), so model outputs are already SIC.
"""

import numpy as np
import torch
import matplotlib.pyplot as plt   # NB: no matplotlib.use("Agg") — keep notebook inline display


def run_inference(model, test_loader, device, out_channels):
    """Return (preds, targets, persistence, climatology), each
    (N_samples, N_nodes, out_channels). The baselines ride along on each
    batch (Data.pers / Data.clim), so they stay aligned with preds/targets
    and don't need a separate materialised array.

    Copied verbatim from util.evaluate.run_inference (evaluate.py:41-64) so the
    predictions match the source project exactly. Baselines are returned for
    convenience (e.g. plotting persistence); no metrics are computed here."""
    model.eval()
    all_preds, all_targets, all_pers, all_clim = [], [], [], []
    with torch.no_grad():
        for batch in test_loader:
            B = batch.num_graphs
            # Read baselines before moving to GPU (no need to round-trip them).
            all_pers.append(batch.pers.numpy().reshape(B, -1, out_channels))
            all_clim.append(batch.clim.numpy().reshape(B, -1, out_channels))
            batch = batch.to(device, non_blocking=True)
            out = model(batch.x, batch.edge_index).cpu().numpy()
            # PyG flattens B graphs along the node axis; split back per graph.
            all_preds.append(out.reshape(B, -1, out_channels))
            all_targets.append(batch.y.cpu().numpy().reshape(B, -1, out_channels))
    return (
        np.concatenate(all_preds,   axis=0),
        np.concatenate(all_targets, axis=0),
        np.concatenate(all_pers,    axis=0),
        np.concatenate(all_clim,    axis=0),
    )


def predict_latest(model, x, device, edge_index=None):
    """Single-window forward for operational forecasting.

    x           : (N_nodes, in_channels) numpy array or tensor (one graph, B=1),
                  as produced by util.data_loader.prepare_live_window.
    returns     : (N_nodes, out_channels) numpy array — the SIC forecast per node
                  for each of the `out_channels` forecast weeks.

    The multi-mesh model carries its own edges and ignores `edge_index`, so an
    empty one is passed when none is given."""
    model.eval()
    if not torch.is_tensor(x):
        x = torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32))
    x = x.to(device)
    if edge_index is None:
        edge_index = torch.empty((2, 0), dtype=torch.long, device=device)
    with torch.no_grad():
        out = model(x, edge_index)
    return out.cpu().numpy()


def plot_forecast(field, n_lat, n_lon, *, titles=None, suptitle=None, path=None,
                  cmap="Blues_r", vmin=0.0, vmax=1.0, cbar_label="SIC"):
    """Render a 1 x H row of SIC maps for a per-node forecast.

    field   : (N_nodes, H) — SIC per node for each of H forecast weeks.
    Adapted from the SIC branch of util.evaluate.save_forecast_figure (sequential
    Blues_r on [0, 1]); no persistence/climatology rows, no metrics. Nodes reshape
    row-major to (n_lat, n_lon); extent is the Antarctic crop [0,360] x [-90,-40].
    Returns the Figure (and saves to `path` if given)."""
    field = np.asarray(field)
    H = field.shape[1]
    fig, axes = plt.subplots(1, H, figsize=(H * 2.5, 3.0), squeeze=False)
    axes = axes[0]
    im = None
    for k in range(H):
        grid = field[:, k].reshape(n_lat, n_lon)
        im = axes[k].imshow(grid, cmap=cmap, vmin=vmin, vmax=vmax,
                            origin="lower", aspect="auto", extent=[0, 360, -90, -40])
        axes[k].set_xticks([]); axes[k].set_yticks([])
        axes[k].set_title(titles[k] if titles is not None else f"+{k+1}w", fontsize=9)
    fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, label=cbar_label)
    if suptitle:
        fig.suptitle(suptitle, fontsize=12)
    if path:
        fig.savefig(path, dpi=150, bbox_inches="tight")
    return fig
