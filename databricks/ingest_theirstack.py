# Databricks notebook source
# MAGIC %md
# MAGIC # TheirStack → Volume ingestion
# MAGIC One run = one session = one new folder: `/Volumes/<catalog>/<schema>/<volume>/<date>_<titles>[_<company>]_<session_id>/`
# MAGIC
# MAGIC **Job parameters** (the only two)
# MAGIC - `payload` – JSON search body: any allowed TheirStack filter, plus optional `limit` (default 25, max 500)
# MAGIC - `session_id` – optional; blank = generate one
# MAGIC
# MAGIC Target volume and the API-key secret are fixed below (`CATALOG`, `SCHEMA`, `VOLUME`, `SECRET_CATALOG`, `SECRET_SCHEMA`, `SECRET_NAME`).

# COMMAND ----------

# MAGIC %pip install -q "pydantic>=2"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json, os, sys

# Make `src.ingestion` importable when this notebook is run from a Git folder / Repo
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))

from src.ingestion import job

# COMMAND ----------

CATALOG, SCHEMA, VOLUME = "dev_catalog", "bronze", "vol-skilliq"
# Unity Catalog secret: <catalog>.<schema>.<name>  (needs serverless env v4+ / DBR 17.3+ and READ SECRET)
SECRET_CATALOG, SECRET_SCHEMA, SECRET_NAME = "dev_catalog", "bronze", "theirstack_api_key"

dbutils.widgets.text("payload", "")
dbutils.widgets.text("session_id", "")

if not dbutils.widgets.get("payload").strip():
    raise ValueError("`payload` parameter is required: a JSON search body, e.g. "
                     '{"posted_at_max_age_days": 7, "job_title_or": ["data engineer"]}')
payload = json.loads(dbutils.widgets.get("payload"))
volume_root = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
api_key = dbutils.secrets.get(catalog=SECRET_CATALOG, schema=SECRET_SCHEMA, key=SECRET_NAME)

if not os.path.isdir(volume_root):
    raise FileNotFoundError(f"Volume not found: {volume_root}")

# COMMAND ----------

result = job.run(payload, volume_root, api_key, dbutils.widgets.get("session_id"))
print(json.dumps(result, indent=2))

# Fail the task (so the job shows red / alerts) if the session did not succeed
if result["status"] != "succeeded":
    raise RuntimeError(f"Ingestion failed: {result['error']}")
