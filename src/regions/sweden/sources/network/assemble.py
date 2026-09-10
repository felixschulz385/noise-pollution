from __future__ import annotations

import geopandas as gpd
from pathlib import Path

from src.regions.sweden.sources.network.preprocess import load_network, save_network_summary, summarize_network


def load_network_bundle(path=None) -> dict[str, object]:
    network = load_network(path)
    return {"network": network, "summary": summarize_network(network)}


def plot_network_with_stations(network: gpd.GeoDataFrame, stations: gpd.GeoDataFrame):
    ax = network.plot(figsize=(10, 10), linewidth=0.5, color="#AEBBD0")
    stations.plot(ax=ax, color="#C75146", markersize=8)
    ax.set_title("Swedish rail network and Trafikverket stations")
    ax.set_axis_off()
    return ax


def save_network_plot_with_stations(network: gpd.GeoDataFrame, stations: gpd.GeoDataFrame, output_path: str | Path) -> str:
    ax = plot_network_with_stations(network, stations)
    figure = ax.get_figure()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    return str(output)


def summarize_and_save_network(path=None) -> dict[str, object]:
    bundle = load_network_bundle(path)
    summary_path = save_network_summary(bundle["summary"])
    bundle["summary_path"] = summary_path
    return bundle
