"""
multi_mesh_grid.py — MultiMeshGNN + grid-local message passing.

The base MultiMeshGNN (GraphCast-style) routes ALL spatial information through
the coarse icosahedral mesh: grid -> mesh -> processor -> mesh -> grid. Grid
nodes never exchange information with their lattice neighbours, so fine local
structure (the ice edge) gets smeared by the ~1.8k-node mesh bottleneck — which
is where the model trails the CNNs on RMSE / ice-masked RMSE.

This variant adds **grid-local message passing** (8-connectivity lattice among
the 18,000 grid nodes) at the two full-resolution points, mirroring a U-Net's
local convolutions on the contracting and expanding paths:

    grid_embed(x)
       │
       ├─ n_grid_pre  x InteractionLayer  (grid<->grid)   <- local context in
       ▼
    encoder (grid->mesh) -> processor (mesh) -> decoder (mesh->grid)
       │   (decoder residual on h_grid acts as a U-Net skip for the pre features)
       ├─ n_grid_post x InteractionLayer  (grid<->grid)   <- sharpen output
       ▼
    readout([h_grid, x]) -> sigmoid

The lattice edges are built internally from (n_lat, n_lon) via
`util.data_loader._grid_adjacency_edges`, so there's no dependency on the
super-pixel `.npy` files (keeps the pod deploy self-contained). Set
`n_grid_pre`/`n_grid_post` to 0 to ablate either side.

Deployment: this is the MIDDLE link of the chain (MultiMeshGNN <- MultiMeshGridGNN
<- MultiMeshGridARGNN). It is not instantiated directly in production — the
deployed `MultiMeshGridARGNN` inherits from it.
"""

import numpy as np
import torch
import torch.nn as nn

from util.config import N_LAT, N_LON
from util.data_loader import _grid_adjacency_edges
from models.multi_mesh import MultiMeshGNN, InteractionLayer


class MultiMeshGridGNN(MultiMeshGNN):
    """MultiMeshGNN with grid-local InteractionLayers before the encoder and
    after the decoder. Same I/O contract: forward(x, edge_index) -> (N, out) in [0,1]."""

    def __init__(
        self,
        in_channels: int = 40,
        out_channels: int = 8,
        hidden_dim: int = 128,
        n_processor_layers: int = 8,
        n_grid_pre: int = 2,
        n_grid_post: int = 2,
        connectivity: int = 8,
        n_lat: int = N_LAT,
        n_lon: int = N_LON,
        bundle_path=None,
        output_activation: str = "sigmoid",
        processor: str = "interaction",
    ):
        super().__init__(in_channels, out_channels, hidden_dim,
                         n_processor_layers, bundle_path,
                         output_activation=output_activation,
                         processor=processor)
        assert n_lat * n_lon == self.n_grid, (
            f"n_lat*n_lon ({n_lat*n_lon}) != n_grid ({self.n_grid}) from the bundle"
        )

        # Lattice edges among grid nodes (row-major node ids), built internally.
        grid_edges = torch.from_numpy(
            _grid_adjacency_edges(n_lat, n_lon, connectivity=connectivity)
        ).long()                                              # (2, n_grid_edges)
        self.register_buffer("_grid_edges", grid_edges)

        self.grid_pre  = nn.ModuleList([InteractionLayer(hidden_dim) for _ in range(n_grid_pre)])
        self.grid_post = nn.ModuleList([InteractionLayer(hidden_dim) for _ in range(n_grid_post)])

        print(f"  + grid-local: {grid_edges.shape[1]} lattice edges "
              f"({connectivity}-conn)  pre={n_grid_pre}  post={n_grid_post}")

    def forward(self, x, edge_index=None):
        """x: (B*N_grid, in_channels). edge_index ignored (model holds its own)."""
        assert x.shape[0] % self.n_grid == 0, (
            f"x has {x.shape[0]} nodes, not a multiple of n_grid={self.n_grid}."
        )
        B = x.shape[0] // self.n_grid

        # Grid embedding + local pre-processing.
        h_grid = self.grid_embed(x)
        grid_e = self._batch_edges(self._grid_edges, B, self.n_grid, self.n_grid)
        for layer in self.grid_pre:
            h_grid = layer(h_grid, grid_e)

        # Mesh init + batched mesh/encoder/decoder edges (as in the base model).
        h_mesh = self.mesh_init.unsqueeze(0).expand(B, -1, -1).reshape(B * self.n_mesh, -1)
        enc = self._batch_edges(self._encoder_edges, B, self.n_grid, self.n_mesh)
        mp  = self._batch_edges(self._mesh_edges,    B, self.n_mesh, self.n_mesh)
        dec = self._batch_edges(self._decoder_edges, B, self.n_mesh, self.n_grid)
        edge_attr = self.level_embed(self._mesh_levels).repeat(B, 1)

        # Encoder -> processor -> decoder (decoder residual on h_grid = U-Net skip).
        h_mesh = self.encoder(h_grid, h_mesh, enc)
        for layer in self.processor:
            h_mesh = layer(h_mesh, mp, edge_attr=edge_attr)
        h_grid = self.decoder(h_mesh, h_grid, dec)

        # Local post-processing (sharpen) + readout with raw-input skip.
        for layer in self.grid_post:
            h_grid = layer(h_grid, grid_e)
        out = self.readout(torch.cat([h_grid, x], dim=-1))
        return self.out_act(out)
