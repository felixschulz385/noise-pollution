"""Noise barrier data pipeline.

FDOT statewide noise-barrier inventory, distributed as a zipped Esri File
Geodatabase through the Florida Geographic Data Library (FGDL), maintained by
the University of Florida GeoPlan Center. Public download, no authentication.

Stages:

* ``fetch`` (:mod:`.fetch`) — download one FGDL release, extract its ``.gdb``
  and metadata XML into ``data/florida/noise_barriers/raw/``.
* ``preprocess`` (:mod:`.preprocess`) — clean one raw release into a single
  tidy GeoParquet layer of physically-present walls (``barriers.parquet``,
  EPSG:3087) plus a ``barriers.json`` provenance sidecar, ready to join to
  school + street-network data in the ``schools`` source.
"""
