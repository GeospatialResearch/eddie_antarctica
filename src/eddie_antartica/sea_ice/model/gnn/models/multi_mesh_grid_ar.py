"""
multi_mesh_grid_ar.py — MultiMeshGNN + grid-local message passing + GRU rollout.

The "best of both" variant: it combines the two independent levers we tested
separately —

  * grid-local message passing (from multi_mesh_grid): n_grid_pre lattice
    InteractionLayers before the encoder and n_grid_post after the decoder,
    giving CNN-like local spatial detail at the ice edge; and
  * latent-rollout decoder (from multi_mesh_ar): a shared GRU cell evolves the
    per-node latent forward one week at a time, decoding SIC each step, for
    temporal/long-lead dynamics with no future forcing needed.

Data flow:
    grid_embed(x)
      -> n_grid_pre  x InteractionLayer   (grid<->grid, local context in)
      -> encoder (grid->mesh) -> processor (mesh) -> decoder (mesh->grid)
      -> n_grid_post x InteractionLayer   (grid<->grid, sharpen output)
      -> ctx = proj([h_grid, x]);  h=ctx;  for k: h=GRU(ctx,h); SIC_k=head(h)
      -> sigmoid

Same I/O contract: forward(x, edge_index) -> (N, out_channels) in [0,1].

*** THIS is the DEPLOYED model *** (weights = data/SIC_production_checkpoint.pt).
Production usage: construct it with the checkpoint's config, load_state_dict, then
call forward on a (N_nodes, 40) window. See models/__init__.py for the snippet and
util/inference.py::predict_latest for the operational single-window wrapper.
"""

import torch
import torch.nn as nn

from util.config import N_LAT, N_LON
from models.multi_mesh_grid import MultiMeshGridGNN


class MultiMeshGridARGNN(MultiMeshGridGNN):
    """Grid-local message passing (inherited) + GRU latent-rollout decoder."""

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
        # Builds grid lattice edges + grid_pre/grid_post (from the grid variant).
        super().__init__(in_channels, out_channels, hidden_dim, n_processor_layers,
                         n_grid_pre, n_grid_post, connectivity, n_lat, n_lon, bundle_path,
                         output_activation=output_activation,
                         processor=processor)

        # Latent-rollout decoder (from the AR variant); replaces the base readout.
        self.ctx_proj = nn.Sequential(
            nn.Linear(hidden_dim + in_channels, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.step = nn.GRUCell(hidden_dim, hidden_dim)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, 1),
        )
        print(f"  + latent-rollout decoder: GRUCell({hidden_dim}) x {out_channels} steps")

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

        # Mesh init + batched edges (as in the base model).
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

        # Local post-processing (sharpen).
        for layer in self.grid_post:
            h_grid = layer(h_grid, grid_e)

        # Latent rollout: evolve the per-node state H times, decode each step.
        ctx = self.ctx_proj(torch.cat([h_grid, x], dim=-1))
        h = ctx
        outs = []
        for _ in range(self.out_channels):
            h = self.step(ctx, h)
            outs.append(self.head(h))
        return self.out_act(torch.cat(outs, dim=-1))
