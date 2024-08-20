import datetime
from functools import partial
from typing import Tuple

import googlemaps
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from mlforecast import MLForecast
from supabase import Client, create_client
from timezonefinder import TimezoneFinder
from io import StringIO

#from greenbutton import parse

from power_dashboard.electricity_maps import (
    get_electricity_maps_carbon_intensity,
    get_electricity_maps_power_breakdown,
    get_electricity_maps_zones,
)

st.set_page_config(
    page_title="Clean Electricity Dashboard", layout="wide", page_icon=":thunderbolt:"
)

tab1, tab2, tab3 = st.tabs(["Now", "Forecast", "Personal"])

gmaps = googlemaps.Client(key=st.secrets["googlemaps"]["api_key"])
tf = TimezoneFinder()


supabase_url: str = st.secrets["supabase"]["supabase_url"]
supabase_key: str = st.secrets["supabase"]["supabase_key"]
supabase_client: Client = create_client(supabase_url, supabase_key)


@st.cache_data
def get_zones():
    return get_electricity_maps_zones()


@st.cache_data(ttl=3600)
def get_carbon_intensity(lat, lng, current_hour):
    # current_hour is included to force the cache to update every hour
    result = get_electricity_maps_carbon_intensity(
        lat, lng, auth_token=st.secrets["electricitymaps"]["api_key"]
    )
    zone = result["zone"]

    # Check for longer history if available.
    response = (
        supabase_client.table("electricitymaps-hourly")
        .select("*")
        .eq("testing", False)
        .eq("zone", zone)
        .execute()
    )
    all_records = pd.DataFrame.from_records(
        [
            record
            for resp in response.data
            for record in resp["carbon_intensity_raw"]["history"]
        ]
    )
    if len(all_records) == 0:
        return result
    else:
        idx = all_records.groupby(["zone", "datetime"])["updatedAt"].idxmax()
        filtered_records = all_records.loc[idx].reset_index(drop=True)

        datetime_cols = ["datetime", "createdAt", "updatedAt"]
        filtered_records[datetime_cols] = filtered_records[datetime_cols].apply(
            pd.to_datetime
        )
        result = {
            "zone": zone,
            "history": filtered_records.to_dict(orient="records"),
        }
        return result


@st.cache_data(ttl=3600)
def get_power_breakdown(lat, lng, current_hour):
    # current_hour is included to force the cache to update every hour
    return get_electricity_maps_power_breakdown(
        lat, lng, auth_token=st.secrets["electricitymaps"]["api_key"]
    )


@st.cache_data
def get_gridemissions_history(region: str) -> pd.DataFrame:
    response = (
        supabase_client.table("gridemissions-ts")
        .select("*")
        .eq("region", region)
        .execute()
    )
    try:
        df = pd.DataFrame.from_records(response.data).set_index("id")
        return df
    except KeyError:
        return pd.DataFrame()


# Cut down gmaps API costs by cacheing results.
@st.cache_data
def geocode_address(address: str) -> dict:
    geocode_result = gmaps.geocode(address)
    location = geocode_result[0]["geometry"]["location"]
    location["formatted_address"] = geocode_result[0]["formatted_address"]
    return location


def find_minimum_hour(
    df: pd.DataFrame, value_col: str, time_col: str, window: int = 4
) -> Tuple[datetime, datetime]:
    """
    Find the minimum contiguous hours of a given length in a DataFrame
    """
    _df = df.reset_index()
    min_index = _df[value_col].idxmin()
    if not np.isnan(min_index):
        min_end = _df.loc[min_index, time_col]
        min_start = min_end - pd.Timedelta(hours=window)
        return (min_start, min_end)
    else:
        return (pd.NaT, pd.NaT)


_func = partial(
    find_minimum_hour,
    value_col="rolling_avg_intensity",
    time_col="local_time",
    window=4,
)


def convert_hour_to_string(hour):
    if hour == 0:
        return "Midnight"
    elif hour == 12:
        return "Noon"
    elif hour > 12:
        return f"{hour - 12}:00 PM"
    else:
        return f"{hour}:00 AM"


@st.cache_data
def load_forecast_model():
    return MLForecast.load("models/final_model")


zones = get_zones()

