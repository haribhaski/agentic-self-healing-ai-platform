#!/bin/bash
# This script sets up a Python 3.10 virtual environment for MLflow and your project, reinstalls all dependencies, and starts the MLflow server.

set -e

# 1. Check for python3.10
if ! command -v python3.10 &> /dev/null; then
  echo "Python 3.10 is not installed. Please install it first (e.g., brew install python@3.10) and re-run this script."
  exit 1
fi

# 2. Remove old venv if exists
if [ -d "venv310" ]; then
  echo "Removing old venv310..."
  rm -rf venv310
fi

# 3. Create new venv
python3.10 -m venv venv
source venv/bin/activate

# 4. Upgrade pip
pip install --upgrade pip

# 5. Reinstall all dependencies
pip install -r backend/requirements.txt
pip install mlflow
# Add any other requirements files here if needed

# 6. Start MLflow server
mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns --host 0.0.0.0 --port 5000
