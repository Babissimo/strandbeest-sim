# Strandbeest simulator

A browser simulator for the Evolving Machines course: four-bar linkages, a Jansen leg playground,
a genetic algorithm that evolves whole Strandbeests, and an arena where a beest walks under
physics. Python runs in the page through PyScript; there is no backend.

```bash
uv run scripts/vendor.py   # fetch the pinned PyScript, Pyodide and pymunk into site/vendor/
uv run scripts/serve.py    # serve site/ at http://127.0.0.1:8000
```

Requirements are in [docs/brief.md](docs/brief.md), open design decisions in
[docs/decisions.md](docs/decisions.md), and the build plan in
[docs/superpowers/plans/](docs/superpowers/plans/).
