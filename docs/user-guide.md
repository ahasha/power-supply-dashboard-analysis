# User Guide

## DVC How To...

Of the tools incorporated in this project template, DVC is likely the least familiar to the typical Data Scientist and has
more of a learning curve to use effectively.  The project has [good documentation](https://dvc.org/doc/user-guide) which is
well worth reviewing in greater detail.

Below are a few of the most common DVC commands you will use frequently during model development, discussed in the order that they're typically used in a standard workflow. Consult the [DVC command reference](https://dvc.org/doc/command-reference) for
a full listing of commands and greater detail.

Below is a summary of the most commonly used commands roughly in the order you will use them when spinning up a pre-existing project with pre-tracked data.  To keep things simple, I avoid discussing command arguments and flags and instead just give a typical example.  You can always add `--help` to see available options or consult the [command reference](https://dvc.org/doc/command-reference) for more detail.

### Pull project data from remote storage: `dvc pull`

Once you have cloned the project code from GitHub, you can fetch the tracked data into the workspace by running `dvc pull`.

:::{tip}
Depending on your environment, you'll likely need to authorize your access to GCP by running `gcloud auth application-default login` first.
:::

### Check whether code and data are aligned: `dvc status`

[`dvc status`](https://dvc.org/doc/command-reference/status) shows changes in the project pipelines, as well as file mismatches either between the cache and workspace, or between the cache and remote storage.  Use it to diagnose whether data and code are aligned and see which stages of the pipeline will run if `dvc repro` is called.


### Switch branches and get aligned data: `git switch <branch>; dvc checkout`

To update your workspace to a different branch and keep the data in sync with DVC, you first use a git command to change the code version, then run `dvc checkout` to load the associated data into the workspace.

[`dvc checkout`](https://dvc.org/doc/command-reference/checkout) updates DVC-tracked files and directories in the workspace based on current `dvc.lock` and `.dvc` files.  This command is usually needed after git checkout, git clone, or any other operation that changes the current dvc.lock or .dvc files in the project (though the installed git hooks frequently automate this step). It restores the
versions of all DVC-tracked data files and directories referenced in DVC metadata files from the cache to the workspace.

:::{tip}
If you have installed the DVC post-checkout hooks, `dvc checkout` will run automatically after `git checkout`.
:::

:::{hint}
If you get warnings that data is missing from the cache, you may need to `dvc pull` from a remote first.
:::

### Define the pipeline DAG

You define the Directed Acyclic Graph (DAG) of your pipeline using the [`dvc.yaml`](https://dvc.org/doc/user-guide/project-structure/dvcyaml-files#dvcyaml). The individual scripts or tasks in the pipeline are called "stages".

`dvc.yaml` defines a list of stages, the commands required to run them, their input data and parameter dependencies, and their output artifacts, metrics, and plots.

dvc.yaml uses the YAML 1.2 format and a human-friendly schema explained in detail [here](https://dvc.org/doc/user-guide/project-structure/dvcyaml-files). DVC provides CLI commands to edit the `dvc.yaml` file, but it is generally easiest to edit it manually.

`dvc.yaml` files are designed to be small enough so you can easily version them with Git along with other DVC files and your project's code.

#### Add a stage to the model pipeline

Let's look at a smaple stage. It depends on a script file it runs as well as on a raw data input:

```yaml
stages:
  prepare:
    cmd: source src/cleanup.sh
    deps:
    - src/cleanup.sh
    - data/raw.csv
    outs:
    - data/clean.csv
```

A new stage can be added to the model pipeline DAG in one of two ways:

1. Directly edit the pipeline in `dvc.yaml` files. (recommended)
2. Use the CLI command `dvc stage add` -- a limited command-line interface to setup
   pipelines.  For example:

```bash
$ dvc stage add --name train \
                --deps src/model.py \
                --deps data/clean.csv \
                --outs data/predict.dat \
                python src/model.py data/clean.csv
```

would add the following to `dvc.yaml`

```yaml
stages:
  prepare:
  ...
  train:
    cmd: python src/model.py data/model.csv
    deps:
    - src/model.py
    - data/clean.csv
    outs:
    - data/predict.dat
```

:::{tip}
One advantage of using `dvc stage add` is that it will verify the validity of
the arguments provided (otherwise stage definition won't be checked until execution).
A disadvantage is that some advanced features such as templating are not available this way.
:::

### Calculate (or reproduce) pipeline outputs: `dvc repro`

[`dvc repro`](https://dvc.org/doc/command-reference/repro) reproduces complete or partial pipelines by running their stage commands as needed in the correct order. This is similar to `make` in software build automation, in that DVC captures "build requirements" (stage dependencies) and determines which stages need to run based on whether there outputs are "up to date".  Unlike `make`, it caches the pipeline's outputs along the way.

Alternatively, you can use a [DVC experiment tracking workflow](dvc-experiments/).

:::{admonition} Why did I get *permission denied* when I try to modify a pipeline output!?!?
:clas: caution

This is expected when you use the default configuration settings of this template! DVC moves all tracked data to the project's cache.  However, the versions of the tracked files that match the current code are also needed in the workspace, so a subset of the cached files are placed in the working directory (using `dvc checkout`).  Does this mean that some files will be duplicated between the workspace and the cache?  That would not be efficient, especially with large files!

In order to have the files present in both directories without duplication, this template configures DVC to create file [hardlinks](https://www.redhat.com/sysadmin/linking-linux-explaiend) to the cached data in the workspace.
A hardlink is merely a second filesystem pointer to the same underlying data blocks on the hard disk, so modifying these files in place would ocrrupt the DVC cache.  To prevent this, DVC takes over managment of the tracked files in the workspace and cache and sets them all to read-only.  **They should only be modified with DVC commands such as `dvc repro`.**  Manually tracked files (not generated by the pipeline, but added with `dvc add`) can be modified after running `dvc unprotect` on it.

Visit [Large Dataset Optimization](https://dvc.org/doc/user-guide/data-management/large-dataset-optimization) for an in-depth discussion of all configurable linking options.
:::

### Define pipeline parameters

Parameters are any values used inside your code to tune analytical results. For example, a random forest classifier may require a maximum depth value. Machine learning experimentation often involves defining and searching hyperparameter spaces to improve the resulting model metrics.

Your source code should read params from structured parameters files (`params.yaml` by default). You can use the `params` field of `dvc.yaml` to tell DVC which parameter each stage depends on. When a param value has changed, `dvc repro` and `dvc exp run` invalidate any stages that depend on it, and reproduces them.

### Run one or more pipelines with varying parameters: `dvc exp run`

[`dvc exp run`](https://dvc.org/doc/command-reference/exp/run) runs or resumes a DVC experiment based on a DVC pipeline.  DVC experiment tracking allows tracking of results from multiple runs of the pipeline with varying parameter values (as defined in `params.yaml`) without requiring each run to be associated with its own git commit[^bloat].  It also runs the experiment using an isolated copy of the workspace, so that edits you make
while the experiment is running will not impact results.

:::{caution}
The experiment tracking feature in DVC is dangerous/confusing to use with a dirty git repository.  DVC creates a copy of the experiment's workspace in .dvc/tmp/exps/ and runs it there.  Git-ignored files/dirs are excluded from queued/temp runs to avoid committing unwanted files into Git (e.g. once successful experiments are persisted).  Under some circumstances, unstaged, git-tracked files are automatically staged and included in the isolated workspace.  The expected behavior isn't 100% clear in the documentation, so I just avoid using `dvc exp run` in a dirty repo.
:::

:::{tip}
Rule of thumb: If you want to run the pipeline to test whether uncommited changes are
correct and ready to be committed, use `dvc repro`.  `dvc exp run` is best used
with a clean repository where you want to "experiment" with results from parameter changes,
not code changes.
:::

Visit the [dvc documentation](https://dvc.org/doc/user-guide/experiment-management) and their helpful [hands-on tutorial](https://dvc.org/doc/start/experiments) to learn about the experiment-tracking features offered by DVC.

[^bloat]: This prevents bloating your repo with temporary commits and branches.

### Record changes to code and data: `dvc commit`

[`dvc commit`](https://dvc.org/doc/command-reference/commit) records changes to files or directories tracked by DVC. Stores the current contents of files and directories tracked by DVC in the cache, and updates `dvc.lock` and `.dvc` metadata files as needed. This forces DVC to accept any changed contents of tracked data currently in the workspace. [^very-useful-when]

[^very-useful-when]: This is useful when you include source files as DVC dependencies, which is recommended to ensure that DVC will recalculate stage outputs when the calculation logic is changed.  However, it can be inconvenient to recalculate a whole stage just because you reformatted a line or two (I'm looking at you `isort`...).  `dvc commit <stage>` tells DVC to ignore the change to the stage and associate the current version of the code with the already-calculated output.

### Manage remote storage endpoints: `dvc remote`

[`dvc remote`](https://dvc.org/doc/command-reference/remote) provides a set of commands to set up and manage remote storage: add, default, list, modify, remove, and rename.

### Write or get data from remote storage: `dvc push|pull`

[`dvc push`](https://dvc.org/doc/command-reference/push) uploads tracked files or directories to remote storage based on the current `dvc.yaml` and `.dvc` files.

[`dvc pull`](https://dvc.org/doc/command-reference/pull) download tracked files or directories from remote storage based on the current `dvc.yaml` and `.dvc` files, and make them visible in the workspace.

### Manually track a file: `dvc add`

[`dvc add`](https://dvc.org/doc/command-reference/add) tells DVC to track versions of data that is not created by the DVC pipeline in `dvc.yaml`. DVC allows tracking of such datasets using .dvc files as lightweight pointers to your data in the cache. The dvc add command is used to track and update your data by creating or updating .dvc files, similar to the usage of `git add` to add source code updates to git.

:::{tip}
If a file is generated as a stage output of `dvc.yaml`, you **do not** need to run `dvc add` to track changes.  `dvc repro` does this for you.
:::

### Review results metrics and their changes: `dvc metrics show|diff`

[`dvc metrics`](https://dvc.org/doc/command-reference/metrics) provides a set of commands to display and compare metrics: show, and diff.

In order to follow the performance of machine learning experiments, DVC has the ability to mark stage outputs or other files as metrics. These metrics are project-specific floating-point or integer values e.g. AUC, ROC, false positives, etc.

In pipelines, metrics files are typically generated by user data processing code, and are tracked using the -m (--metrics) and -M (--metrics-no-cache) options of `dvc stage add`

#### Compare results of two different pipeline runs or experiments

It's a good idea to use git tags to identify project revisions that you will want
to share with others and/or reference in discussions.

```bash
$ git tag -a my-great-experiment [revision]
```

creates an annotated tag at the given revision.  If `revision` is left out, HEAD is used.

You can compare pipeline metrics across any two git revisions with

```bash
$ dvc metrics diff [rev1] [rev2]
```

where `rev1` and `rev2` are any git commit hash, tag, or branch name.

### DVC internal directories and files

You shouldn't need to muck around with DVC's internals to use the tool successfully, but having a high-level understanding of how the tool works can increase your confidence and help you solve problems that inevitably arise. See the [DVC documentation](https://dvc.org/doc/user-guide/project-structure/internal-files) for more detail.

DVC creates a hidden directory in your project at `.dvc/` relative to your project root folder, which contains the directories and files needed for DVC operation.  The cache structure is similar to the structure of a `.git/` cache folder in a git repository, if that's something your familiar with.

- `.dvc/config`: This is the default [DVC configuration](https://dvc.org/doc/user-guide/project-structure/configuration) file. It can be edited by hand or with the `dvc config` command.

- `.dvc/config.local`: This is an optional Git-ignored configuration file, that will overwrite options in `.dvc/config`. This is useful when you need to specify sensitive values (secrets) which should not reach the Git repo (credentials, private locations, etc). This config file can also be edited by hand or with `dvc config --local`.

- `.dvc/cache`: Default location of the cache directory. By default, the data files and directories in the workspace will only contain links to the data files in the cache. See `dvc config cache` for related configuration options, including changing its location.

:::{important}
  Note that DVC includes the cache directory in `.gitignore` during initialization. No data tracked by DVC should ever be pushed to the Git repository, only the DVC files (`*.dvc` or `dvc.lock`) that are needed to locate or reproduce that data.
:::

- `.dvc/cache/runs`: Default location of the [run cache](https://dvc.org/doc/user-guide/project-structure/internal-files#run-cache).

- `.dvc/plots`: Directory for
  [plot templates](https://dvc.org/doc/user-guide/experiment-management/visualizing-plots#plot-templates-data-series-only)

- `.dvc/tmp`: Directory for miscellaneous temporary files

- `.dvc/tmp/updater`: This file is used to store the latest available version of
  DVC. It's used to remind the user to upgrade when the installed version is
  behind.

- `.dvc/tmp/updater.lock`: Lock file for `.dvc/tmp/updater`

- `.dvc/tmp/lock`: Lock file for the entire DVC project

- `.dvc/tmp/rwlock`: JSON file that contains read and write locks for specific
  dependencies and outputs, to allow safely running multiple DVC commands in
  parallel

- `.dvc/tmp/exps`: This directory will contain workspace copies used for
  temporary or [queued experiments](https://dvc.org/doc/user-guide/experiment-management/running-experiments#the-experiments-queue).

### DVC pre-commit hooks

`make initialize` installs several DVC pre-commit hooks to simplify your DVC+git workflow.

* The post-checkout hook executes `dvc checkout` after git checkout to automatically update the workspace with the correct data file versions.
* The pre-commit hook executes `dvc status` before git commit to inform the user about the differences between cache and workspace.
* The pre-push hook executes `dvc push` before git push to upload files and directories tracked by DVC to the dvc remote default.


## Poetry How To...

### Add software dependencies to the project

The [`poetry add`](https://python-poetry.org/docs/cli/#add) command adds required packages to your pyproject.toml and installs them.  This updates `pyproject.toml` and `poetry.lock`, which should both be committed to the git repository.

If you do not specify a version constraint, poetry will choose a suitable one based on the available package versions.

```bash
$ poetry add requests pendulum
```

```bash
# Allow >=2.0.5, <3.0.0 versions
poetry add pendulum@^2.0.5

# Allow >=2.0.5, <2.1.0 versions
poetry add pendulum@~2.0.5

# Allow >=2.0.5 versions, without upper bound
poetry add "pendulum>=2.0.5"

# Allow only 2.0.5 version
poetry add pendulum==2.0.5
```

## Documentation How To...

### Build the docs

Just run

```bash
$ make docs
```

from the project root and the documentation website will be generated in `docs/_build/html`.

### Use advanced markup supported by MyST Parser

This project uses [Sphinx](https://www.sphinx-doc.org/en/master/) combined with the
[MyST Parser Plugin](https://myst-parser.readtheocs.io/en/latest/faq/index.html) to enable
you to write documentation in markdown, but retain many of the powerful features Restructured Text (rst) format.

Check out the MyST plugin [documentation](https://myst-parser.readtheocs.io/en/latest/faq/index.html) for an overview of everything that's possible.

#### Admonitions

You can create admonitions

```
:::{tip}
Let's give readers a helpful hint!
:::
```

produces

:::{tip}
Let's give readers a helpful hint!
:::

#### Equations

You can add equations in LaTex

```
:::{math}
:label: mymath
(a + b)^2 &=& a^2 + 2ab + b^2 \\
          &=& (a + b)(a + b)
:::
```

produces

:::{math}
:label: mymath
(a + b)^2 &=& a^2 + 2ab + b^2 \\
          &=& (a + b)(a + b)
:::

You can reference them too!

```
Equation {eq}`mymath` is a quadratic equation.
```

produces

Equation {eq}`mymath` is a quadratic equation.

#### Footnotes

You can also make footnotes

```
Look at this footnote [^example-footnote]

[^example-footnote]: This is a footnote.
```

produces

Look at this footnote [^example-footnote]

[^example-footnote]: This is a footnote.

### Serve the documentation website

To build and share the documentation website:

* `make docs` builds the project documentation to `docs/_build/html`.
* `make start-doc-server` runs an http server for the documentation website.
* `make stop-doc-server` stops a running http server.


## Project Structure Roadmap

:::{include} project-organization.md
:::