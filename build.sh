#!/usr/bin/env bash

function krm_clean() {
    rm -rf \
        dist build \
        .coverage .pytest_cache .tmp \
        *.egg-info src/*.egg-info **/__pycache__ \
        .direnv .ruff_cache requirements.txt

    find . | grep -E "(/__pycache__$|\.pyc$|\.pyo$)" | xargs rm -rf
}

krm_${@}