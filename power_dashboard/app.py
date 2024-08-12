import datetime

import googlemaps
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from timezonefinder import TimezoneFinder

from power_dashboard.electricity_maps import (
    get_electricity_maps_carbon_intensity,
    get_electricity_maps_power_breakdown,
    get_electricity_maps_zones,
)

st.set_page_config(
    page_title="Clean Electricity Dashboard", layout="wide", page_icon=":thunderbolt:"
)

# t1, t2 = st.columns((0.07,1))

# t1.image('images/index.png', width = 120)
st.title("Clean Electricity Dashboard")

gmaps = googlemaps.Client(key=st.secrets["googlemaps"]["api_key"])
tf = TimezoneFinder()


@st.cache_data
def get_zones():
    return get_electricity_maps_zones()


@st.cache_data(ttl=3600)
def get_carbon_intensity(lat, lng, current_hour):
    # current_hour is included to force the cache to update every hour
    return get_electricity_maps_carbon_intensity(
        lat, lng, auth_token=st.secrets["electricitymaps"]["api_key"]
    )


@st.cache_data(ttl=3600)
def get_power_breakdown(lat, lng, current_hour):
    # current_hour is included to force the cache to update every hour
    return get_electricity_maps_power_breakdown(
        lat, lng, auth_token=st.secrets["electricitymaps"]["api_key"]
    )


# Cut down gmaps API costs by cacheing results.
@st.cache_data
def geocode_address(address: str) -> dict:
    geocode_result = gmaps.geocode(address)
    location = geocode_result[0]["geometry"]["location"]
    location["formatted_address"] = geocode_result[0]["formatted_address"]
    return location


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

    # Display grid intensity
    m1, m2, m3 = st.columns((1, 1, 1))
    m1.metric(
        label="Fossil Free Percentage",
        value=f"{power_breakdown_result['fossilFreePercentage']} %",
    )
    m2.metric(
        label="Carbon Intensity",
        value=f"{latest_carbon_intensity} gCO2e/kWh",
        delta=f"{delta:.2f}% from 24hr average",
        delta_color="inverse",
    )
    m3.metric(
        label="Renewable Percentage",
        value=f"{power_breakdown_result['renewablePercentage']} %",
    )

    # Display production reakdown
    cols = st.columns(len(power_breakdown_result["powerConsumptionBreakdown"].keys()))

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
        localized_time, carbon_intensity_df["carbonIntensity"], label="Carbon Intensity"
    )
    ax.hlines(
        mean_carbon_intensity,
        localized_time.min(),
        localized_time.max(),
        label="Average Carbon Intensity",
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
