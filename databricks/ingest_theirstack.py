# Databricks notebook source
# MAGIC %md
# MAGIC # TheirStack → Volume ingestion
# MAGIC One run = one session = one new folder: `/Volumes/<catalog>/<schema>/<volume>/session_id=<id>/`
# MAGIC
# MAGIC **Job parameters**
# MAGIC - `payload` – JSON search body (any TheirStack filter + `limit`), same shape the frontend sends
# MAGIC - `catalog` / `schema` / `volume` – target volume
# MAGIC - `secret_scope` / `secret_key` – where the TheirStack API key lives
# MAGIC - `session_id` – optional; blank = generate one

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

dbutils.widgets.text("payload", json.dumps({
    "posted_at_max_age_days": 1,
    "job_location_or": [{"id": 6251999}],   # Canada
    "job_title_or": ["Data Engineer", "Data Architect", "AI Engineer"],
    "limit": 100,
}))
dbutils.widgets.text("catalog", "dev_catalog")
dbutils.widgets.text("schema", "landing")        # TODO confirm: schema that holds the `skillediq` volume
dbutils.widgets.text("volume", "skillediq")
dbutils.widgets.text("secret_scope", "theirstack")
dbutils.widgets.text("secret_key", "api_key")
dbutils.widgets.text("session_id", "")

payload = json.loads(dbutils.widgets.get("payload"))
volume_root = "/Volumes/{}/{}/{}".format(*(dbutils.widgets.get(k) for k in ("catalog", "schema", "volume")))
api_key = dbutils.secrets.get(dbutils.widgets.get("secret_scope"), dbutils.widgets.get("secret_key"))

if not os.path.isdir(volume_root):
    raise FileNotFoundError(f"Volume not found: {volume_root} — check the catalog/schema/volume parameters")

# COMMAND ----------

result = job.run(payload, volume_root, api_key, dbutils.widgets.get("session_id"))
print(json.dumps(result, indent=2))

# Fail the task (so the job shows red / alerts) if the session did not succeed
if result["status"] != "succeeded":
    raise RuntimeError(f"Ingestion failed: {result['error']}")
