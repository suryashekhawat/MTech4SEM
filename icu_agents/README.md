# ICU Multi-Agent Synthetic Data Generation

This project generates synthetic ICU patients using specialized agents (vitals, labs, radiology, respiratory, risk, narrative), and includes Airflow DAGs for orchestration.

## 1) Local Setup (Windows native: app + Streamlit)

From `ICU-pipeline`:

```bash
cd icu_agents
python -m venv .venv
source .venv/Scripts/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 2) Run the Core App

```bash
python app.py
```

You should see a generated patient bundle and ICU summary in terminal output.

## 3) Run Streamlit UI

```bash
streamlit run ui/streamlit_app.py
```

Open the local URL shown by Streamlit and click **Generate Synthetic ICU Patient**.

## 4) Airflow Setup (Important for Windows users)

Airflow is POSIX-oriented and does not run reliably on native Windows Python.
If you see:

`ModuleNotFoundError: No module named 'fcntl'`

that is expected on Windows-native environments.

Use one of these options:

- **WSL2 (recommended for local development)**
- **Docker (recommended for reproducibility)**

### Option A: Airflow via WSL2

Open Ubuntu/WSL terminal, then run:

```bash
cd /mnt/c/Users/Surya/ICU-pipeline/icu_agents
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install apache-airflow
export AIRFLOW_HOME=$(pwd)/.airflow
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/airflow/dags
airflow db init
airflow users create \
  --username admin \
  --firstname admin \
  --lastname admin \
  --role Admin \
  --email admin@example.com \
  --password admin
```

Start services in separate terminals:

```bash
# Terminal 1
cd /mnt/c/Users/Surya/ICU-pipeline/icu_agents
source .venv/bin/activate
export AIRFLOW_HOME=$(pwd)/.airflow
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/airflow/dags
airflow scheduler
```

```bash
# Terminal 2
cd /mnt/c/Users/Surya/ICU-pipeline/icu_agents
source .venv/bin/activate
export AIRFLOW_HOME=$(pwd)/.airflow
export AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/airflow/dags
airflow webserver --port 8080
```

Open: [http://localhost:8080](http://localhost:8080)

### Option B: Airflow via Docker

From `icu_agents`:

```bash
docker compose up airflow-init
docker compose up -d airflow-webserver airflow-scheduler
```

Open: [http://localhost:8080](http://localhost:8080)

Default login:

- username: `admin`
- password: `admin`

Useful commands:

```bash
# Stop services
docker compose down

# See logs
docker compose logs -f airflow-webserver
docker compose logs -f airflow-scheduler

# Full reset (DB + metadata)
docker compose down -v
```

Notes:

- DAGs are loaded from `icu_agents/airflow/dags`.
- Output artifacts are written into your local `icu_agents/output` folder via bind mount.

## 5) DAGs Included

- `icu_multi_agent_pipeline`
- `icu_temporal_reasoning_pipeline`

Trigger either DAG from the Airflow UI. Outputs are written to:

- `output/json`
- `output/reports`
- `output/timelines`

## 6) Quick Troubleshooting

- If `airflow` command is missing, ensure virtual environment is active.
- If running on Windows native and you get `fcntl` error, switch to WSL2 or Docker.
- If DAGs do not appear, confirm `AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/airflow/dags`.
- If port conflict on `8080`, run webserver with another port (example: `--port 8081`).
- If Docker Airflow fails after dependency changes, rebuild images: `docker compose build --no-cache`.
