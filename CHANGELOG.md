# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- grafana.krm.kubed.io: Panel, Dashboard and Folder functions, with Embed and Target nodes, that build Grafana dashboards for grafana-operator
- CI in the kubed-io house style: a lint and test matrix, quality gates (CodeQL, pip-audit, zizmor, hadolint), package and image builds, and a manual publish to PyPI and Docker Hub
- the `suite` image's venv now lands on its PATH, and its `kubed/krm` base is pinned
- skeleton of the project
- working build
