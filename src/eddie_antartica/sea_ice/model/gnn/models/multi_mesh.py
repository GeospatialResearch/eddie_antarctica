"""
multi_mesh.py — GraphCast-style multi-mesh GNN for Antarctic sea-ice forecasting.

=========================================================================
WHAT THIS MODEL IS (read this first)
=========================================================================
We forecast sea-ice concentration on a 50×360 lat/lon grid = 18,000 "grid
nodes". Each grid node carries 40 input channels (10 variables × 4 past weeks)
and must predict 8 future weeks. The hard part: ice/ocean signals travel LONG
distances, but a plain grid GNN moves information only ONE hop per layer — so
spanning the continent would need dozens of layers (slow, and they blur detail).

GraphCast's idea (Lam et al., 2022) is to add a SECOND, much COARSER set of
nodes — an icosahedral "mesh" (~1,800 nodes spread evenly over the sphere) — and
route long-range information through it. Picture the grid as local streets and
the mesh as a highway grid laid on top: you get on the highway (ENCODER), travel
far in a few hops (PROCESSOR), then exit back to the streets (DECODER). So there
are TWO node sets and THREE phases:

    GRID  (18,000 lat/lon cells)            MESH  (~1,800 icosahedral nodes)
    carries the real input data             carries NO data — a learned vector
            │                                          ▲    │
            │ grid_embed (MLP: 40 → 128)               │    │
            ▼                                          │    ▼
        h_grid ──[ ENCODER: grid → mesh ]───────────►  h_mesh
                                                            │
                                          PROCESSOR: K rounds of
                                          mesh ↔ mesh message passing
                                          (the long-range mixing; the operator
                                           used HERE is what --processor ablates)
                                                            │
        h_grid ◄──[ DECODER: mesh → grid ]──────────────────┘
            │
            │ readout (MLP) + skip back to the raw input
            ▼
        SIC forecast (18,000 nodes × 8 weeks), squashed to [0,1] by sigmoid
            (SICA instead uses a linear head — signed anomalies, not in [0,1])

=========================================================================
WHAT "MESSAGE PASSING" MEANS HERE (the Interaction Network)
=========================================================================
Every phase is an *Interaction Network* layer (Battaglia et al., 2016) — the
most general message-passing GNN. For one layer, each node i is updated in 3
steps:

  1. MESSAGE (per edge j→i): build a message from BOTH endpoints (and, in the
     processor, a descriptor of the edge):
         m_ij = MLP_edge( [ h_i , h_j , edge_attr_ij ] )
  2. AGGREGATE (per node i): sum the messages arriving at i:
         m_i  = Σ over neighbours j of  m_ij
  3. UPDATE (per node i): mix i's own state with its aggregated messages, with a
     residual + LayerNorm so deep stacks train stably:
         h_i ← LayerNorm( h_i + MLP_node( [ h_i , m_i ] ) )

"Interaction" = the message is a learned NONLINEAR function of the sender AND
receiver (their interaction), not a plain copy or weighted average. That is what
makes it more expressive than GraphSAGE (fixed mean of neighbours) or GAT
(attention-weighted *linear* messages) — see `make_processor()` for the operator
swap that the ablation uses.

=========================================================================
THE MESH GRAPH (what lives in multi_mesh_bundle.npz)
=========================================================================
Built once by Code/mesh/multi_mesh_creator.ipynb, loaded at construction:
  • encoder_edges (grid → mesh): which grid cells feed which mesh node.
  • mm_edges      (mesh ↔ mesh): the mesh's own wiring, spanning K+1 REFINEMENT
                  LEVELS. The icosahedron is subdivided K times; level 0 = coarse
                  long edges (highways), level K = fine short edges (local roads).
                  Each edge stores its level in mm_levels, and `level_embed` turns
                  that into the edge_attr the processor reads — so the network can
                  treat long-range vs short-range mesh edges differently.
                  (These edges are stored ONCE per pair in a single orientation,
                  i.e. directed, not symmetrised — see the loading code.)
  • decoder_edges (mesh → grid): which mesh nodes write back to which grid cell.
Edges are registered as buffers so they follow the model under `.to(device)`.

=========================================================================
BATCHING
=========================================================================
PyG batches B samples by concatenating their nodes along axis 0. The mesh graph
is identical for every sample, so `forward()` tiles the stored edges B times with
per-sample index offsets (`_batch_edges`). The public call stays:
    pred = model(batch.x, batch.edge_index)
`batch.edge_index` (the grid lattice) is IGNORED — this model carries its own
mesh edges internally.

=========================================================================
AT RUNTIME (production) — what this file actually runs
=========================================================================
The deployed model is `MultiMeshGridARGNN` (in multi_mesh_grid_ar.py), which
subclasses `MultiMeshGridGNN` -> `MultiMeshGNN` (this file). In production only
two things execute: the constructor `__init__` (loads the mesh bundle, builds the
layers) and `forward` (the prediction). The processor operator is fixed to
`"interaction"` for the deployed checkpoint.

Helpers in this file that are BUILD/ABLATION-time only (safe to ignore for
deployment): `make_processor`'s non-interaction branches (sage/gat/diffusion) and
`_DConvBlock` — the diffusion branch also lazily imports `torch_geometric_temporal`,
which the deployment does NOT install; `graph_tag` / `build_run_name` /
`resolve_bundle_path` / `_find_bundle` — filename/bundle bookkeeping used by the
research CLI. None of these run on the live forward path.
"""
import os
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.nn import MessagePassing, SAGEConv, GATConv

