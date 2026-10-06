"""Local Scribe application package."""

from . import winlibs as _winlibs

# Must run before anything imports ctranslate2 or onnxruntime, so their
# native libraries can find cuBLAS/cuDNN and the Visual C++ runtime on
# Windows. A no-op on every other platform.
_winlibs.prepare()
