"""
data_loader.py — GNN SIC / SICA prediction data loading utilities
==================================================================
Loads NetCDF feature files, scales features (NOT the target), builds
sliding-window node/target tensors, loads the precomputed edge_index,
and exposes a `torch_geometric.loader.DataLoader` over PyG `Data` objects.

=========================================================================
DEPLOYMENT MAP — what the production team touches
=========================================================================
This module is copied from the research project and does more than the live path
needs. For a deployed digital twin, the relevant pieces are:

  LIVE / OPERATIONAL forecast (live_forecast.ipynb):
    * load_train_stats(path)      -> (scaler, train_means, meta): loads the FROZEN
                                     training-era normalisation from train_stats.npz.
    * prepare_live_window(dir, scaler, train_means, ...) -> (N_nodes, 40): builds
                                     the latest input window from recent .nc files,
                                     scaling with the frozen scaler (never re-fits).
    * CustomScaler                -> the per-variable z-score scaler (+ save/load).
    * DEFAULT_DATA_DIR            -> resolves to this project's data/ folder (where the
                                     .nc feed lives). RECENT_DIR in the notebook overrides it.

  VALIDATION-SPLIT check (inference_testset.ipynb):
    * prepare_sic_data(...)       -> rebuilds the chronological split + fits the scaler
                                     internally (needs the full .nc archive in data/).
    * make_loader(split, ...)     -> a PyG DataLoader over that split.

  train_stats.npz (the frozen scaler shipped in data/) was produced OFFLINE in the
  development environment; load_nc_files / fill_nans_with_train_mean /
  _stack_timestep_arrays / save_train_stats are the helpers it used, and are also
  called internally by prepare_sic_data.

  NOT used by the twin (inherited from training/eval): build_edge_index,
    dynamic_ice_mask, split_train_val_test, SICGraphDataset internals, the
    non-"standard" scaler modes.

Key data contract: the 40 input channels are FEATURE-MAJOR — [v0_t0, v0_t1, v0_t2,
v0_t3, v1_t0, ...] (variable-major, then lookback). The target is NEVER scaled
(SIC in [0,1]); only the 7 non-SIC feature variables are z-scored.

Supports both tasks:
    label = "sea_ice_concentration"  →  SIC,  sigmoid-head models,
                                        climatology baseline = sic_climatology
    label = "sic_anomaly"            →  SICA, linear-head models,
                                        climatology baseline = zeros

Quick start
-----------
    from util.data_loader import prepare_sic_data, make_loader, build_edge_index

    bundle = prepare_sic_data(
        label="sea_ice_concentration",
        input_size=4,
        prediction_horizon=8,
        train_frac=0.70,
        val_frac=0.15,
    )

    # edge_index comes from a precomputed .npy file produced by
    # Code/super_pixel_edge_creator.ipynb. Two files are expected:
    #   edge_index_4conn.npy  — 4-conn lattice + super-pixel edges
    #   edge_index_8conn.npy  — 8-conn lattice + super-pixel edges
    edge_index = build_edge_index(connectivity=8)

    train_loader = make_loader(bundle.train, edge_index, batch_size=2, shuffle=True)
    val_loader   = make_loader(bundle.val,   edge_index, batch_size=2, shuffle=False)
    test_loader  = make_loader(bundle.test,  edge_index, batch_size=2, shuffle=False)

    # Each batched `Data` carries the baselines alongside the target:
    #   batch.y      target            (B*N_nodes, prediction_horizon)
    #   batch.pers   persistence       (B*N_nodes, prediction_horizon)
    #   batch.clim   climatology       (B*N_nodes, prediction_horizon)
    bundle.scaler  # to inverse-transform features if needed

Design choices
--------------
- Mirrors the CNN project's data_loader.py 1:1 for shapes and semantics:
  channel ordering is FEATURE-MAJOR ([v0_t0, v0_t1, …, v0_t(L-1), v1_t0, …]),
  target/climatology/anomaly are NEVER scaled, splits are chronological
  with a leakage buffer.
- Node layout: the (H, W) grid is flattened row-major into N_NODES = H × W
  nodes. The edge_index is precomputed and lives on disk; switch lattice
  connectivity (4 vs 8) via the `connectivity` arg of `build_edge_index`.
- LAZY WINDOWING: instead of materialising every sliding window into one big
  (N_samples, N_nodes, C) array — which costs ~(input+horizon)× the raw data
  in RAM — we keep compact per-timestep arrays and build each window on the
  fly in `SICGraphDataset.get()`. A `Split` is just those shared arrays plus
  the window indices for that split. PyG's batching concatenates samples along
  the node axis, so a batch of B graphs gives x of shape (B*N_nodes, C).
"""