from util.data_loader import _CANDIDATE_EDGE_DIRS


# ─────────────────────────────────────────────────────────────────────
#  Output-activation switch (SIC: sigmoid; SICA: linear)
# ─────────────────────────────────────────────────────────────────────
def _make_output_activation(name: str) -> nn.Module:
    """sigmoid for SIC (target in [0,1]); linear for SICA (signed anomaly)."""
    if name == "sigmoid": return nn.Sigmoid()
    if name == "linear":  return nn.Identity()
    raise ValueError(f"Unknown output_activation: {name!r}. Use 'sigmoid' or 'linear'.")


# ─────────────────────────────────────────────────────────────────────
#  Bundle lookup
# ─────────────────────────────────────────────────────────────────────
def _find_bundle(filename: str = "multi_mesh_bundle.npz") -> str:
    for d in _CANDIDATE_EDGE_DIRS:
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(
        f"{filename!r} not found in any of:\n  "
        + "\n  ".join(_CANDIDATE_EDGE_DIRS)
        + "\nRun Code/multi_mesh_creator.ipynb to produce it."
    )


# ─────────────────────────────────────────────────────────────────────
#  Graph tag — a short id of the coarse graph's *refinement*, recorded in
#  run names / training logs / checkpoints / test npz so a run always says
#  which mesh (K) or SLIC (n_segments, levels) it was trained & tested on.
# ─────────────────────────────────────────────────────────────────────
DEFAULT_GRAPH_TAG = "mesh_K5"   # the standard icosahedral mesh; gets NO run-name suffix


def _graph_tag_from_bundle(bundle) -> str:
    """icosahedral mesh -> 'mesh_K{K}';  SLIC ->
    'slic[_polar][_<features>][-<stat>]_n{nodes}_L{levels}' (n = ACTUAL supernode count;
    the '_polar' marker appears only for the polar-stereographic projection, and the
    feature/stat suffix is omitted for the default SIC-only mean, so the standard
    lat-lon SIC names stay back-compatible)."""
    if "source" in bundle.files and str(bundle["source"]).startswith("slic"):
        n_nodes = int(bundle["mesh_lat"].shape[0])
        L = int(bundle["levels"]) if "levels" in bundle.files else 1
        feat = str(bundle["feat_tag"]) if "feat_tag" in bundle.files else "sic"
        stat = str(bundle["stat"])     if "stat"     in bundle.files else "mean"
        proj = str(bundle["projection"]) if "projection" in bundle.files else "latlon"
        proj_tag = "" if proj == "latlon" else f"_{proj}"        # e.g. '_polar'
        suffix = "" if (feat == "sic" and stat == "mean") else \
                 "_" + feat + ("" if stat == "mean" else f"-{stat}")
        return f"slic{proj_tag}{suffix}_n{n_nodes}_L{L}"
    return f"mesh_K{int(bundle['K'])}"


