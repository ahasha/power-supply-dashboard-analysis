import logging
from pathlib import Path

import pandas as pd
from logging_config import configure_logging

from power_dashboard.gridemissions_utils import load_bulk

logger = logging.getLogger(__name__)


def load_gridemissions_history():
    """
    Load gridemissions history data.
    """
    # Hard-coded for now.
    bulk_file_dir = Path("data/interim/gridemissions")

    co2i = load_bulk(bulk_file_dir, "co2i")
    all_ts = (
        co2i.df.reset_index()
        .melt(id_vars=["period"], var_name="region", value_name="CO2 Intensity")
        .dropna()
    )

    # period represents "UTC Time at End of Hour" (see https://github.com/jdechalendar/gridemissions/blob/696838bc82c74aa40ab54206b36aec2026908a2d/src/gridemissions/eia_bulk_grid_monitor.py#L29)
    # We need to localize the timestamp to UTC and subtract an hour
    # to get to the beginning of the hour.  We can then convert to specific timezones downstream.
    all_ts.period = all_ts.period.dt.tz_localize("UTC") - pd.Timedelta(hours=1)
    logger.info(
        f"Loaded {len(all_ts)} records for {len(all_ts.region.unique())} regions."
    )
    logger.info(f"Earliest timestamp: {all_ts.period.min()}")
    logger.info(f"Latest timestamp: {all_ts.period.max()}")

    all_ts.to_csv("data/processed/gridemissions_ts.csv")
    logger.info(
        "Manually upload data/processed/gridemissions_ts.csv to supabase as follows"
    )
    logger.info(
        "psql -h aws-0-us-east-1.pooler.supabase.com -p 5432 -d postgres -U postgres.zsfmcbykdoviifsoauxs"
    )
    logger.info("... password required ...")
    upload_command = """
    \copy "gridemissions-ts" ("id", "period", "region", "co2_intensity") FROM 'data/processed/gridemissions_ts.csv' DELIMITER ',' CSV HEADER;
    """
    logger.info(upload_command)


if __name__ == "__main__":
    configure_logging("pipeline_logs/load_grid_emissions_history.log")
    load_gridemissions_history()
