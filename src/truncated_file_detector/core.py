"""Core logic for detecting truncated files.

A file is considered *truncated* when its actual byte size on disk is smaller
than the size declared in a companion manifest. The manifest is a plain JSON
object mapping file paths (relative or absolute) to their expected byte sizes.

Design decisions
----------------
* Manifest values must be non-negative integers. A negative or non-integer
  value is a *malformed manifest*, not a truncation, so we raise
  ``ValueError`` rather than silently treating it as zero.
* Missing files are reported as truncated (actual size 0 < declared size).
  If a file genuinely does not exist that is a data-loss condition worth
  surfacing.
* Files whose actual size *exceeds* the declared size are not flagged here.
  Growing a file is a different problem (possible corruption) and mixing the
  two would make the result ambiguous.
* Result type is a lightweight ``TruncationResult`` (a ``namedtuple``) so it
  is immutable, self-documenting, and cheap to construct — callers may build
  thousands of these in a batch run.
"""

from __future__ import annotations

import json
import os
from collections import namedtuple
from typing import Dict, Iterable, List, Union

__all__ = ["TruncationResult", "detect_truncation"]

#: Immutable record describing one file's truncation status.
TruncationResult = namedtuple(
    "_TruncationResult",
    ["path", "declared_size", "actual_size", "is_truncated"],
)


def _load_manifest(manifest: Union[str, os.PathLike, Dict[str, int]]) -> Dict[str, int]:
    """Return a normalised ``{path: size}`` dict from *manifest*.

    *manifest* may be a path to a JSON file or an already-parsed dict. Keeping
    both supported means the library is usable in-process (manifest produced
    by another component) and from disk without the caller doing extra work.
    """
    if isinstance(manifest, dict):
        return manifest

    with open(manifest, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, dict):
        raise ValueError(
            "Manifest root must be a JSON object mapping paths to sizes; "
            "got {0}".format(type(data).__name__)
        )
    return data


def _validate_size(path: str, size: object) -> int:
    """Coerce and validate a declared size value.

    JSON numbers arrive as ``int`` or ``float``. We accept ``int`` and
    whole-number ``float`` (e.g. ``1024.0``) for ergonomics, but reject
    anything else loudly so callers find manifest typos immediately.
    """
    if isinstance(size, bool):
        # bool is a subclass of int in Python — guard explicitly so
        # ``true``/``false`` in the manifest are not silently accepted.
        raise ValueError(
            "Declared size for {0!r} must be an integer, got bool".format(path)
        )
    if isinstance(size, float):
        if not size.is_integer():
            raise ValueError(
                "Declared size for {0!r} must be an integer, got {1}".format(path, size)
            )
        size = int(size)
    if not isinstance(size, int):
        raise ValueError(
            "Declared size for {0!r} must be an integer, got {1}".format(
                path, type(size).__name__
            )
        )
    if size < 0:
        raise ValueError(
            "Declared size for {0!r} must be non-negative, got {1}".format(path, size)
        )
    return size


def _actual_size(path: str) -> int:
    """Return the byte size of *path* on disk, or 0 if it is absent.

    We deliberately do **not** follow symlinks: a broken symlink is reported
    as size 0, which in turn surfaces as truncated when the declared size is
    non-zero.
    """
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def detect_truncation(
    manifest: Union[str, os.PathLike, Dict[str, int]],
    base_dir: Union[str, os.PathLike, None] = None,
) -> List[TruncationResult]:
    """Detect files whose on-disk size is smaller than declared.

    Parameters
    ----------
    manifest:
        Either a path to a JSON manifest file or a pre-parsed ``{path: size}``
        dictionary. Keys are interpreted as paths relative to *base_dir*;
        absolute keys ignore *base_dir*.
    base_dir:
        Directory to resolve relative manifest keys against. If ``None``,
        relative keys are resolved against the current working directory.

    Returns
    -------
    list[TruncationResult]
        One result per manifest entry, in insertion order. Each result has
        ``path``, ``declared_size``, ``actual_size``, and ``is_truncated``
        fields. ``is_truncated`` is ``True`` when ``actual_size <
        declared_size``.

    Raises
    ------
    ValueError:
        If the manifest is structurally invalid or contains a non-integer or
        negative size.
    """
    raw = _load_manifest(manifest)
    results: List[TruncationResult] = []

    for path, raw_size in raw.items():
        declared = _validate_size(path, raw_size)
        resolved = path if os.path.isabs(path) else os.path.join(
            base_dir or os.curdir, path
        )
        actual = _actual_size(resolved)
        results.append(
            TruncationResult(
                path=path,
                declared_size=declared,
                actual_size=actual,
                is_truncated=actual < declared,
            )
        )

    return results
