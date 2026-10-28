"""
The sea ice GNN, copied from the reference code (util/ and models/) on 8/10/26.

@author: tobi-milz

Attribution: the model, its training and all code in this folder are Tobi's work. Only the import lines
were changed, to fit this package.

Same layout as the reference code (util/, models/), so `diff -r` against it shows exactly what differs.

Excluded from flake8 and pylint (.flake8, .pylintrc) on purpose: this is reference code kept as written,
so it can be diffed against and refreshed from its source. Making it pass this repo's docstring and
type-annotation rules would rewrite most of its lines and lose that. Run by model.sic_gnn_model.
"""
