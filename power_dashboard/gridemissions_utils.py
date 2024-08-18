from pathlib import Path
from typing import Union

import gridemissions as ge
import pandas as pd

TIMEZONE_MAP = {
    "CO2i_ISNE_D": "America/New_York",
    "CO2i_WACM_D": "America/Denver",
}


def load_bulk(path: Union[str, Path], which: str = "elec") -> ge.GraphData:
    if isinstance(path, str):
        path = Path(path)
    if which not in ["elec", "co2", "co2i", "raw", "basic", "rolling", "opt"]:
        raise ValueError(f"Unexpected value for which: {which}")
    files = [f for f in path.iterdir() if f.name.endswith(f"{which}.csv")]
    gd = ge.GraphData(
        pd.concat(
            [pd.read_csv(path, index_col=0, parse_dates=True) for path in files],
            axis=0,
        )
    )
    gd.df.sort_index(inplace=True)
    gd.df = gd.df[~gd.df.index.duplicated(keep="last")]

    return gd
