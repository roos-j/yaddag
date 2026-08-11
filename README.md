## Yet Another Dependency DAG

**(This is work in progress)**

This is a Python package inspired by [plastexdepgraph](https://github.com/PatrickMassot/plastexdepgraph) for creating rich explorable dependency graphs from LaTeX documents.
It will also read and display Lean formalization metadata in the format of [leanblueprint](https://github.com/PatrickMassot/leanblueprint).
This code has been developed through extended back and forth with Codex.

## Installation

Install directly from a checkout:

```bash
python -m pip install .
```

For development, install an editable copy instead:

```bash
python -m pip install -e .
```

This installs two commands:

```bash
yaddag-extract blueprint.tex graph.json --strict
yaddag-number-labels blueprint.tex label-numbers.json
yaddag-render graph.json dependency-graph.html
```

The extractor works directly from the source `.tex` file. The renderer requires
Graphviz's `dot` and `neato` executables and a local MathJax
`tex-svg-full.js` bundle; pass its location with `--mathjax-js` when it is not in
one of the renderer's default locations.

`yaddag-number-labels` writes the local label-to-number mapping used by the
extractor. It supports standard heading counters, basic `\newtheorem`
declarations, section-based theorem numbering, and shared theorem counters.

## System dependencies (Linux)

On Debian and Ubuntu, install the renderer's system tools with:

```bash
sudo apt update
sudo apt install -y graphviz nodejs npm
```

Install the MathJax 3 bundle outside the repository, then pass its location to
the renderer:

```bash
npm install --prefix "$HOME/.local/share/yaddag" mathjax-full@3
export MATHJAX_JS="$HOME/.local/share/yaddag/node_modules/mathjax-full/es5/tex-svg-full.js"

yaddag-render graph.json dependency-graph.html --mathjax-js "$MATHJAX_JS"
```

The optional JSON Schema validation command requires one Python library:

```bash
python -m pip install jsonschema
```

Check that the external commands are available with `dot -V` and `neato -V`.

## GitHub Actions

[`render-dependency-graph.yml`](.github/workflows/render-dependency-graph.yml)
can be run manually for a TeX file in this repository. It renders the requested
HTML file, makes a UTC-timestamped copy, and uploads both files as an artifact.

It can also be called from another repository. Pin `yaddag_ref` to a release tag
or commit SHA:

```yaml
jobs:
  render-graph:
    uses: OWNER/yaddag/.github/workflows/render-dependency-graph.yml@v0.1.0
    with:
      yaddag_repository: OWNER/yaddag
      yaddag_ref: v0.1.0
      tex_file: blueprint.tex
      html_file: output/dependency-graph.html
```

For a private YADDAG repository, pass a read token as the workflow's
`yaddag_read_token` secret.
