"""
cloud/gcs_mirror.py
-------------------
Optional GCS upload for each run folder.

Usage:
    from cloud.gcs_mirror import make_gcs_mirror_fn
    mirror = make_gcs_mirror_fn(bucket="my-bucket", prefix="sim-runs")
    # pass mirror as gcs_mirror_fn to run_batch(...)

Requires:
    google-cloud-storage  (pip install google-cloud-storage)
    GOOGLE_APPLICATION_CREDENTIALS env var  OR  ADC via `gcloud auth application-default login`
"""
from __future__ import annotations

import os
from typing import Optional


def make_gcs_mirror_fn(bucket: str, prefix: str = "sim-runs"):
    """
    Returns a callable(run_dir: str) -> gcs_path: str
    that uploads every file in run_dir to gs://bucket/prefix/<run_id>/...
    """
    try:
        from google.cloud import storage as gcs  # type: ignore
    except ImportError:
        raise ImportError(
            "google-cloud-storage is not installed. "
            "Run: pip install google-cloud-storage"
        )

    client = gcs.Client()
    gcs_bucket = client.bucket(bucket)

    def _mirror(run_dir: str) -> str:
        run_id = os.path.basename(run_dir)
        uploaded = []
        for fname in os.listdir(run_dir):
            local_path = os.path.join(run_dir, fname)
            if not os.path.isfile(local_path):
                continue
            blob_name = f"{prefix}/{run_id}/{fname}"
            blob = gcs_bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            uploaded.append(blob_name)

        gcs_path = f"gs://{bucket}/{prefix}/{run_id}"
        print(f"  [GCS] Uploaded {len(uploaded)} file(s) -> {gcs_path}")
        return gcs_path

    return _mirror


def upload_registry(
    registry_path: str,
    bucket: str,
    prefix: str = "sim-runs",
    dest_name: str = "registry.csv",
) -> str:
    """Upload the registry CSV to GCS and return its gs:// URI."""
    try:
        from google.cloud import storage as gcs  # type: ignore
    except ImportError:
        raise ImportError("pip install google-cloud-storage")

    client = gcs.Client()
    blob = client.bucket(bucket).blob(f"{prefix}/{dest_name}")
    blob.upload_from_filename(registry_path)
    uri = f"gs://{bucket}/{prefix}/{dest_name}"
    print(f"[GCS] Registry uploaded -> {uri}")
    return uri
