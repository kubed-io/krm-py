# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.8] - 2026-10-09

## [0.0.7] - 2026-10-09

- grafana.krm.kubed.io: a GrafanaLibrary function that builds Panel and Dashboard data, with Embed and Target nodes, into grafana-operator library panels, dashboards and folders
- grafana.krm.kubed.io: a `LibraryPanel` kind for existing library panels, and `Embed` or `Target` in a dashboard's `elements` spreading what they bring in, keyed by name
- CI in the kubed-io house style: a lint and test matrix, quality gates (CodeQL, pip-audit, zizmor, hadolint), package and image builds, and a manual publish to PyPI and Docker Hub
- the `suite` image's venv now lands on its PATH, and its `kubed/krm` base is pinned
- skeleton of the project
- working build
