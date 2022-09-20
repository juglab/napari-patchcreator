try:
    from ._version import version as __version__
except ImportError:
    __version__ = "unknown"
from ._patch_widget import PatchWidget

__all__ = ("PatchWidget",)
