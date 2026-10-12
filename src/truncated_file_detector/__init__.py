"""Package entry point for truncated_file_detector.

Re-exports the public API so users can write::

    from truncated_file_detector import TruncationResult, detect_truncation

rather than reaching into internal modules.
"""

from .core import TruncationResult, detect_truncation

__all__ = ["TruncationResult", "detect_truncation"]
