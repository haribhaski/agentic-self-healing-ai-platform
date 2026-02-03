# 1. Kill all processes using port 5020
echo "Killing any process using port 5020..."
lsof -ti :5020 | xargs kill -9 2>/dev/null || true
#!/bin/bash
# Setup and run all agents and servers in compatible Python environment


# 2. Activate venv and install requirements
source venv/bin/activate

# 3. Start MLflow server (background)
echo "Starting MLflow server on port 5020..."
mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlruns --host 0.0.0.0 --port 5020 &
MLFLOW_PID=$!
