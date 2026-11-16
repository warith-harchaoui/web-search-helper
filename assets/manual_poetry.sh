#!/bin/zsh
#
# Manual recipe: a conda environment, then a Poetry twin of pyproject.toml.
#
# DO NOT RUN IT AS A SCRIPT. Copy and paste the commands one by one in your
# terminal; each step is worth looking at before the next one. The project
# itself builds with setuptools from pyproject.toml, so none of this is needed
# to install, test or release web-search-helper.
#
# PHP (>= 7.4, with mbstring) is not a Python package: install it from the
# system to run the parity tests and `web-search-helper serve`.

# Enable debug and error checking
set -x  # Print each command before executing it
set -e  # Exit the script immediately on any command failure

# Configuration
PROJECT_NAME="web-search-helper"
PYTHON_VERSION="3.10"
ENV="env4wsh"

# The core dependencies, as in requirements.txt. The real embedder
# (sentence-transformers, which pulls torch) is the [embed] extra.
DEPENDENCIES=(
    "os-helper>=4.2,<5"
    "click>=8.1,<9"
    "numpy>=1.24"
)

DESCRIPTION="Search a private corpus from a website with PHP only: index it on your machine, serve it with one PHP file, embed the question in the browser."
AUTHORS="Warith Harchaoui <warithmetics@deraison.ai>"

conda init
source ~/.zshrc

# Start from a clean environment of that name.
if conda info --envs | grep -q "^$ENV"; then
    echo "Environment $ENV already exists, removing it..."
    conda deactivate
    conda remove --name $ENV --all -y
fi

echo "Creating environment $ENV..."
conda create -y -n $ENV python=$PYTHON_VERSION
conda activate $ENV
conda install -y pip

# One dependency at a time, so a failure names its culprit.
for dep in "${DEPENDENCIES[@]}"; do
    echo "Adding $dep..."
    pip install "$dep"
done

# The Poetry twin goes to a separate file, never over the real pyproject.toml.
python assets/requirements_to_toml.py \
    --project_name "$PROJECT_NAME" \
    --description "$DESCRIPTION" \
    --authors "$AUTHORS" \
    --python_version "^$PYTHON_VERSION" \
    --requirements_file "requirements.txt" \
    --output_file "pyproject.poetry.toml" \
    --opensource

echo "Environment $ENV ready; Poetry twin written to pyproject.poetry.toml."
