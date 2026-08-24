"""Build the C Warnsdorff DFS extension (production)."""
from setuptools import Extension, setup

setup(
    name="hampath-dfs-native",
    version="0.1.0",
    description="Native C Warnsdorff DFS for hampath",
    ext_modules=[
        Extension(
            "warnsdorff_c",
            sources=["warnsdorff_cmodule.c", "warnsdorff_dfs_c.c"],
            include_dirs=["."],
        )
    ],
    zip_safe=False,
)
