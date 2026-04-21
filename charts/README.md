# Charts

Source and rendered charts used in the project README and docs.

- `src/` — Mermaid source (`.mmd`). These are the editable definitions.
- `rendered/` — Rasterized output (`.png`, `.svg`). These are what the
  README actually embeds, so the diagrams display without requiring
  Mermaid support in the viewer.

## Regenerating

```bash
just charts
```

Or directly:

```bash
npx -y @mermaid-js/mermaid-cli \
    -i charts/src/<name>.mmd \
    -o charts/rendered/<name>.png \
    -w 1200 -b transparent
```

Keep `.mmd` sources and rendered outputs in sync — the README links
into `rendered/`, not `src/`.
