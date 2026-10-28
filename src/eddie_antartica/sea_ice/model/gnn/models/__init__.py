"""
models — the deployed GNN (GraphCast-style multi-mesh) for SIC forecasting.

Inheritance chain (ONLY the last class is instantiated at runtime; each builds on
the one above it):

    MultiMeshGNN              multi_mesh.py           encode-process-decode over the
                                                      18,000-node grid + a ~1,800-node
                                                      icosahedral mesh (long-range mixing)
      +-- MultiMeshGridGNN    multi_mesh_grid.py      adds grid-local lattice message
                                                      passing (sharper ice edge)
            +-- MultiMeshGridARGNN  multi_mesh_grid_ar.py   adds a GRU rollout decoder
                                                            <-- THE DEPLOYED MODEL

Runtime usage (see util/inference.py and the notebooks):

    model = MultiMeshGridARGNN(
        in_channels=40, out_channels=8, output_activation="sigmoid",
        bundle_path=".../multi_mesh_bundle_K5.npz", processor="interaction")
    model.load_state_dict(checkpoint["model_state_dict"])
    forecast = model(x, edge_index)          # x: (N_nodes, 40) -> (N_nodes, 8) in [0,1]

The model carries its own mesh edges (from the bundle) and IGNORES `edge_index`.
Everything else in these files — the sage/gat/diffusion processor variants in
`make_processor`, and the `graph_tag`/`build_run_name`/`resolve_bundle_path`
helpers — is build- and ablation-time machinery from the research project, NOT
exercised by the live forward pass.

`multi_mesh.py` opens with a detailed, plain-language walkthrough of the
architecture — read that first.
"""
