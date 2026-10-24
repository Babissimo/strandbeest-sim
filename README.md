# Strandbeest simulator

A browser simulator for the Evolving Machines course: four-bar linkages, a Jansen leg playground,
a genetic algorithm that evolves whole Strandbeests, and an arena where a beest walks under
physics. Python runs in the page through PyScript; there is no backend. It is at
<https://strandbeests.babissimo.net>.

```bash
uv run scripts/vendor.py   # fetch the pinned PyScript, Pyodide and pymunk into site/vendor/
uv run scripts/serve.py    # serve site/ at http://127.0.0.1:8000
```

## Hosting

A Cloudflare Worker with no script serves `site/` as static files, with the headers in
`site/_headers`, as Ratchet's site is served. Its configuration is `deploy/wrangler.jsonc`, with
wrangler pinned in `deploy/package.json`. A push to `main` that changes what is served runs
`.github/workflows/deploy.yml`, which fetches the runtime and deploys; a pull request that could
change it gets a dry run, which fails on a file over Cloudflare's 25 MiB limit. To redeploy `main`
without a change, run the workflow from the Actions tab.

The deploy reads one repository secret, `CLOUDFLARE_API_TOKEN`. Make it under Account API tokens
in the Cloudflare dashboard from the "Edit Cloudflare Workers" template, scoped to this account and
the `babissimo.net` zone, then store it with:

```bash
gh secret set CLOUDFLARE_API_TOKEN -R Babissimo/strandbeest-sim
```

The first deploy creates the `strandbeests.babissimo.net` DNS record and certificate. To try
Cloudflare's own file server on the vendored site, run `npm ci` and then `npx wrangler dev` in
`deploy/`, which serves it at http://127.0.0.1:8787.

Requirements are in [docs/brief.md](docs/brief.md), open design decisions in
[docs/decisions.md](docs/decisions.md), and the build plan in
[docs/superpowers/plans/](docs/superpowers/plans/).
