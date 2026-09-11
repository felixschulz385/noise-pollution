"""Florida statewide roadway-centerline network.

FDOT RCI-derived roads, distributed as a zipped Esri File Geodatabase through
the Florida Geographic Data Library (FGDL) — the same publisher and archive
shape as ``noise_barriers``. This is the base layer for the ``schools``
source's side-of-road matching (algorithms 3-5, see
``docs/data/florida/road_network/README.md``) and, later, the planned
``traffic`` / ``road_projects`` sources.

Stages:

* ``fetch`` (:mod:`.fetch`) — download one FGDL ``rciroads`` release, extract
  its shapefile parts and metadata XML into ``data/florida/road_network/raw/``.
* ``preprocess`` (:mod:`.preprocess`) — clean one raw release into a single
  tidy GeoParquet layer of roadway centerline segments
  (``road_network.parquet``, EPSG:3087) plus a ``road_network.json``
  provenance sidecar, ready to join to ``noise_barriers`` + school points in
  the ``schools`` source.
"""
