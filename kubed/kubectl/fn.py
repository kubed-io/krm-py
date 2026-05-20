#!/usr/bin/env python3
"""kubectl fn - Fission function utilities

Commands:
  pack      Package source files into a zip archive
  publish   Publish package to Fission storagesvc and update service.yaml
"""

import sys
import os
import socket
import time
import zipfile
import hashlib
import subprocess
import argparse
from pathlib import Path
import yaml
from datetime import datetime
import fnmatch

try:
    import requests
except ImportError:
    requests = None


def pack(service_file, output=None, quiet=False):
    """Pack source files into a zip archive

    Args:
        service_file: Path to service.yaml file
        output: Optional output zip file path (defaults to <package-name>-<timestamp>.zip)
        quiet: If True, suppress output messages (for use by KRM generator)

    Returns:
        tuple: (zip_path, checksum)
    """
    service_path = Path(service_file).resolve()

    if not service_path.exists():
        if not quiet:
            print(f"Error: Service file not found: {service_path}", file=sys.stderr)
        sys.exit(1)

    # Load service.yaml
    with open(service_path, 'r') as f:
        service = yaml.safe_load(f)

    # Validate it's a Service kind
    if service.get('kind') != 'Service' or not service.get('apiVersion', '').startswith('serverless.krm.kubed.io'):
        if not quiet:
            print(f"Error: File is not a serverless Service resource", file=sys.stderr)
        sys.exit(1)

    spec = service.get('spec', {})
    package_spec = spec.get('package', {})
    include_patterns = package_spec.get('include', [])
    package_name = package_spec.get('name', service['metadata']['name'])
    source_spec = package_spec.get('source', {})
    embedded_source = source_spec.get('literal')

    source_dir = service_path.parent

    # Determine output path
    if output:
        output_path = Path(output).resolve()
    else:
        version = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        archive_name = f"{package_name}-{version}.zip"
        output_path = Path(f"/tmp/{archive_name}")

    # Collect files matching include patterns
    files_to_pack = []
    embedded_files = {}  # {filename: content}

    # Handle embedded source
    if embedded_source:
        # Default to main.py if no include patterns
        embedded_filename = "main.py"
        embedded_files[embedded_filename] = embedded_source
        if not quiet:
            print(f"Including embedded source as {embedded_filename}")

    # Collect files from include patterns
    for pattern in include_patterns:
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(source_dir)
                rel_path_str = str(rel_path)
                if fnmatch.fnmatch(rel_path_str, pattern) or fnmatch.fnmatch(file_path.name, pattern):
                    # Skip if this file would conflict with embedded source
                    if rel_path_str not in embedded_files:
                        if file_path not in files_to_pack:
                            files_to_pack.append(file_path)

    # Automatically include buildcmd file if specified
    buildcmd = package_spec.get('buildcmd')
    if buildcmd:
        buildcmd_path = source_dir / buildcmd
        if buildcmd_path.exists() and buildcmd_path.is_file():
            if buildcmd_path not in files_to_pack and buildcmd not in embedded_files:
                files_to_pack.append(buildcmd_path)

    if not files_to_pack and not embedded_files:
        if not quiet:
            print(f"Error: No files to pack (no include patterns and no embedded source)", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print(f"Packing {len(files_to_pack) + len(embedded_files)} files")
        if embedded_files:
            for filename in sorted(embedded_files.keys()):
                print(f"  - {filename} (embedded)")
        for f in sorted(files_to_pack):
            print(f"  - {f.relative_to(source_dir)}")

    # Create zip archive
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add embedded files first
        for filename, content in embedded_files.items():
            zipf.writestr(filename, content)

        # Add files from disk
        for file_path in files_to_pack:
            arcname = file_path.relative_to(source_dir)
            zipf.write(file_path, arcname)

    # Calculate SHA256
    sha256_hash = hashlib.sha256()
    with open(output_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)

    checksum = sha256_hash.hexdigest()

    if not quiet:
        print(f"\nPackage created: {output_path}")
        print(f"Size: {output_path.stat().st_size} bytes")
        print(f"SHA256: {checksum}")

    return str(output_path), checksum


STORAGESVC_IN_CLUSTER = 'http://storagesvc.flow'
STORAGESVC_NAMESPACE = 'flow'
STORAGESVC_PORT_FORWARD_LOCAL = 17731


def _storagesvc_reachable(url):
    """Check if storagesvc is reachable at the given base URL."""
    try:
        host = url.replace('http://', '').split(':')[0]
        port = int(url.split(':')[-1]) if ':' in url.replace('http://', '') else 80
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((host, port))
        sock.close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False


def _upload_to_storagesvc(zip_path):
    """Upload a zip to storagesvc. Returns the in-cluster source URL.

    Tries the in-cluster URL first; falls back to kubectl port-forward
    when running outside the cluster.
    """
    if requests is None:
        print("Error: 'requests' library is required. Run: pip install requests", file=sys.stderr)
        sys.exit(1)

    pf_proc = None
    upload_base = STORAGESVC_IN_CLUSTER

    if not _storagesvc_reachable(STORAGESVC_IN_CLUSTER):
        local = f'http://localhost:{STORAGESVC_PORT_FORWARD_LOCAL}'
        print(f"storagesvc not reachable in-cluster, starting port-forward on :{STORAGESVC_PORT_FORWARD_LOCAL}...")
        pf_proc = subprocess.Popen(
            ['kubectl', 'port-forward', 'svc/storagesvc',
             f'{STORAGESVC_PORT_FORWARD_LOCAL}:80', '-n', STORAGESVC_NAMESPACE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)
        upload_base = local

    try:
        file_size = Path(zip_path).stat().st_size
        with open(zip_path, 'rb') as f:
            resp = requests.post(
                f'{upload_base}/v1/archive',
                headers={'X-File-Size': str(file_size)},
                files={'uploadfile': (Path(zip_path).name, f, 'application/zip')},
                timeout=60,
            )
        resp.raise_for_status()
        archive_id = resp.json()['id']
    finally:
        if pf_proc:
            pf_proc.terminate()

    # Always return the in-cluster URL — Fission fetches from inside the cluster
    return f'{STORAGESVC_IN_CLUSTER}/v1/archive?id={archive_id}'


def publish(service_file):
    """Publish package to Fission storagesvc and update service.yaml

    Args:
        service_file: Path to service.yaml file
    """
    service_path = Path(service_file).resolve()

    if not service_path.exists():
        print(f"Error: Service file not found: {service_path}", file=sys.stderr)
        sys.exit(1)

    # Load service.yaml
    with open(service_path, 'r') as f:
        service = yaml.safe_load(f)

    # Validate it's a Service kind
    if service.get('kind') != 'Service' or not service.get('apiVersion', '').startswith('serverless.krm.kubed.io'):
        print(f"Error: File is not a serverless Service resource", file=sys.stderr)
        sys.exit(1)

    spec = service.get('spec', {})
    package_spec = spec.get('package', {})
    package_name = package_spec.get('name', service['metadata']['name'])
    include_patterns = package_spec.get('include', ['*.py'])
    source_dir = service_path.parent

    print(f"=== Publishing package: {package_name} ===")
    print(f"Service file: {service_path}")
    print(f"Source directory: {source_dir}")
    print(f"Include patterns: {include_patterns}")

    # Pack the files
    zip_path, checksum = pack(service_file, output=None)

    # Upload to storagesvc
    print(f"\nUploading to storagesvc...")
    source_url = _upload_to_storagesvc(zip_path)
    print(f"Stored at: {source_url}")

    # Update service.yaml
    print(f"Updating {service_path.name}...")
    if 'package' not in spec:
        spec['package'] = {}
    if 'source' not in spec['package']:
        spec['package']['source'] = {}

    spec['package']['source']['type'] = 'url'
    spec['package']['source']['url'] = source_url

    if 'checksum' not in spec['package']['source']:
        spec['package']['source']['checksum'] = {}
    spec['package']['source']['checksum']['type'] = 'sha256'
    spec['package']['source']['checksum']['sum'] = checksum

    # Write back to file
    with open(service_path, 'w') as f:
        yaml.dump(service, f, default_flow_style=False, sort_keys=False)

    # Cleanup temp zip
    temp_zip = Path(zip_path)
    if temp_zip.exists() and temp_zip.parent == Path('/tmp'):
        temp_zip.unlink()

    print("\n=== Publish Complete ===")
    print(f"Package: {package_name}")
    print(f"Archive: {source_url}")
    print(f"Checksum: {checksum}")
    print(f"\nRun 'kubectl up {source_dir}' to deploy.")


def main():
    """Main entry point for kubectl-fn"""
    parser = argparse.ArgumentParser(
        prog='kubectl-fn',
        description='Fission function utilities'
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # pack subcommand
    pack_parser = subparsers.add_parser('pack', help='Package source files into a zip archive')
    pack_parser.add_argument('service_file', help='Path to service.yaml file')
    pack_parser.add_argument('-o', '--out', help='Output zip file path (default: <package-name>-<timestamp>.zip in /tmp)')

    # publish subcommand
    publish_parser = subparsers.add_parser('publish', help='Publish package to Fission storagesvc and update service.yaml')
    publish_parser.add_argument('service_file', help='Path to service.yaml file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'pack':
        pack(args.service_file, output=args.out)
    elif args.command == 'publish':
        publish(args.service_file)


if __name__ == '__main__':
    main()