import os
import glob
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import xarray as xr
from torch_geometric.data import Data, Dataset as PyGDataset
from torch_geometric.loader import DataLoader as PyGDataLoader

from util.config import TIME_RESOLUTION


# The project's own `data/` folder — computed RELATIVE to this file (no hardcoded
# paths), so it resolves wherever the project is placed.
#   this file = <project>/Code/util/data_loader.py  ->  parents[2] = <project>  ->  <project>/data
# The folder is split (the dataprocessor writes the same layout):
#   data/historical/  — the frozen training-era .nc ARCHIVE (what prepare_sic_data / the scaler use)
#   data/live/final_1_degree/  — the LATEST .nc feed the dataprocessor builds (live_forecast RECENT_DIR)
#   data/  (root)     — mesh bundle, checkpoint, train_stats.npz
_SIBLING_DATA = str(Path(__file__).resolve().parents[2] / "data")
_HIST_DATA    = os.path.join(_SIBLING_DATA, "historical")
_LIVE_DATA    = os.path.join(_SIBLING_DATA, "live", "final_1_degree")

# Where the .nc ARCHIVE is looked up (autodetect / prepare_sic_data default). The historical
# archive comes first; the live feed and the root are fallbacks. (The notebooks pass explicit
# paths too, so these are only the fallback.) Add new hosts here rather than hardcoding elsewhere.
_CANDIDATE_DATA_DIRS = [
    _HIST_DATA,        # <project>/data/historical/  — the frozen .nc archive lives here
    _LIVE_DATA,        # <project>/data/live/final_1_degree/  — the live feed (fallback)
    _SIBLING_DATA,     # <project>/data/  — legacy flat layout (fallback)
]

_CANDIDATE_EDGE_DIRS = [
    _SIBLING_DATA,     # <project>/data/  — multi_mesh_bundle_K5.npz lives here (root)
]


def _autodetect_data_dir() -> str:
    """Return the first candidate dir that exists AND contains at least one .nc file.
    The `.nc` check matters here: the deployment project keeps a `data/` folder for the
    bundle/checkpoint/stats that may hold NO `.nc` archive, so an existence-only check
    would wrongly select it and every load would fail with 'no files to open'."""
    for p in _CANDIDATE_DATA_DIRS:
        if os.path.isdir(p) and glob.glob(os.path.join(p, "*.nc")):
            return os.path.join(p, "")
    raise FileNotFoundError(
        "No candidate data directory with .nc files exists on this machine:\n  "
        + "\n  ".join(_CANDIDATE_DATA_DIRS)
        + "\nAdd this machine's archive path to _CANDIDATE_DATA_DIRS in util/data_loader.py, "
          "or pass an explicit data_dir/RECENT_DIR."
    )


def _find_edge_file(filename: str) -> Optional[str]:
    """Look up an edge-index file across candidate dirs. Returns None if missing."""
    for d in _CANDIDATE_EDGE_DIRS:
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    return None


# Tolerant at import: the live/deployment path may run on a machine with only a
# small recent .nc feed (passed explicitly), no full archive in any candidate dir.
# So don't raise here — fall back to the sibling data/ and let functions that truly
# need an archive fail later (or accept an explicit data_dir) with a clear message.
try:
    DEFAULT_DATA_DIR = _autodetect_data_dir()
except FileNotFoundError:
    DEFAULT_DATA_DIR = os.path.join(_SIBLING_DATA, "")


