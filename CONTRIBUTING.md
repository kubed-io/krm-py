# Contributing

Follow these steps to be proper. There is a lot of very specific steps and automations, please read this entire document before starting. Many questions will be answered by simply getting everything setup exactly the same way in the instructions.

## Clone the Repo

Clone the repo with the wiki submodule. The wiki submodule contains the static content and templates for mkdocs.

```sh
git clone --recurse-submodules git@github.com:kubed-io/krm-py.git
```

## [Direnv](https://github.com/direnv/direnv) Setup

Here is a good start for a decent `.envrc` file.

```sh
layout python3 # creates the python venv using direnv and sets the VIRTUAL_ENV environment variable to use it
```

## Installation

Install dependencies in editable mode so you can use step through debugging. All of the optional dependencies are included within the square brackets. You can see what they all are in the [`pyproject.toml`](pyproject.toml) file.

```sh
pip install --editable '.[build]'
```

The unit tests are a good starting place for development.

```sh
pytest src -m unit
```

At least this should work: 

```sh
kustomize build ./examples/embed --enable-alpha-plugins --enable-exec
```


## Changelog

Make sure to take note of your changes in the changelog. This is done by updating the `CHANGELOG.md` file. Add any new details under the `## [Unreleased]` section. When a new version is published, the word `Unreleased` will be replaced with the version number and the date. The section will also be the detailed release notes under releases in Github. The checks on the PR will fail if you don't add any notes in the changelog.

## Signed Commits

This is a public repo, one cannot simply trust that a commit came from who it says it did. To ensure the integrity of the commits, all commits must be signed. Your commits and PR will be rejected if they are not signed. Please read more about how to do this here if you do not know how: [Github Signing Commits](https://docs.github.com/en/github/authenticating-to-github/managing-commit-signature-verification/signing-commits). Ideally, if you have 1password, please follow these instructions: [1Password Signing Commits](https://blog.1password.com/git-commit-signing/).

## Building Artifacts

Build the pip package. This will cache in the build folder and the final output will be in the dist folder. This package is deployed to [pypi](https://pypi.org/project/kubed-krm/).

```sh
python -m build
```

## Version Bump

Get the current version:

```sh
python -m setuptools_scm
```

When building the artifact the setuptools scm tool will use the a snazzy semver logic to determine version.

_ref:_ [SetupTools SCM](https://pypi.org/project/setuptools-scm/)

When Ready to publish a new version live, go to the workflow and run the workflow manually. This will bump the version, build the artifact, and push the new version to pypi.

## Docker Image

The docker file uses a couple of stages to do a few different tasks. Mainly the official image is the runner target. The bin target is for generating multiarch binaries.

Build the main image locally for your machine using compose.

```sh
docker compose build
```

Or use bake to for a multiarch image. You just can't export images that are not your arch locally. So use compose to actually build the image locally.

```sh
docker buildx bake
```



## Documentation

The wiki is a static generated website using mkdocs. All of the resource docs are pulled out from the pydoc strings in the code. The convention for docs in code is [Google style docstrings](https://google.github.io/styleguide/pyguide.html).

Here is an example of the docstring format.

```python
def my_function(param1, param2) -> dict:
    """This is a function that does something.

    Args:
      param1: The first parameter.
      param2: The second parameter.

    Returns:
      message: The return value.

    Raises:
        KubedError: If the value is not correct.
    """
    return {}
```

## VSCode Setup

To be helpful as possible, all of the sweet spot configurations for VSCode are included in the `.vscode` folder. Although these files are committed they have been ignored from the working tree, so feel free to update them as you see fit and they will not be committed.

Here is how git is ignoring the files.

```sh
git update-index --skip-worktree .vscode/settings.json
```

### Step Through Debugging

Within the `.vscode/launch.json`, change the `args` to the command you want to debug, this is equivelent to running from the command line. Remember to install the project with `--editable` so you can step through the code easily.

### Tasks

All of the commands described above have been implemented as VSCode tasks in the `.vscode/tasks.json`. This goes well with the [spmeesseman.vscode-taskexplorer](https://marketplace.visualstudio.com/items?itemName=spmeesseman.vscode-taskexplorer) extension which gives you a nice little button to run the tasks.

### Devcontainer

The `.devcontainer.json` file is included for quickly spinning up a working enviornment. This is a good way to ensure that all of the dependencies are installed and the correct version of python is being used without fighting with any nuances present in your local environment.


