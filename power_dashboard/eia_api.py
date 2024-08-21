import logging
import os
import datetime
import json
import requests
from typing import Optional
import streamlit as st

# 3rd party packages
from IPython import display
import pandas as pd

logger = logging.getLogger(__name__)

EIA_API_KEY = st.secrets["eia"]["api_key"];

assert EIA_API_KEY != "", "You must set an EIA API key before continuing."

default_end_date = datetime.date.today().isoformat()
default_start_date = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()

def get_co2_data_hourly(
    local_ba,
    personal_use_by_hour,
    start_date=default_start_date,
    end_date=default_end_date,
):
    
    demand_df = get_eia_net_demand_and_generation_timeseries_hourly([local_ba]
        , start_date=start_date
        , end_date=end_date
        , frequency="hourly"
    )
    energy_generated_and_used_locally = demand_df.groupby("period").apply(
       get_energy_generated_and_consumed_locally
    )
    interchange_df = get_eia_interchange_timeseries_hourly([local_ba]
        , start_date=start_date
        , end_date=end_date
        , frequency="hourly"
    )
    energy_imported_then_consumed_locally_by_source_ba = (
        interchange_df.groupby(["period", "fromba"])[
            "Interchange to local BA (MWh)"
        ].sum()
        ## We're only interested in data points where energy is coming *in* to the local BA, i.e. where net export is negative
        ## Therefore, ignore positive net exports
        .apply(lambda interchange: max(interchange, 0))
    )
    consumed_locally_column_name = "Power consumed locally (MWh)"

    # Combine these two together to get all energy used locally, grouped by the source BA (both local and connected)
    energy_consumed_locally_by_source_ba = pd.concat(
        [
            energy_imported_then_consumed_locally_by_source_ba.rename(
                consumed_locally_column_name
            ).reset_index("fromba"),
            pd.DataFrame(
                {
                    "fromba": local_ba,
                    consumed_locally_column_name: energy_generated_and_used_locally,
                }
            ),
        ]
    ).reset_index()

    # Now that we know how much (if any) energy is imported by our local BA, and from which source BAs,
    # let's get a full breakdown of the grid mix (fuel types) for that imported energy

    # First, get a list of all source BAs: our local BA plus the ones we're importing from
    all_source_bas = energy_consumed_locally_by_source_ba["fromba"].unique().tolist()

    # Then, fetch the fuel type breakdowns for each of those BAs
    generation_types_by_ba = get_eia_grid_mix_timeseries_hourly(all_source_bas
        , start_date=start_date
        , end_date=end_date
        , frequency="hourly"
        ).rename(
        {"respondent": "fromba", "type-name": "generation_type"}, axis="columns"
    )
    # The goal is to get a DataFrame of energy used at the local BA (in MWh), broken down by both
    #  * the BA that the energy came from, and 
    #  * the fuel type of that energy.
    # So we'll end up with one row for each combination of source BA and fuel type.

    # To get there, we need to combine the amount of imported energy from each source ba with grid mix for that source BA.
    # The general formula is:
    # Power consumed locally from a (BA, fuel type) combination = 
    #    total power consumed locally from this source BA * (fuel type as a % of source BA's generation)
    # fuel type as a % of source BA's generation = 
    #    (total generation at source BA) / (total generation for this fuel type at this BA)
    total_generation_by_source_ba = generation_types_by_ba.groupby(["period", "fromba"])[
        "Generation (MWh)"
    ].sum()
    generation_types_by_ba_with_totals = generation_types_by_ba.join(
        total_generation_by_source_ba,
        how="left",
        on=["period", "fromba"],
        rsuffix=" Total",
    )
    generation_types_by_ba_with_totals["Generation (% of BA generation)"] = (
        generation_types_by_ba_with_totals["Generation (MWh)"]
        / generation_types_by_ba_with_totals["Generation (MWh) Total"]
    )
    generation_types_by_ba_with_totals_and_source_ba_breakdown = generation_types_by_ba_with_totals.merge(
        energy_consumed_locally_by_source_ba.rename(
            {"Power consumed locally (MWh)": "Power consumed locally from source BA (MWh)"},
            axis="columns",
        ),
        on=["period", "fromba"],
    )
    generation_types_by_ba_with_totals_and_source_ba_breakdown = generation_types_by_ba_with_totals_and_source_ba_breakdown.loc[generation_types_by_ba_with_totals_and_source_ba_breakdown['Generation (MWh) Total'] > 0]
    #full_df_reindexed = (
    #    generation_types_by_ba_with_totals_and_source_ba_breakdown.set_index(
    #        ["period", "fromba", "generation_type"]
    #    )
    #)
    co2_kwh_est = generation_types_by_ba_with_totals_and_source_ba_breakdown
    co2_kwh_est['CO2/(kWh)'] = co2_kwh_est[['fueltype', 'Generation (% of BA generation)', "Power consumed locally from source BA (MWh)", "Generation (MWh) Total"]].apply(co2_contrib, axis=1);
    co2_kwh_est_sum = (
        co2_kwh_est.groupby(["timestamp"])[
            "CO2/(kWh)"
        ].sum()
    ).reset_index()
    #st.text(co2_kwh_est_sum.dtypes)
    co2_kwh_est_sum["timestamp"] = co2_kwh_est_sum["timestamp"].apply(
        pd.to_datetime, format="%Y/%m/%d %H:%M:%S", utc=True
    )
    #st.text(co2_kwh_est_sum.dtypes)

    personal_use_by_hour_est = co2_kwh_est_sum.merge(
        personal_use_by_hour,
        how="left",
        on=["timestamp"]
        #, rsuffix=" Total",
    )
    personal_use_by_hour_est['Net gCO2'] = (
        personal_use_by_hour_est["CO2/(kWh)"] * personal_use_by_hour_est["Net Usage"] / 1000
    )

    return personal_use_by_hour_est