# ─────────────────────────────────────────────
#  Scaler
# ─────────────────────────────────────────────

class CustomScaler:
    """Per-variable scaler with NaN-aware statistics."""

    def __init__(self):
        self.scalers = {}

    def fit(self, data: xr.Dataset):
        for var in data.data_vars:
            arr = data[var]
            self.scalers[var] = {
                "mean": float(arr.mean(skipna=True).values),
                "std":  float(arr.std(skipna=True).values),
                "min":  float(arr.min(skipna=True).values),
                "max":  float(arr.max(skipna=True).values),
            }

    # ── z-score ──────────────────────────────────────────────────────
    def standard_transform_var(self, data, var):
        s = self.scalers[var]
        return (data - s["mean"]) / s["std"]

    def standard_inverse_transform_var(self, data, var):
        s = self.scalers[var]
        return data * s["std"] + s["mean"]

    def standard_transform_xr(self, data, vars: Optional[List[str]] = None):
        targets = set(vars) if vars is not None else set(data.data_vars)
        out = {}
        for v in data.data_vars:
            out[v] = self.standard_transform_var(data[v], v) if v in targets else data[v]
        return xr.Dataset(out)

    # ── min-max ──────────────────────────────────────────────────────
    def min_max_transform_var(self, data, var):
        s = self.scalers[var]
        return (data - s["min"]) / (s["max"] - s["min"])

    def min_max_inverse_transform_var(self, data, var):
        s = self.scalers[var]
        return data * (s["max"] - s["min"]) + s["min"]

    # ── [-1, 1] ──────────────────────────────────────────────────────
    def minus_one_one_transform_var(self, data, var):
        s = self.scalers[var]
        return 2 * (data - s["min"]) / (s["max"] - s["min"]) - 1

    def minus_one_one_inverse_transform_var(self, data, var):
        s = self.scalers[var]
        return ((data + 1) * (s["max"] - s["min"]) / 2) + s["min"]

    # ── (de)serialization ─────────────────────────────────────────────
    # A fitted scaler is just the per-variable stats dict, so it round-trips
    # through JSON. The DEPLOYMENT (live) path must reuse the EXACT training-era
    # stats — never re-fit on a shifting live archive — so we freeze them here.
    def to_dict(self) -> Dict[str, dict]:
        return self.scalers

    @classmethod
    def from_dict(cls, d: Dict[str, dict]) -> "CustomScaler":
        s = cls()
        s.scalers = {k: dict(v) for k, v in d.items()}
        return s

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.scalers, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "CustomScaler":
        with open(path) as f:
            return cls.from_dict(json.load(f))


# ─────────────────────────────────────────────
#  Loading + NaN handling
# ─────────────────────────────────────────────

def load_nc_files(
    data_dir: str = DEFAULT_DATA_DIR,
    features: Optional[List[str]] = None,
    time_resolution: str = "weekly",
) -> xr.Dataset:
    """Load all .nc files in `data_dir`. If `features` is given, keep only those vars."""
    data = xr.open_mfdataset(
        data_dir + "*.nc",
        combine="by_coords",
        engine="netcdf4",
        compat="override",
    )

    if time_resolution == "weekly":
       data = data.coarsen(time=7, boundary="pad").mean()

    if features:
        data = data[features]
    return data


def fill_nans_with_train_mean(data: xr.Dataset, train_data: xr.Dataset) -> xr.Dataset:
    """Replace NaNs with per-variable training-period mean (skipna=True)."""
    out = {}
    for v in data.data_vars:
        if data[v].isnull().any():
            mean = float(train_data[v].mean(skipna=True).values)
            out[v] = data[v].fillna(mean)
        else:
            out[v] = data[v]
    return xr.Dataset(out)


# ─────────────────────────────────────────────
#  Compact per-timestep arrays (lazy windowing)
# ─────────────────────────────────────────────

