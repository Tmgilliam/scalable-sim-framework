"""
cloud/vertex_job.py
--------------------
Lightweight Vertex AI Custom Job wrapper.

Lets you launch `run_batch` as a Vertex AI Custom Training Job so a recruiter
(or you) can trigger cloud-scale runs with one call.

Usage (local trigger):
    python -m cloud.vertex_job \
        --project my-gcp-project \
        --region us-central1 \
        --bucket my-bucket \
        --image gcr.io/my-gcp-project/sim-framework:latest \
        --scenarios Base Stress BlackSwan \
        --seeds 42 43 44 101

The job runs `python entrypoint.py` inside your container, which should call
run_batch(...) with GCS mirroring enabled.

Requires:
    google-cloud-aiplatform  (pip install google-cloud-aiplatform)
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional


def submit_vertex_job(
    project: str,
    region: str,
    bucket: str,
    container_image_uri: str,
    job_display_name: str = "scalable-sim-batch",
    prefix: str = "sim-runs",
    scenarios: Optional[List[str]] = None,
    seeds: Optional[List[int]] = None,
    machine_type: str = "n1-standard-4",
    service_account: Optional[str] = None,
) -> str:
    """
    Submit a Vertex AI Custom Job and return its resource name.

    The container must have the sim framework installed and expose an
    entrypoint that accepts --scenarios / --seeds / --bucket / --prefix CLI args.

    Returns:
        Vertex AI job resource name (str)
    """
    try:
        from google.cloud import aiplatform  # type: ignore
    except ImportError:
        raise ImportError(
            "google-cloud-aiplatform is not installed. "
            "Run: pip install google-cloud-aiplatform"
        )

    aiplatform.init(project=project, location=region)

    # Build args list forwarded into the container
    container_args: List[str] = [
        "--bucket", bucket,
        "--prefix", prefix,
    ]
    if scenarios:
        container_args += ["--scenarios"] + scenarios
    if seeds:
        container_args += ["--seeds"] + [str(s) for s in seeds]

    worker_spec = {
        "machine_spec": {"machine_type": machine_type},
        "replica_count": 1,
        "container_spec": {
            "image_uri": container_image_uri,
            "args": container_args,
        },
    }
    if service_account:
        worker_spec["service_account"] = service_account

    job = aiplatform.CustomJob(
        display_name=job_display_name,
        worker_pool_specs=[worker_spec],
        staging_bucket=f"gs://{bucket}/vertex-staging",
    )
    job.submit()
    print(f"[Vertex] Job submitted: {job.resource_name}")
    print(f"[Vertex] Console: https://console.cloud.google.com/vertex-ai/training/custom-jobs?project={project}")
    return job.resource_name


# ---------------------------------------------------------------------------
# Container entrypoint  (run inside the Docker image on Vertex)
# ---------------------------------------------------------------------------

def _entrypoint() -> None:
    """
    Called by the container when Vertex starts the job.
    Parses CLI args, runs the batch with GCS mirroring, uploads registry.
    """
    import sys
    sys.path.insert(0, "/app")  # project root inside container

    from batch_runner import run_batch
    from cloud.gcs_mirror import make_gcs_mirror_fn, upload_registry

    p = argparse.ArgumentParser()
    p.add_argument("--bucket",    required=True)
    p.add_argument("--prefix",    default="sim-runs")
    p.add_argument("--scenarios", nargs="*", default=None)
    p.add_argument("--seeds",     nargs="*", type=int, default=None)
    args = p.parse_args()

    mirror = make_gcs_mirror_fn(bucket=args.bucket, prefix=args.prefix)
    run_batch(
        scenarios=args.scenarios,
        seeds=args.seeds,
        gcs_mirror_fn=mirror,
    )
    upload_registry("runs/registry.csv", bucket=args.bucket, prefix=args.prefix)


# ---------------------------------------------------------------------------
# CLI  (local submission)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Submit sim batch as Vertex AI Custom Job")
    p.add_argument("--project",   required=True,  help="GCP project ID")
    p.add_argument("--region",    default="us-central1")
    p.add_argument("--bucket",    required=True,  help="GCS bucket name (no gs:// prefix)")
    p.add_argument("--image",     required=True,  help="Container image URI")
    p.add_argument("--job-name",  default="scalable-sim-batch")
    p.add_argument("--prefix",    default="sim-runs")
    p.add_argument("--machine",   default="n1-standard-4")
    p.add_argument("--sa",        default=None,   help="Service account email (optional)")
    p.add_argument("--scenarios", nargs="*", default=None)
    p.add_argument("--seeds",     nargs="*", type=int, default=None)
    args = p.parse_args()

    submit_vertex_job(
        project=args.project,
        region=args.region,
        bucket=args.bucket,
        container_image_uri=args.image,
        job_display_name=args.job_name,
        prefix=args.prefix,
        scenarios=args.scenarios,
        seeds=args.seeds,
        machine_type=args.machine,
        service_account=args.sa,
    )
