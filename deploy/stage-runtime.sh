#!/bin/sh
# Stage a release without changing the running services or current symlink.
set -eu
if [ "$#" -ne 2 ]; then
  echo 'Usage: stage-runtime.sh /path/to/repository /opt/gensticker-release-NAME' >&2
  exit 2
fi
code_root=$(cd "$1" && pwd)
release_root=$2
if [ -e "$release_root" ] || [ -L "$release_root" ]; then
  echo 'Release path already exists; choose a new path.' >&2
  exit 1
fi
umask 022
mkdir -p "$release_root"
# Source checkout must be trusted. No permission walk or symlink dereference.
tar -C "$code_root/backend" --exclude=.git --exclude=__pycache__ --exclude='*.pyc' --exclude='*.egg-info' --exclude=build -cf - meme-generator pil-utils | tar -C "$release_root" -xf -
python3.12 -m venv "$release_root/api-venv"
python3.12 -m venv "$release_root/worker-venv"
for role in api worker; do
  "$release_root/$role-venv/bin/python" -m pip install --upgrade 'pip==26.2.1'
  if [ "$role" = worker ]; then
    "$release_root/$role-venv/bin/python" -m pip install -e "$release_root/meme-generator" -r "$code_root/deploy/requirements-features.txt"
  else
    "$release_root/$role-venv/bin/python" -m pip install -e "$release_root/meme-generator" 'onnxruntime>=1.23,<2'
  fi
  "$release_root/$role-venv/bin/python" -m pip check
done
printf 'Staged release: %s\nRun isolated tests and backup before activation.\n' "$release_root"