def _stack_timestep_arrays(
    data: xr.Dataset,
    label: str = "sea_ice_concentration",
    climatology_var: str = "sic_climatology",
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Flatten the (scaled) dataset to compact PER-TIMESTEP node-major arrays.
    Sliding windows are NOT materialised here — they're built on the fly per
    sample in `SICGraphDataset.get()`, which keeps peak RAM ~= one copy of the
    raw data instead of (input_size+horizon)× that from dense windowing.

    Returns (float32):
        feat : (T, N_nodes, n_vars)  — every data_var, in dataset order
        tgt  : (T, N_nodes)          — the (unscaled) label
        clim : (T, N_nodes)          — climatology BASELINE

    Climatology baseline depends on the target:
        label == "sic_anomaly"           → all zeros (anomaly clim = 0 by definition)
        label == "sea_ice_concentration" (or other) → `climatology_var` field
    """
    # (n_vars, T, H, W) → (T, H, W, n_vars) → (T, N_nodes, n_vars)
    arr = data.to_array().values
    n_vars, T, H, W = arr.shape
    feat = np.ascontiguousarray(np.transpose(arr, (1, 2, 3, 0))).reshape(T, H * W, n_vars)
    feat = feat.astype(np.float32, copy=False)
    del arr

    tgt = data[label].values.reshape(T, H * W).astype(np.float32, copy=False)
    if label == "sic_anomaly":
        # Zero-anomaly climatology baseline.
        clim = np.zeros_like(tgt)
    else:
        clim = data[climatology_var].values.reshape(T, H * W).astype(np.float32, copy=False)
    return feat, tgt, clim


# ─────────────────────────────────────────────
#  Leakage-safe chronological split
# ─────────────────────────────────────────────

@dataclass
class Split:
    """One split, lazy. The big per-timestep arrays (`feat`/`tgt`/`clim`) are
    SHARED by reference across train/val/test — only `indices` differs, so the
    three splits cost one copy of the data total. Each `indices[j]` is a global
    window start; `SICGraphDataset` builds that window on demand."""
    feat:    np.ndarray   # (T, N_nodes, n_vars)  shared
    tgt:     np.ndarray   # (T, N_nodes)          shared
    clim:    np.ndarray   # (T, N_nodes)          shared
    indices: np.ndarray   # (n_split,) global window start-indices for this split
    input_size: int
    prediction_horizon: int


def split_train_val_test(
    feat: np.ndarray,
    tgt: np.ndarray,
    clim: np.ndarray,
    n_samples: int,
    input_size: int,
    prediction_horizon: int,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    buffer: int = 0,
) -> Tuple[Split, Split, Split]:
    """Chronological split on the window indices, with a `buffer`-sample gap to
    prevent leakage. Index ranges match the old array-slicing exactly:
    train [0, train_end-buffer), val [train_end, val_end-buffer), test [val_end, N)."""
    n = n_samples
    train_end = int(n * train_frac)
    val_end   = train_end + int(n * val_frac)

    def mk(start, stop):
        return Split(
            feat, tgt, clim,
            np.arange(max(start, 0), max(stop, 0), dtype=np.int64),
            input_size, prediction_horizon,
        )

    train = mk(0,         train_end - buffer)
    val   = mk(train_end, val_end - buffer)
    test  = mk(val_end,   n)
    return train, val, test


def dynamic_ice_mask(split: Split, threshold: float = 0.01) -> np.ndarray:
    """
    Boolean (N_nodes,) mask of nodes whose target SIC standard deviation across
    the split's windowed targets (samples x horizon) exceeds `threshold`.
    Permanent open ocean (~0) and permanent pack (~1) are masked out, so masked
    metrics aren't diluted by trivially-predictable pixels.

    Mirrors the CNN project's `dynamic_ice_mask` exactly (there: channels-last
    `split.target.std(axis=(0, 3)) > threshold`). Pass `bundle.train` so the
    mask is derived from training data only (no val/test leakage) and reuse the
    same mask across all models/baselines for comparability.

    Std is accumulated per node over the H horizon offsets (memory-safe: one
    (n_samples, N_nodes) gather at a time, never the full windowed array).
    """
    tgt = split.tgt                      # (T, N_nodes)
    idx = split.indices                  # (n,) window starts
    L, H = split.input_size, split.prediction_horizon
    n_nodes = tgt.shape[1]
    cnt = len(idx) * H
    ssum = np.zeros(n_nodes, dtype=np.float64)
    ssq  = np.zeros(n_nodes, dtype=np.float64)
    for h in range(H):
        vals = tgt[idx + L + h].astype(np.float64)   # (n, N_nodes)
        ssum += vals.sum(axis=0)
        ssq  += (vals ** 2).sum(axis=0)
    mean = ssum / cnt
    std = np.sqrt(np.maximum(ssq / cnt - mean ** 2, 0.0))
    return std > threshold


# ─────────────────────────────────────────────
#  Graph construction
# ─────────────────────────────────────────────

def _grid_adjacency_edges(n_lat: int, n_lon: int, connectivity: int = 8) -> np.ndarray:
    """
    Build the edge list for a (n_lat × n_lon) row-major grid graph.

    connectivity=4 → N/S/E/W neighbours.
    connectivity=8 → also NE/NW/SE/SW (diagonals).

    Returns edge_index of shape (2, n_edges), undirected (both directions
    included). Node id for (i, j) is i * n_lon + j.
    """
    edges = []

    def idx(i, j):
        return i * n_lon + j

    for i in range(n_lat):
        for j in range(n_lon):
            if j + 1 < n_lon:
                edges.append((idx(i, j), idx(i, j + 1)))
            if i + 1 < n_lat:
                edges.append((idx(i, j), idx(i + 1, j)))
            if connectivity == 8:
                if i + 1 < n_lat and j + 1 < n_lon:
                    edges.append((idx(i, j), idx(i + 1, j + 1)))
                if i + 1 < n_lat and j - 1 >= 0:
                    edges.append((idx(i, j), idx(i + 1, j - 1)))

    e = np.array(edges, dtype=np.int64).T                  # (2, n_directed)
    # Symmetrise → undirected
    edge_index = np.concatenate([e, e[[1, 0]]], axis=1)    # (2, 2 * n_directed)
    return edge_index


def build_edge_index(connectivity: int = 8) -> torch.Tensor:
    """
    Load the precomputed edge_index for the SIC graph.

    The file is produced by `Code/super_pixel_edge_creator.ipynb` and
    already contains the grid lattice edges concatenated with the
    super-pixel hub edges, so this function is a pure file load.

    Args:
        connectivity: 4 → loads `edge_index_4conn.npy` (N/S/E/W only).
                      8 → loads `edge_index_8conn.npy` (+ NE/NW/SE/SW).

    Returns torch.long tensor of shape (2, n_edges).
    """
    if connectivity not in (4, 8):
        raise ValueError(f"connectivity must be 4 or 8; got {connectivity}")

    filename = f"edge_index_{connectivity}conn.npy"
    path = _find_edge_file(filename)
    if path is None:
        raise FileNotFoundError(
            f"{filename!r} not found in any of:\n  "
            + "\n  ".join(_CANDIDATE_EDGE_DIRS)
            + "\n\nGenerate it with Code/super_pixel_edge_creator.ipynb (which writes "
              "both 4conn and 8conn files), then copy into one of those dirs — "
              "or extend _CANDIDATE_EDGE_DIRS in util/data_loader.py."
        )

    arr = np.load(path).astype(np.int64)
    if arr.ndim != 2 or arr.shape[0] != 2:
        raise ValueError(f"{filename} must have shape (2, n_edges); got {arr.shape}")
    return torch.from_numpy(arr).contiguous()


# ─────────────────────────────────────────────
#  PyG Dataset + DataLoader
# ─────────────────────────────────────────────

class SICGraphDataset(PyGDataset):
    """
    Serves one PyG `Data` per time-window, building the window ON THE FLY from
    the shared per-timestep arrays (no dense pre-expansion). PyG's batching
    concatenates B graphs along the node axis, giving x of shape
    (B * N_nodes, C_in) and y of shape (B * N_nodes, prediction_horizon).

    For global window start `i` (L = input_size, H = prediction_horizon):
      x    : feat[i : i+L]  reordered to feature-major channels (N_nodes, n_vars*L)
             with channel c = var*L + lookback  ([v0_t0..v0_t(L-1), v1_t0, ...])
      y    : tgt[i+L : i+L+H]                      (N_nodes, H)
      pers : tgt[i+L-1] tiled across the horizon   (N_nodes, H)
      clim : clim[i+L : i+L+H]                     (N_nodes, H)
    """
    def __init__(self, split: Split, edge_index: torch.Tensor):
        super().__init__()
        self.feat    = split.feat
        self.tgt     = split.tgt
        self.clim    = split.clim
        self.win_idx = split.indices      # NB: not `indices` — PyG Dataset.indices() exists
        self.L       = split.input_size
        self.H       = split.prediction_horizon
        self.edge_index = edge_index

    def len(self):
        return len(self.win_idx)

    def get(self, idx):
        i = int(self.win_idx[idx])
        L, H = self.L, self.H
        win = self.feat[i : i + L]                                  # (L, N_nodes, n_vars)
        # (L, N_nodes, n_vars) → (N_nodes, n_vars, L) → (N_nodes, n_vars*L), feature-major.
        x    = np.transpose(win, (1, 2, 0)).reshape(win.shape[1], -1)
        y    = self.tgt[i + L : i + L + H].T                        # (N_nodes, H)
        pers = np.repeat(self.tgt[i + L - 1][:, None], H, axis=1)   # (N_nodes, H)
        clim = self.clim[i + L : i + L + H].T                       # (N_nodes, H)
        return Data(
            x          = torch.from_numpy(np.ascontiguousarray(x,    dtype=np.float32)),
            edge_index = self.edge_index,
            y          = torch.from_numpy(np.ascontiguousarray(y,    dtype=np.float32)),
            pers       = torch.from_numpy(np.ascontiguousarray(pers, dtype=np.float32)),
            clim       = torch.from_numpy(np.ascontiguousarray(clim, dtype=np.float32)),
        )


def make_loader(
    split: Split,
    edge_index: torch.Tensor,
    batch_size: int = 2,
    shuffle: bool = False,
    num_workers: int = 0,
    pin_memory: bool = True,
    generator=None,
) -> PyGDataLoader:
    """PyG DataLoader factory. num_workers defaults to 0 for portability
    (Windows spawns workers, which would pickle the shared per-timestep
    arrays). On Linux you can safely raise it — fork shares those arrays
    copy-on-write, and windowing each sample is cheap CPU work that overlaps
    GPU compute. Pass a seeded `generator` to make the shuffle order reproducible
    (and identical across models, independent of weight-init RNG consumption)."""
    return PyGDataLoader(
        SICGraphDataset(split, edge_index),
        batch_size         = batch_size,
        shuffle            = shuffle,
        num_workers        = num_workers,
        pin_memory         = pin_memory,
        persistent_workers = num_workers > 0,   # don't respawn workers every epoch
        generator          = generator,
    )


# ─────────────────────────────────────────────
#  Top-level orchestrator
# ─────────────────────────────────────────────

@dataclass
class DataBundle:
    train: Split
    val:   Split
    test:  Split
    scaler: CustomScaler
    feature_vars: List[str]
    n_features:   int
    n_lookback:   int
    prediction_horizon: int
    n_lat: int
    n_lon: int
    n_nodes: int
    lat: np.ndarray
    lon: np.ndarray
    time_resolution: str


def prepare_sic_data(
    data_dir: str = DEFAULT_DATA_DIR,
    label: str = "sea_ice_concentration",
    input_size: int = 4,
    prediction_horizon: int = 8,
    train_frac: float = 0.70,
    val_frac: float = 0.15,
    features: Optional[List[str]] = None,
    climatology_var: str = "sic_climatology",
    scale_kind: str = "standard",
    time_resolution: str = TIME_RESOLUTION,
) -> DataBundle:
    """
    Full pipeline: load → fit scaler on training period → NaN-fill →
    scale features (NOT the target/climatology/anomaly) → window → split.

    Mirrors the CNN project's prepare_sic_data, but the per-split arrays
    here are node-major: (N_samples, N_nodes, C) instead of channels-last
    (N_samples, H, W, C). Use `build_edge_index` separately to construct
    the graph topology, then `make_loader(split, edge_index, ...)` to
    obtain a PyG DataLoader.
    """
    # ── Load raw (daily on disk; coarsened to weekly if requested) ────
    data = load_nc_files(data_dir, features=features, time_resolution=time_resolution)

    # ── Identify what to scale (everything except target/climatology) ─
    # Both SIC and SIC anomaly are kept unscaled regardless of which is the
    # active label, so neither gets z-scored when it's a feature.
    UNSCALED_VARS = {label, climatology_var, "sic_anomaly", "sea_ice_concentration"}
    feature_vars = [v for v in data.data_vars if v not in UNSCALED_VARS]

    # ── Training-period slice (for stats and NaN-fill) ────────────────
    train_end_time = int(len(data.time) * train_frac)
    train_data     = data.isel(time=slice(0, train_end_time))

    # ── NaN handling using TRAINING means ─────────────────────────────
    data = fill_nans_with_train_mean(data, train_data)
    train_data = data.isel(time=slice(0, train_end_time))

    # ── Fit scaler on training data, scale only feature vars ──────────
    scaler = CustomScaler()
    scaler.fit(train_data[feature_vars])

    if scale_kind == "standard":
        scaled = scaler.standard_transform_xr(data, vars=feature_vars)
    elif scale_kind == "min_max":
        scaled = xr.Dataset({
            v: (scaler.min_max_transform_var(data[v], v) if v in feature_vars else data[v])
            for v in data.data_vars
        })
    elif scale_kind == "minus_one_one":
        scaled = xr.Dataset({
            v: (scaler.minus_one_one_transform_var(data[v], v) if v in feature_vars else data[v])
            for v in data.data_vars
        })
    else:
        raise ValueError(f"Unknown scale_kind: {scale_kind!r}")

    # ── Compact per-timestep arrays (windows built lazily per sample) ─
    feat, tgt, clim = _stack_timestep_arrays(scaled, label=label, climatology_var=climatology_var)
    T = feat.shape[0]
    n_samples = T - input_size - prediction_horizon + 1
    if n_samples <= 0:
        raise ValueError(
            f"Not enough timesteps ({T}) for input_size={input_size} + "
            f"prediction_horizon={prediction_horizon}."
        )

    # ── Leakage-safe chronological split (on window indices) ──────────
    buffer = input_size + prediction_horizon
    train, val, test = split_train_val_test(
        feat, tgt, clim, n_samples,
        input_size         = input_size,
        prediction_horizon = prediction_horizon,
        train_frac         = train_frac,
        val_frac           = val_frac,
        buffer             = buffer,
    )

    n_lat = len(scaled.lat)
    n_lon = len(scaled.lon)
    return DataBundle(
        train              = train,
        val                = val,
        test               = test,
        scaler             = scaler,
        feature_vars       = list(scaled.data_vars),
        n_features         = len(scaled.data_vars),
        n_lookback         = input_size,
        prediction_horizon = prediction_horizon,
        n_lat              = n_lat,
        n_lon              = n_lon,
        n_nodes            = n_lat * n_lon,
        lat                = scaled.lat.values,
        lon                = scaled.lon.values,
        time_resolution    = time_resolution,
    )


# ─────────────────────────────────────────────
#  Deployment (live) inference — persisted-scaler path
# ─────────────────────────────────────────────
#
# The training pipeline (`prepare_sic_data`) fits the scaler + NaN-fill means on
# the training slice of whatever archive is present. A deployed digital twin must
# instead reuse the FROZEN training-era statistics on every new observation, so
# they are frozen ONCE offline into the shipped `train_stats.npz` and the live path
# below just loads them — it never re-fits. The target is unscaled (SIC in [0, 1],
# sigmoid head), so model outputs are already SIC; nothing to inverse-transform.

def save_train_stats(path, scaler: "CustomScaler", train_means: Dict[str, float], *,
                     var_order: List[str], label: str, climatology_var: str,
                     time_resolution: str):
    """Freeze everything the live path needs to reproduce training normalization:
    the fitted feature scaler, the per-variable NaN-fill means, the full data_vars
    ORDER (which fixes the feature-major channel layout the checkpoint expects),
    and the label/climatology/resolution the model was trained with."""
    np.savez(
        path,
        scaler_json=json.dumps(scaler.to_dict()),
        train_means_json=json.dumps({k: float(v) for k, v in train_means.items()}),
        var_order=np.array(list(var_order)),
        label=str(label), climatology_var=str(climatology_var),
        time_resolution=str(time_resolution),
    )


def load_train_stats(path):
    """Return (scaler, train_means, meta) from a `train_stats.npz`.
    meta = {var_order, label, climatology_var, time_resolution}."""
    z = np.load(path, allow_pickle=True)
    scaler = CustomScaler.from_dict(json.loads(str(z["scaler_json"].item())))
    train_means = json.loads(str(z["train_means_json"].item()))
    meta = dict(
        var_order=[str(v) for v in z["var_order"]],
        label=str(z["label"]),
        climatology_var=str(z["climatology_var"]),
        time_resolution=str(z["time_resolution"]),
    )
    return scaler, train_means, meta


def prepare_live_window(
    data_dir: str,
    scaler: "CustomScaler",
    train_means: Dict[str, float],
    *,
    var_order: Optional[List[str]] = None,
    label: str = "sea_ice_concentration",
    climatology_var: str = "sic_climatology",
    input_size: int = 4,
    time_resolution: str = TIME_RESOLUTION,
    features: Optional[List[str]] = None,
) -> np.ndarray:
    """Build ONE latest input window from recent .nc data for operational forecasting.

    The live analogue of `prepare_sic_data`, but with NO split and NO target: it
    NaN-fills with the PERSISTED training means, scales feature vars with the
    PERSISTED scaler (never re-fitting), and returns the most recent `input_size`
    timesteps as a single feature-major node array:

        x : (N_nodes, n_vars * input_size)   float32   channel c = var*L + lookback

    `var_order` (from `train_stats` meta) reorders the loaded vars to the exact
    training channel order so `x` lines up with the checkpoint. `data_dir` must
    hold the SAME variables as training (incl. `label` and `climatology_var`) for
    at least `input_size` steps after weekly coarsening.
    """
    data = load_nc_files(data_dir, features=features, time_resolution=time_resolution)

    # Reorder to the exact training data_vars order (fixes the channel layout).
    if var_order is not None:
        missing = [v for v in var_order if v not in data.data_vars]
        if missing:
            raise ValueError(f"Live data is missing training variables: {missing}")
        data = data[list(var_order)]

    UNSCALED_VARS = {label, climatology_var, "sic_anomaly", "sea_ice_concentration"}
    feature_vars = [v for v in data.data_vars if v not in UNSCALED_VARS]

    # NaN-fill with PERSISTED training means (never recomputed from live data).
    filled = {}
    for v in data.data_vars:
        if data[v].isnull().any():
            if v not in train_means:
                raise KeyError(f"No persisted train mean for '{v}' to NaN-fill.")
            filled[v] = data[v].fillna(train_means[v])
        else:
            filled[v] = data[v]
    data = xr.Dataset(filled)

    # Scale feature vars with the frozen scaler (z-score); target/clim left as-is.
    scaled = scaler.standard_transform_xr(data, vars=feature_vars)

    # Compact per-timestep arrays, then take the LAST input_size steps as one window.
    feat, _, _ = _stack_timestep_arrays(scaled, label=label, climatology_var=climatology_var)
    T = feat.shape[0]
    if T < input_size:
        raise ValueError(f"Need >= {input_size} timesteps for a live window; got {T}.")
    win = feat[T - input_size:]                                   # (L, N_nodes, n_vars)
    # (L, N_nodes, n_vars) -> (N_nodes, n_vars, L) -> (N_nodes, n_vars*L), feature-major.
    x = np.transpose(win, (1, 2, 0)).reshape(win.shape[1], -1)
    return np.ascontiguousarray(x, dtype=np.float32)