# https://github.com/jdechalendar/gridemissions/blob/696838bc82c74aa40ab54206b36aec2026908a2d/src/gridemissions/emissions.py#L14-L33 
def co2_contrib(args):
    fueltype = args[0]
    percent = args[1]
    local_fraction = args[2] / args[3]
    if fueltype == "OIL":
        return 840 * percent * local_fraction
    elif fueltype == "COL":
        return 1000 * percent * local_fraction
    elif fueltype == "NG":
        return 469 * percent * local_fraction
    elif fueltype == "SUN":
        return 46 * percent * local_fraction
    elif fueltype == "WAT":
        return 4 * percent * local_fraction
    elif fueltype == "NUC":
        return 16 * percent * local_fraction
    elif fueltype == "WND":
        return 12 * percent * local_fraction
    elif fueltype == "OTH":
        return 439 * percent * local_fraction
    elif fueltype == "UNK":
        return 439 * percent * local_fraction
    elif fueltype == "BIO":
        return 230 * percent * local_fraction
    elif fueltype == "GEO":
        return 42 * percent * local_fraction
    else:
        return 0

def get_energy_generated_and_consumed_locally(df):
    demand_stats = df.groupby("type-name")["Demand (MWh)"].sum()
    # If local demand is smaller than net (local) generation, that means: amount generated and used locally == Demand (net export)
    # If local generation is smaller than local demand, that means: amount generated and used locally == Net generation (net import)
    # Therefore, the amount generated and used locally is the minimum of these two
    try:
        return min(demand_stats["Demand"], demand_stats["Net generation"])
    except KeyError:
        # Sometimes for a particular timestamp we're missing demand or net generation. Be conservative and set iat to zero
        print(f'Warning - either Demand or Net generation is missing from this timestamp. Values found for "type-name": {list(demand_stats.index)}')
        return 0

