import json
import os

CONTRACT = os.path.join("electron-spike", "contracts", "electron-bridge-contract.json")

with open(CONTRACT, "r", encoding="utf-8") as f:
    data = json.load(f)

ops = data["operations"]
existing = {op["name"] for op in ops}

new_ops = [
    {
        "direction": "command",
        "event_fields": [],
        "mapped_to": "import_videos",
        "name": "import_videos",
        "notes": "Multi-file import: registers several videos as jobs in one call.",
        "phase8": "qol multi-import",
        "production_core": False,
        "request_fields": ["paths"],
        "request_id_required": False,
        "response_fields": ["ok", "jobs", "failures"],
        "status": "IMPLEMENTED"
    },
    {
        "direction": "command",
        "event_fields": [],
        "mapped_to": "apply_job_settings",
        "name": "apply_job_settings",
        "notes": "Applies shared output mode and quality preset to a batch of jobs.",
        "phase8": "qol multi-import",
        "production_core": False,
        "request_fields": ["job_ids", "mode", "preset"],
        "request_id_required": False,
        "response_fields": ["ok", "applied"],
        "status": "IMPLEMENTED"
    },
    {
        "direction": "command",
        "event_fields": [],
        "mapped_to": "queue_jobs",
        "name": "queue_jobs",
        "notes": "Queues a batch of jobs for processing.",
        "phase8": "qol multi-import",
        "production_core": False,
        "request_fields": ["job_ids"],
        "request_id_required": False,
        "response_fields": ["ok", "count"],
        "status": "IMPLEMENTED"
    },
    {
        "direction": "command",
        "event_fields": [],
        "mapped_to": "search_transcripts",
        "name": "search_transcripts",
        "notes": "Global transcript search across all lectures.",
        "phase8": "qol transcript search",
        "production_core": False,
        "request_fields": ["query", "limit"],
        "request_id_required": False,
        "response_fields": ["ok", "results"],
        "status": "IMPLEMENTED"
    },
    {
        "direction": "event",
        "event_fields": ["event", "jobs"],
        "mapped_to": "batch_import",
        "name": "batch_import",
        "notes": "Reports a completed multi-file import with the created jobs.",
        "phase8": "qol multi-import",
        "production_core": False,
        "request_fields": [],
        "request_id_required": False,
        "response_fields": [],
        "status": "IMPLEMENTED"
    }
]

for op in new_ops:
    if op["name"] not in existing:
        ops.append(op)

with open(CONTRACT, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")

print("Added", len([o for o in new_ops if o["name"] not in existing]), "operations; total now", len(ops))