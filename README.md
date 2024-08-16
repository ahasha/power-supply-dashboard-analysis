# power-supply-dashboard-analysis

Personalized dashboard providing location-based insight into carbon emissions intensity of the grid

## Quick Start

Requires python 3.12 and [poetry](https://python-poetry.org/docs/#installation) to be installed.

Create `secrets.toml` in `power_dashboard/.streamlit/` as follows (if "power_dashboard" is your git clone root):

```
[electricitymaps]
api_key = "YOUR_API_KEY" # Get an API key from https://api-portal.electricitymaps.com/

[googlemaps]
api_key = "YOUR_API_KEY"
```

Then run the streamlit app locally using:

```bash
$ poetry install
$ poetry run streamlit run power_dashboard/app.py
```

## Project Organization

Visit the [docs folder](https://github.com/ahasha/power-supply-dashboard-analysis/blob/main/docs/user-guide.md) for more info on this project's structure and how to use [DVC](https://dvc.org).
