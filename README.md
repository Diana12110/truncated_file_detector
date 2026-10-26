# truncated_file_detector

Identifies files whose actual byte size is smaller than a declared size in a companion manifest.

## Usage

```python
from truncated_file_detector import TruncationResult, detect_truncation

results = detect_truncation(
    manifest={"data/important.bin": 4096},
    base_dir="/path/to/project",
)

for r in results:
    if r.is_truncated:
        print(f"{r.path}: declared {r.declared_size}, actual {r.actual_size}")
```

`manifest` can be a path to a JSON file or a pre-parsed `{path: size}` dict.
`base_dir` resolves relative keys; absolute keys ignore it. Each result is a
`TruncationResult` namedtuple with `path`, `declared_size`, `actual_size`, and
`is_truncated`.

## Why

In pipelines that stage files alongside a manifest — build artifacts, dataset
shards, backup payloads — a file can be partially written and silently shipped
onward. Checking declared vs. actual size before downstream consumption catches
the most common failure without reading file contents, which matters when files
are large.

The trade-off: this only catches truncation, not corruption of equal size or
files larger than declared. Those are different problems; mixing them makes the
result ambiguous.

## Edge case

A missing file is reported as truncated (actual size 0). If your pipeline
treats "absent" and "partial" differently, filter on `actual_size == 0`.

Manifest sizes must be non-negative integers. `4.0` (whole-number float) is
accepted; `4.5`, `true`, and `-1` raise `ValueError` immediately so bad
manifests surface before any disk check.

## Run tests

```sh
PYTHONPATH=src python -m unittest discover -s tests
```

Zero third-party dependencies. Standard library only.

## Performance

The window keeps a bounded buffer, so `push` is constant time and memory does not
grow with the length of the stream. `peak` and `trough` are linear in the window
size, which is the trade that keeps `push` cheap.

## Design notes

The window stores values eagerly rather than keeping running aggregates. Running
sums drift with floating point over long streams, and recomputing from a small
buffer is cheap enough that the drift is not worth the speed.

