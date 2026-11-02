"""Imported first by the package: one OpenBLAS thread unless the user set OPENBLAS_NUM_THREADS. tune barely uses BLAS
(a small solve for natural voices, CLAP), while every idle OpenBLAS thread reserves its own buffer: about 450 MB of
commit per process on an 8-core Windows machine, times each bake worker. No effect when numpy was imported first."""
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
