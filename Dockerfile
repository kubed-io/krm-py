ARG PY_VERSION=3.12 \
    TARGETPLATFORM \
    BUILDPLATFORM
##
# Base setup step
# Simply copy project and install
## 
FROM python:$PY_VERSION AS setup
WORKDIR /app
COPY . . 
RUN <<EOF
pip install --no-cache-dir --upgrade pip
pip install --no-cache-dir .[build]
EOF

##
# Package builder intermediate step
# Allows for successive steps to simple copy the built package
##
FROM setup AS builder
RUN python -m build --no-isolation

##
# Final runtime image
# This is pushed to the registry.
##
FROM kubed/krm:latest AS runner
ARG TARGETPLATFORM \
    BUILDPLATFORM

RUN apk --no-cache add \
        python3 \
        py3-pip \
        ncurses

COPY --from=builder /app/dist ./dist/

RUN pip install --break-system-packages --no-cache-dir ./dist/*.whl && \
    rm -rf ./dist

SHELL [ "/bin/bash", "-c" ]

CMD ["kubed"]

##
# Dev container build
# docs: https://github.com/microsoft/vscode-dev-containers/blob/main/containers/python-3/README.md
# Makes the dev container environment
##
FROM mcr.microsoft.com/vscode/devcontainers/python:${PY_VERSION} AS dev
ARG NODE_VERSION="none" \
    KUSTOMIZE_VERSION="v5.7.1" \
    TARGETPLATFORM \
    BUILDPLATFORM
RUN <<EOF 
export DEBIAN_FRONTEND=noninteractive && apt-get update
apt-get -y install --no-install-recommends direnv python3-venv
apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/library-scripts 
curl -L "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" | tar -xz -C /usr/local/bin kustomize
chmod +x /usr/local/bin/kustomize
EOF
