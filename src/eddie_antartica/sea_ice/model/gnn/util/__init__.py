"""
util — shared utilities for the SIC digital twin (data preparation + inference).

This package is a frozen, INFERENCE-ONLY copy of the research project's `util/`.
Three modules:

  config       Constants that define the data/model shape — grid size (50x360),
               input channels (40 = 10 vars x 4 lookback weeks), forecast horizon
               (8 weeks), temporal resolution ("weekly"), and the target label.
               Single source of truth, imported by the model and data code.

  data_loader  NetCDF loading, feature scaling, and sliding-window construction.
               The PRODUCTION / live path uses only:
                   load_train_stats(...)   - load the frozen training-era scaler
                   prepare_live_window(...) - build the latest input window
                   CustomScaler            - the scaler object
               prepare_sic_data(...) / make_loader(...) are used by the
               validation-split notebook; the rest (SICGraphDataset, the split
               helpers, dynamic_ice_mask) are inherited from the research pipeline.

  inference    The metric-free forward core:
                   run_inference(...)   - a whole split -> predictions
                   predict_latest(...)  - one operational window -> 8-week forecast
                   plot_forecast(...)   - render the forecast maps

See ../../README.md for the end-to-end deployment workflow.
"""