with st.spinner("Updating..."):
    address = st.sidebar.text_input("Enter your address")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H")

    if address == "":
        st.stop()

    location = geocode_address(address)

    # Get the carbon intensity data
    result = get_carbon_intensity(location["lat"], location["lng"], now)
    timezone_str = tf.timezone_at(lng=location["lng"], lat=location["lat"])
    carbon_intensity_df = pd.DataFrame.from_records(result["history"])
    localized_time = pd.to_datetime(carbon_intensity_df["datetime"]).dt.tz_convert(
        timezone_str
    )
    latest_time = localized_time.max()
    latest_carbon_intensity = carbon_intensity_df.loc[
        localized_time == latest_time, "carbonIntensity"
    ].values[0]
    mean_carbon_intensity = carbon_intensity_df["carbonIntensity"].mean()
    delta = (
        (latest_carbon_intensity - mean_carbon_intensity) / mean_carbon_intensity * 100
    )

    # Get the production breakdown data
    power_breakdown_result = get_power_breakdown(location["lat"], location["lng"], now)

    with st.sidebar:
        st.markdown("### Displaying Results for:")
        st.markdown(f"**Location**: {location['formatted_address']}")
        st.markdown(f"**Grid Zone**: {zones[result["zone"]]['zoneName']}")
        st.markdown(f"**Timezone**: {timezone_str}")
        st.markdown(f"**Local Time**: {latest_time}")

    with tab1:
        st.title("Clean Electricity Dashboard")
        # Display grid intensity
        m1, m2, m3 = st.columns((1, 1, 1))
        m1.metric(
            label="Fossil Free Percentage",
            value=f"{power_breakdown_result['fossilFreePercentage']} %",
        )
        m2.metric(
            label="Carbon Intensity",
            value=f"{latest_carbon_intensity} gCO2e/kWh",
            delta=f"{delta:.2f}% from recent average",
            delta_color="inverse",
        )
        m3.metric(
            label="Renewable Percentage",
            value=f"{power_breakdown_result['renewablePercentage']} %",
        )

        # Display production reakdown
        cols = st.columns(
            len(power_breakdown_result["powerConsumptionBreakdown"].keys())
        )

        # Sort power consumption breakdown in decreasing order and display the top 3 sources
        sorted_sources = sorted(
            power_breakdown_result["powerConsumptionBreakdown"].items(),
            key=lambda item: item[1],
            reverse=True,
        )

        st.subheader("Top 3 power generation sources")
        cols = st.columns((1, 1, 1))
        for i, (source, value) in enumerate(sorted_sources[:3]):
            cols[i].metric(label=source, value=f"{value} MW")

        with st.expander("Show more sources"):
            cols = st.columns(
                len(power_breakdown_result["powerConsumptionBreakdown"].keys())
            )
            for i, (source, value) in enumerate(sorted_sources[3:]):
                st.metric(label=source, value=f"{value} MW")

        st.subheader(
            f"Carbon Intensity over previous 24 hrs in {zones[result['zone']]['zoneName']}"
        )
        fig, ax = plt.subplots(figsize=(10, 3))

        ax.plot(
            localized_time.tail(24),
            carbon_intensity_df["carbonIntensity"].tail(24),
            label="Carbon Intensity",
        )
        ax.hlines(
            mean_carbon_intensity,
            localized_time.tail(24).min(),
            localized_time.tail(24).max(),
            label="Recent Average Carbon Intensity",
            color="red",
            linestyle="--",
        )
        ax.legend()
        ax.set_ylabel("gCO2e/kWh")
        ax.set_xlabel("Time")

        st.pyplot(fig)
        st.caption(
            "Data from [electricityMap API](https://api-portal.electricitymaps.com/)"
        )

    with tab2:
        st.title("Forecasted Grid Emissions")

        ba_str = result["zone"].split("-")[-1]
        region = f"CO2i_{ba_str}_D"
        df = get_gridemissions_history(region)

        if len(df) == 0:
            st.write(
                "Grid Emissions History and Forecasts are not available for this region."
            )
            st.stop()

        df["local_time"] = pd.to_datetime(df.period).dt.tz_convert(timezone_str)
        df["rolling_avg_intensity"] = df["co2_intensity"].rolling(window=4).mean()
        start_time_by_day = df.groupby(df.local_time.dt.date).apply(
            lambda grp: _func(df=grp)[0].hour
        )

        distribution = start_time_by_day.value_counts().sort_index()
        st.write(
            f"In {zones[result['zone']]['zoneName']}, the most frequent start time for a minimum 4-hour contiguous low CO2 intensity period is:"
        )
        st.subheader(f"**{convert_hour_to_string(distribution.idxmax())}!!**")

        # Plot it
        fig, ax = plt.subplots()
        distribution.plot(kind="bar", ax=ax)
        ax.set_title(
            f"Distribution of start of Minimum 4-hour Contiguous Low CO2 Intensity Periods for {zones[result['zone']]['zoneName']}"
        )
        ax.set_xlabel("Hour of the Day")

        st.pyplot(fig)
        st.caption(
            "Data from [gridemissions](https://gridemissions.jdechalendar.su.domains/)"
        )

        model = load_forecast_model()
        # carbon_intensity_df = pd.DataFrame.from_records(result["history"])
        # localized_time = pd.to_datetime(carbon_intensity_df["datetime"]).dt.tz_convert(
        #     timezone_str
        # )
        X = pd.DataFrame(
            {
                "y": carbon_intensity_df["carbonIntensity"],
                "ds": localized_time,
                "unique_id": region,
            }
        )
        forecast = model.predict(
            h=24,
            new_df=X,
        )
        (min_start, min_end) = find_minimum_hour(forecast, "LGBMRegressor", "ds")
        st.write(
            "In the next 24 hours, forecasting finds a minimum 4-hour contiguous low CO2 intensity period starts at:"
        )
        st.subheader(f"**{convert_hour_to_string(min_start.hour)}!!**")

        fig, ax = plt.subplots()
        ax.plot(X.tail(24).ds, X.tail(24).y, label="Observed")
        ax.plot(forecast.ds, forecast["LGBMRegressor"], label="Forecast")
        ax.set_title(f"24-hour Forecast for {zones[result['zone']]['zoneName']}")

        # Set major locator to every hour
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=6, tz=timezone_str))

        # Set major formatter to show date and time
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%Y-%m-%d %H:%M", tz=timezone_str)
        )

        # Optional: rotate and align the tick labels so they look better
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        # Optional: add grid for better readability
        ax.grid(True)
        ax.legend(bbox_to_anchor=(1, 0.7))
        ax.set_ylabel("Carbon Intensity (gCO2eq/kWh)")
        fig.autofmt_xdate()
        st.pyplot(fig)

    with tab3:
        st.title("Personal CO2 Calculator from Green Button XML File")

        uploaded_file = st.file_uploader("Choose a Green Button XML file")
        if uploaded_file is not None:
            stringio = StringIO(uploaded_file.getvalue().decode("utf-8"))
            string_data = stringio.read()
            #ups = parse.parse_feed(string_data)
            st.write(string_data)