def graph_tag(bundle_path: Optional[str] = None) -> str:
    """Graph tag for a bundle path (default: the auto-detected mesh bundle)."""
    if bundle_path is None:
        bundle_path = _find_bundle()
    return _graph_tag_from_bundle(np.load(bundle_path))


# Friendly operator labels for the run name (others fall through to the --processor
# name). Edit here to rename an operator in the output filenames.
_GNN_LABEL = {"gat": "deepgat"}


def build_run_name(model: str, gtag: str, processor: str = "interaction", seed=None) -> str:
    """Human-readable run name (task prefix added separately by the caller):
        {graph_type}_{structure}_{gnn}_{grid_ar}[_seed{seed}]
      graph_type + structure  <- graph_tag:  'mesh_K5' stays 'mesh_K5'; a SLIC tag
                                  'slic[_<feat>][-<stat>]_n{n}_L{L}' collapses to
                                  'slic_n{n}_L{L}' (the feature/stat tag is dropped).
      gnn        <- processor  (mapped via _GNN_LABEL, e.g. gat -> deepgat).
      grid_ar    <- the model name minus its 'multi_mesh' base -> 'grid_ar'/'grid'/'ar'/''.
      seed       <- appended as '_seed{seed}' only when given (multi-seed sweeps), so
                    seeds don't clobber; omitted (clean names) for single runs.
    e.g. build_run_name('multi_mesh_grid_ar', 'slic_sic-t2m-sst_n1805_L5', 'interaction', 3)
         -> 'slic_n1805_L5_interaction_grid_ar_seed3'."""
    if gtag.startswith("slic"):
        toks = gtag.split("_")
        n_tok = next((t for t in toks if t.startswith("n") and t[1:].isdigit()), None)
        l_tok = next((t for t in toks if t.startswith("L") and t[1:].isdigit()), None)
        graph = "_".join(["slic"] + [t for t in (n_tok, l_tok) if t])
    else:
        graph = gtag                                    # mesh_K5 / mesh_K6
    gnn = _GNN_LABEL.get(processor, processor)
    variant = model[len("multi_mesh"):].strip("_") if model.startswith("multi_mesh") else model
    name = "_".join([graph, gnn] + ([variant] if variant else []))
    if seed is not None:
        name += f"_seed{seed}"
    return name


def resolve_bundle_path(bundle: Optional[str]) -> str:
    """Map a --bundle value to a concrete bundle path. Accepts:
        'mesh' / None      -> multi_mesh_bundle_K5.npz (the canonical low-res mesh)
        'slic'             -> slic_bundle.npz
        an existing path   -> used as-is
        any other filename -> searched on the candidate edge dirs by basename
    so you can point at e.g. multi_mesh_bundle_K6.npz or slic_bundle_n4500_L6.npz.

    The bare `multi_mesh_bundle.npz` is REJECTED — every mesh must be an explicit
    refinement (multi_mesh_bundle_K5/_K6) so a run is never ambiguous about which
    mesh it used."""
    if bundle in (None, "mesh"):
        return _find_bundle("multi_mesh_bundle_K5.npz")
    if bundle == "slic":
        return _find_bundle("slic_bundle.npz")
    if os.path.basename(bundle) == "multi_mesh_bundle.npz":
        raise ValueError(
            "The bare 'multi_mesh_bundle.npz' is no longer accepted — use an explicit "
            "refinement: 'multi_mesh_bundle_K5.npz' or 'multi_mesh_bundle_K6.npz'.")
    if os.path.isfile(bundle):
        return os.path.abspath(bundle)
    return _find_bundle(os.path.basename(bundle))


