"""Output module init."""

from codereview.output.generator import OutputGenerator
from codereview.output.inline import InlineCommentBuilder

__all__ = ["InlineCommentBuilder", "OutputGenerator"]