def get_eia_timeseries(
    url_segment,
    facets,
    value_column_name="value",
    start_date=default_start_date,
    end_date=default_end_date,
    start_page=0,
    frequency="daily"
):
    """
    A generalized helper function to fetch data from the EIA API
    """

    max_row_count = 5000  # This is the maximum allowed per API call from the EIA
    api_url = f"https://api.eia.gov/v2/electricity/rto/{url_segment}/data/?api_key={EIA_API_KEY}"
    offset = start_page * max_row_count

    #print(api_url)
    #print(start_date)
    #print(end_date)
    #print(start_page)
    #print(frequency)

    logger.error(f"Request: {api_url} {start_date} {end_date} {start_page} {frequency}")

    response_content = requests.get(
        api_url,
        headers={
            "X-Params": json.dumps(
                {
                    "frequency": frequency,
                    "data": ["value"],
                    #"facets": dict(**{"timezone": ["Pacific"]}, **facets),
                    "facets": dict(**facets),
                    "start": start_date,
                    "end": end_date,
                    "sort": [{"column": "period", "direction": "desc"}],
                    "offset": offset,
                    "length": max_row_count,
                }
            )
        },
    ).json()


    # Sometimes EIA API responses are nested under a "response" key. Sometimes not 🤷 :lol
    if "response" in response_content:
        response_content = response_content["response"]

    if "data" in response_content:
        print(f"{len(response_content['data'])} rows fetched")
    else:
        print(response_content)

    # Convert the data to a Pandas DataFrame and clean it up for plotting & analysis.
    dataframe = pd.DataFrame(response_content["data"])
    # Add a more useful timestamp column
    #print(dataframe)
    #return dataframe

    dataframe["timestamp"] = dataframe["period"].apply(
        pd.to_datetime, format="%Y-%m-%dT%H"
    )
    # Clean up the "value" column-
    # EIA always sends the value we asked for in a column called "value"
    # Oddly, this is sometimes sent as a string though it should always be a number.
    # We convert its dtype and set the name to a more useful one
    eia_value_column_name = "value"
    processed_df = dataframe.astype({eia_value_column_name: float}).rename(
        columns={eia_value_column_name: value_column_name}
    )

    # Pagination logic
    rows_fetched = len(processed_df) + offset
    rows_total = int(response_content["total"])
    more_rows_needed = rows_fetched != rows_total
    if more_rows_needed:
        # Recursive call to get remaining rows
        additional_rows = get_eia_timeseries(
            url_segment=url_segment,
            facets=facets,
            value_column_name=value_column_name,
            start_date=start_date,
            end_date=end_date,
            start_page=start_page + 1,
            frequency=frequency
        )
        return pd.concat([processed_df, additional_rows])
    else:
        return processed_df
    
def get_eia_grid_mix_timeseries_hourly(balancing_authorities, **kwargs):
    """
    Fetch electricity generation data by fuel type
    """
    return get_eia_timeseries(
        url_segment="fuel-type-data",
        facets={"respondent": balancing_authorities},
        value_column_name="Generation (MWh)",
        **kwargs,
    )    

def get_eia_net_demand_and_generation_timeseries_hourly(balancing_authorities, **kwargs):
    """
    Fetch electricity demand data
    """
    return get_eia_timeseries(
        url_segment="region-data",
        facets={
            "respondent": balancing_authorities,
            "type": ["D", "NG", "TI"],  # Filter out the "Demand forecast" (DF) type
            #"timezone": ["Mountain"],
        },
        value_column_name="Demand (MWh)",
        **kwargs,
    )

def get_eia_interchange_timeseries_hourly(balancing_authorities, **kwargs):
    """
    Fetch electricity interchange data (imports & exports from other utilities)
    """
    return get_eia_timeseries(
        url_segment="interchange-data",
        facets={"toba": balancing_authorities}, #, "timezone": ["Mountain"]},
        value_column_name=f"Interchange to local BA (MWh)",
        **kwargs,
    )