# ─────────────────────────────────────────────────────────────────────
#  Interaction Network layers
# ─────────────────────────────────────────────────────────────────────
class InteractionLayer(MessagePassing):
    """One **Interaction Network** layer (Battaglia et al., 2016) — the default
    mesh processor operator and the most general message-passing GNN.

    Works on a SINGLE node set (the mesh) with an optional per-edge attribute
    (here the refinement-level embedding). One layer does, for each node i:

        message:   m_ij    = MLP_edge([h_i, h_j, edge_attr_ij])   # per edge j→i
        aggregate: m_i     = Σ_{j∈N(i)} m_ij                      # sum at i
        update:    h_i_new = LayerNorm( h_i + MLP_node([h_i, m_i]) )

    The residual (h_i + …) and LayerNorm keep an 8-deep stack stable. Input and
    output have the same shape (hidden_dim per node).

    PyG plumbing: subclass MessagePassing(aggr="sum"); calling `self.propagate`
    runs `message()` once per edge and sums the results at each destination node.
    PyG's naming convention inside message(): x_i = destination (receiver), x_j =
    source (sender) features, already gathered per edge.
    """
    def __init__(self, hidden_dim: int, edge_dim: int = 0):
        super().__init__(aggr="sum")                   # step 2: aggregate = sum over neighbours
        edge_in = 2 * hidden_dim + edge_dim            # message input = [h_i, h_j, edge_attr]
        self.edge_mlp = nn.Sequential(                 # the MESSAGE (edge) function
            nn.Linear(edge_in, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.node_mlp = nn.Sequential(                 # the UPDATE (node) function
            nn.Linear(2 * hidden_dim, hidden_dim),     # input = [h_i, aggregated messages m_i]
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.norm = nn.LayerNorm(hidden_dim)

    def message(self, x_i, x_j, edge_attr=None):
        # STEP 1 (per edge): a learned nonlinear function of the RECEIVER (x_i),
        # the SENDER (x_j) and the edge's level descriptor. Depending on both
        # endpoints is what makes this an *Interaction* network (vs. just passing
        # the neighbour's features through).
        if edge_attr is None:
            inp = torch.cat([x_i, x_j], dim=-1)
        else:
            inp = torch.cat([x_i, x_j, edge_attr], dim=-1)
        return self.edge_mlp(inp)

    def forward(self, x, edge_index, edge_attr=None):
        # propagate() runs message() per edge then SUMS messages per node -> m_i.
        agg = self.propagate(edge_index, x=x, edge_attr=edge_attr)   # steps 1+2 -> m_i
        upd = self.node_mlp(torch.cat([x, agg], dim=-1))             # step 3: MLP_node([h_i, m_i])
        return self.norm(x + upd)                                    # residual + LayerNorm


class BipartiteInteraction(MessagePassing):
    """Interaction Network across TWO DIFFERENT node sets (a bipartite graph):
    messages flow source → destination and update ONLY the destination. These
    are the on/off ramps between the grid and the mesh — used twice:

        ENCODER:  source = grid (18k)  →  destination = mesh (~1.8k)   "get on"
        DECODER:  source = mesh        →  destination = grid           "get off"

    Same message → sum → residual-update recipe as InteractionLayer, but sender
    and receiver live in separate tensors, so propagate gets x=(x_src, x_dst).
    No edge_attr here (the grid↔mesh edges are untyped). Returns the updated
    DESTINATION features only.
    """
    def __init__(self, src_dim: int, dst_dim: int, hidden_dim: int):
        super().__init__(aggr="sum", flow="source_to_target")
        self.edge_mlp = nn.Sequential(                 # message from [sender, receiver]
            nn.Linear(src_dim + dst_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.node_mlp = nn.Sequential(                 # update the destination node
            nn.Linear(dst_dim + hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, dst_dim),
        )
        self.norm = nn.LayerNorm(dst_dim)

    def message(self, x_j, x_i):
        # x_j = source-node features (edge tails), x_i = destination (edge heads).
        return self.edge_mlp(torch.cat([x_j, x_i], dim=-1))

    def forward(self, x_src, x_dst, edge_index):
        agg = self.propagate(edge_index, x=(x_src, x_dst))      # messages summed at each dst
        upd = self.node_mlp(torch.cat([x_dst, agg], dim=-1))    # update dst from its own state + agg
        return self.norm(x_dst + upd)                           # residual + LayerNorm on the dst side


# ─────────────────────────────────────────────────────────────────────
#  Alternative processor operators (graph-creation / operator ablation)
# ─────────────────────────────────────────────────────────────────────
# The processor (mesh ↔ mesh message passing) is the one stage we swap to
# isolate the *operator* from the *graph*. `interaction` is the GraphCast
# default; `sage`/`gat`/`diffusion` reproduce the GraphSAGE / GAT / DCRNN
# operators from the legacy SLIC project, so the same operator can be run on
# either the icosahedral mesh or the SLIC super-pixel graph (via --bundle).
class _DConvBlock(nn.Module):
    """DCRNN diffusion convolution (Li et al., 2018) as a residual processor block:
        h <- LayerNorm(h + SiLU(DConv(h))).
    Uses the EXACT diffusion conv from torch_geometric_temporal — the operator
    the legacy DCRNN model was built on — i.e. K-step bidirectional random-walk
    diffusion. Edge-structure only (unit edge weights; the full DCRNN's temporal
    GRU recurrence is supplied separately by the `_ar` decoder). DConv is imported
    lazily, so torch_geometric_temporal is needed only when this operator is
    selected (sage/gat/interaction stay dependency-light)."""
    def __init__(self, hidden_dim: int, K: int = 2):
        super().__init__()
        try:
            from torch_geometric_temporal.nn.recurrent.dcrnn import DConv
        except Exception as e:                                  # pragma: no cover
            raise ImportError(
                "--processor diffusion/dcrnn needs torch_geometric_temporal "
                "(pip install torch-geometric-temporal)."
            ) from e
        self.dconv = DConv(hidden_dim, hidden_dim, K=K)
        self.act = nn.SiLU()
        self.norm = nn.LayerNorm(hidden_dim)

    def forward(self, x, edge_index, edge_attr=None):
        # DConv normalises by node degree (bidirectional random walk), so any
        # zero-degree node -> reciprocal(0)=inf -> NaN. The icosahedral mesh has
        # sink/source nodes (80 with zero out-degree), so add self-loops to
        # guarantee degree >= 1. Also dedup (DConv round-trips through a dense
        # adjacency and needs a duplicate-free, unit-weight edge set).
        n = x.size(0)
        loops = torch.arange(n, device=x.device).unsqueeze(0).expand(2, -1)
        ei = torch.unique(torch.cat([edge_index, loops], dim=1), dim=1)
        ew = torch.ones(ei.size(1), device=x.device, dtype=x.dtype)
        return self.norm(x + self.act(self.dconv(x, ei, ew)))


class _ResidualConvBlock(nn.Module):
    """Wrap a bare PyG conv as a residual processor block —
        h <- LayerNorm(h + SiLU(conv(h, edge_index[, edge_attr]))) —
    so SAGE / GAT / diffusion share InteractionLayer's residual+norm scaffolding.
    Processor depth and stabilisation are thus held constant across operators;
    only the message/aggregation core changes (that is exactly the ablation)."""
    def __init__(self, conv: nn.Module, hidden_dim: int, uses_edge_attr: bool):
        super().__init__()
        self.conv = conv
        self.uses_edge_attr = uses_edge_attr
        self.act = nn.SiLU()
        self.norm = nn.LayerNorm(hidden_dim)

    def forward(self, x, edge_index, edge_attr=None):
        m = (self.conv(x, edge_index, edge_attr) if self.uses_edge_attr
             else self.conv(x, edge_index))
        return self.norm(x + self.act(m))


PROCESSOR_OPS = ("interaction", "sage", "gat", "diffusion", "dcrnn")


def make_processor(processor: str, n_layers: int, hidden_dim: int) -> nn.ModuleList:
    """Build the mesh processor as `n_layers` blocks of the chosen operator.

    `interaction` (default) is the GraphCast edge-aware Interaction Network and
    is kept BYTE-IDENTICAL to the original so existing checkpoints still load.
    The alternatives wrap a bare PyG conv in `_ResidualConvBlock`:
      `sage`            GraphSAGE (mean aggr; edge-unaware)
      `gat`             GAT (4 concatenated heads, as DeepGAT; edge-aware via level embed)
      `diffusion`/`dcrnn`  DCRNN diffusion conv (torch_geometric_temporal DConv,
                        K=2; edge-unaware) — see `_DConvBlock`
    """
    p = processor.lower()
    if p == "interaction":
        return nn.ModuleList([InteractionLayer(hidden_dim, edge_dim=hidden_dim)
                              for _ in range(n_layers)])
    if p == "sage":
        return nn.ModuleList([_ResidualConvBlock(
            SAGEConv(hidden_dim, hidden_dim, aggr="mean"),
            hidden_dim, uses_edge_attr=False) for _ in range(n_layers)])
    if p == "gat":
        heads = 4
        assert hidden_dim % heads == 0, f"hidden_dim {hidden_dim} must be divisible by heads {heads}"
        # Concatenated heads (out=hidden_dim//heads per head -> hidden_dim total), as in
        # the legacy DeepGAT — ~4x lighter than averaging full-width heads (concat=False).
        return nn.ModuleList([_ResidualConvBlock(
            GATConv(hidden_dim, hidden_dim // heads, heads=heads, concat=True,
                    edge_dim=hidden_dim, add_self_loops=False),
            hidden_dim, uses_edge_attr=True) for _ in range(n_layers)])
    if p in ("diffusion", "dcrnn"):
        return nn.ModuleList([_DConvBlock(hidden_dim, K=2) for _ in range(n_layers)])
    raise ValueError(f"Unknown processor {processor!r}. Choose from {PROCESSOR_OPS}.")


# ─────────────────────────────────────────────────────────────────────
#  Multi-mesh GNN
# ─────────────────────────────────────────────────────────────────────
class MultiMeshGNN(nn.Module):
    """GraphCast-style multi-mesh GNN (encoder → processor → decoder over a grid
    and a coarse icosahedral mesh). See the module docstring at the top of this
    file for the full conceptual walkthrough; `forward()` is the 7-step pipeline.

    Args
    ----
    in_channels  : grid input feature dim (default 40 = 10 features × 4 weeks).
    out_channels : forecast horizon (default 8 weeks).
    hidden_dim   : internal feature width (default 128).
    n_processor_layers : number of mesh ↔ mesh message-passing rounds (default 8).
    bundle_path  : path to the mesh graph `*.npz`. Auto-detected if None
                   (multi_mesh_bundle.npz; pass slic_bundle.npz for the SLIC graph).
    output_activation : "sigmoid" for SIC (target in [0,1]) or "linear" for SICA.
    processor    : which operator the processor uses — one of PROCESSOR_OPS
                   ("interaction" default | "sage" | "gat" | "diffusion"/"dcrnn").
                   This is the lever the operator ablation turns; see make_processor.
    """
    def __init__(
        self,
        in_channels: int = 40,
        out_channels: int = 8,
        hidden_dim: int = 128,
        n_processor_layers: int = 8,
        bundle_path: Optional[str] = None,
        output_activation: str = "sigmoid",
        processor: str = "interaction",
    ):
        super().__init__()

        # Output activation: sigmoid for SIC ([0,1]); identity for SICA (signed anomaly).
        # Subclasses inherit this attribute via super().__init__() and use it in their forward.
        self.out_act = _make_output_activation(output_activation)

        if bundle_path is None:
            bundle_path = _find_bundle()
        bundle = np.load(bundle_path)

        # The mesh graph (see the module docstring). Each edge set is (2, n_edges)
        # with row 0 = source node id, row 1 = destination node id:
        #   encoder_edges : grid → mesh  (load data onto the mesh)
        #   mm_edges      : mesh ↔ mesh  (the processor's wiring; stored ONCE per
        #                   pair in a single orientation — directed, not symmetrised)
        #   decoder_edges : mesh → grid  (write the mesh state back to the grid)
        #   mm_levels     : per mesh-edge refinement level 0..K (0=coarse/long,
        #                   K=fine/short); turned into edge_attr via level_embed.
        encoder_edges = torch.from_numpy(bundle["encoder_edges"]).long()         # (2, n_enc)
        mesh_edges    = torch.from_numpy(bundle["mm_edges"]).long().T            # (2, n_mesh_e)
        decoder_edges = torch.from_numpy(bundle["decoder_edges"]).long()         # (2, n_dec)
        mesh_levels   = torch.from_numpy(bundle["mm_levels"]).long()             # (n_mesh_e,)
        self.register_buffer("_encoder_edges", encoder_edges)
        self.register_buffer("_mesh_edges",    mesh_edges)
        self.register_buffer("_decoder_edges", decoder_edges)
        self.register_buffer("_mesh_levels",   mesh_levels)

        self.n_grid   = int(bundle["grid_lat"].shape[0])
        self.n_mesh   = int(bundle["mesh_lat"].shape[0])
        self.n_levels = int(bundle["K"]) + 1
        self.graph_tag = _graph_tag_from_bundle(bundle)   # e.g. mesh_K5 / slic_n1800_L4
        self.in_channels  = in_channels
        self.out_channels = out_channels
        self.hidden_dim   = hidden_dim

        print(
            f"MultiMeshGNN[{self.graph_tag}]: grid={self.n_grid}  mesh={self.n_mesh}  "
            f"enc={encoder_edges.shape[1]}  mesh_edges={mesh_edges.shape[1]}  "
            f"dec={decoder_edges.shape[1]}  levels={self.n_levels}"
        )

        # ── Embeddings ────────────────────────────────────────────────
        self.grid_embed = nn.Sequential(
            nn.Linear(in_channels, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        # Learnable per-mesh-node initial features. Small init so the
        # encoder dominates on the first forward pass and the mesh state
        # has a chance to be informed by the inputs.
        self.mesh_init = nn.Parameter(torch.randn(self.n_mesh, hidden_dim) * 0.01)
        # Edge-type embedding for the processor (one vector per refinement level).
        self.level_embed = nn.Embedding(self.n_levels, hidden_dim)

        # ── Encoder / Processor / Decoder ─────────────────────────────
        self.encoder = BipartiteInteraction(hidden_dim, hidden_dim, hidden_dim)
        # Processor operator is swappable for the ablation (interaction default
        # is byte-identical to before, so old checkpoints still load).
        self.processor_kind = processor
        self.processor = make_processor(processor, n_processor_layers, hidden_dim)
        print(f"  processor: {processor} × {n_processor_layers}")
        self.decoder = BipartiteInteraction(hidden_dim, hidden_dim, hidden_dim)

        # ── Readout ───────────────────────────────────────────────────
        # Concat decoded grid features with raw input (residual skip).
        self.readout = nn.Sequential(
            nn.Linear(hidden_dim + in_channels, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, out_channels),
        )

    # ─────────────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _batch_edges(edges: torch.Tensor, B: int,
                     n_src_per_graph: int, n_dst_per_graph: int) -> torch.Tensor:
        """Replicate a (2, n_edges) edge_index B times with per-graph offsets."""
        if B == 1:
            return edges
        device  = edges.device
        n_edges = edges.shape[1]
        bid     = torch.arange(B, device=device).repeat_interleave(n_edges)
        src     = edges[0].repeat(B) + bid * n_src_per_graph
        dst     = edges[1].repeat(B) + bid * n_dst_per_graph
        return torch.stack([src, dst])

    # ─────────────────────────────────────────────────────────────────
    #  Forward
    # ─────────────────────────────────────────────────────────────────
    def forward(self, x, edge_index=None):
        """x: (B*N_grid, in_channels). edge_index is ignored (model holds its own)."""
        # 0. Infer batch size from x.
        assert x.shape[0] % self.n_grid == 0, (
            f"x has {x.shape[0]} nodes, not a multiple of n_grid={self.n_grid}. "
            f"Did the dataloader change?"
        )
        B = x.shape[0] // self.n_grid

        # 1. Embed grid features.
        h_grid = self.grid_embed(x)                                              # (B*N_grid, H)

        # 2. Initialise mesh features, tiled across the batch.
        h_mesh = self.mesh_init.unsqueeze(0).expand(B, -1, -1).reshape(B * self.n_mesh, -1)

        # 3. Build batched edges + edge attributes for the processor.
        enc  = self._batch_edges(self._encoder_edges, B, self.n_grid, self.n_mesh)
        mp   = self._batch_edges(self._mesh_edges,    B, self.n_mesh, self.n_mesh)
        dec  = self._batch_edges(self._decoder_edges, B, self.n_mesh, self.n_grid)
        # Mesh-level edge embeddings tile B times as well.
        edge_attr = self.level_embed(self._mesh_levels).repeat(B, 1)             # (B*n_mesh_e, H)

        # 4. Encoder — grid features push into mesh nodes.
        h_mesh = self.encoder(h_grid, h_mesh, enc)

        # 5. Processor — many rounds of mesh ↔ mesh message passing.
        for layer in self.processor:
            h_mesh = layer(h_mesh, mp, edge_attr=edge_attr)

        # 6. Decoder — mesh features broadcast back to grid nodes.
        h_grid_decoded = self.decoder(h_mesh, h_grid, dec)

        # 7. Readout with a skip connection to the raw input.
        out = self.readout(torch.cat([h_grid_decoded, x], dim=-1))
        return self.out_act(out)
