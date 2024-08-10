### Project Organization

```
├── Makefile                   <- Makefile with project operations like `make test` or `make docs`
├── README.md                  <- The top-level README for developers using this project.
├── data
│   ├── raw                    <- The initial raw data extract from the data warehouse.
│   ├── interim                <- Intermediate data that has been transformed but is not used directly for modeling or evaluation.
│   ├── processed              <- The final, canonical data sets for modeling and evaluation.
│   └── external               <- Data from third party sources.
│
├── docs                       <- Documentation templates guiding you through documentation expectations; Structured
│   │                             as a sphinx project to automate generation of formatted documents; see sphinx-doc.org for details
│   ├── figures                <- Generated graphics and figures to be used in reporting
│   └── _build                 <- Generated documentation as HTML, PDF, LaTeX, etc.  Do not edit this directory manually.
│
├── models                     <- Trained and serialized models, model predictions, or model summaries
│
├── notebooks                  <- Jupyter notebooks. Naming convention is a number (for ordering),
│                                 the creator's initials, and a short `-` delimited description, e.g.
│                                 `1.0-jqp-initial-data-exploration.ipynb`.
├── references                 <- Data dictionaries, manuals, important papers, etc
│
├── pyproject.toml             <- Project configuration file; see [`setuptools documentation`](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
│
├── poetry.lock                <- The requirements file for reproducing the analysis environment, e.g.
│                                 generated with `poetry install`; see https://python-poetry.org/docs/
│
├── .pre-commit-config.yaml    <- Default configuration for pre-commit hooks enforcing style and formatting standards
│                                 and use of a linter (`isort`, `brunette`, and `flake8`)
│
├── .dvc                       <- Data versioning cache and configuration using dvc; see https://dvc.org
│   └── config                 <- YAML formatted configuration file for dvc project; defines default remote data storage cache location;
│
├── tests                      <- Automated test scripts;
│
├── power_dashboard            <- Source code for use in this project.
│   │
│   ├── __init__.py            <- Makes power_dashboard a Python module
|   |
|   |── ...                    <- Package modules
```