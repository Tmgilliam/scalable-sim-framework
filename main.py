#!/usr/bin/env python
"""
main.py
-------
Local entrypoint for the Scalable Simulation Framework.

Examples
--------
# Run all scenarios, seeds 42-44, no GCS
python main.py

# Run specific scenarios
python main.py --scenarios Stress BlackSwan --seeds 42 99

# Run with GCS mirroring (requires google-cloud-storage + credentials)
python main.py --bucket my-bucket --prefix sim-runs

# Submit to Vertex AI (requires google-cloud-aiplatform)
python main.py --vertex \
    --project my-gcp-project \
    --bucket my-bucket \
    --image gcr.io/my-gcp-project/sim-framework:latest
"""

import argparse
import sys


def main():
    p = argparse.ArgumentParser(description="Scalable Sim Framework - local runner")
    p.add_argument("--scenarios",   nargs="*", default=None,
                   help="Scenario names to run (default: all)")
    p.add_argument("--seeds",       nargs="*", type=int, default=None,
                   help="Seeds (default: 42 43 44)")
    p.add_argument("--catalog",     default="scenarios/catalog.yaml",
                   help="Path to scenario catalog YAML")

    # GCS options
    p.add_argument("--bucket",  default=None,
                   help="GCS bucket name to mirror each run (omit to skip)")
    p.add_argument("--prefix",  default="sim-runs",
                   help="GCS prefix/folder (default: sim-runs)")

    # Vertex AI submission
    p.add_argument("--vertex",   action="store_true",
                   help="Submit batch as Vertex AI Custom Job instead of running locally")
    p.add_argument("--project",  default=None, help="GCP project (required for --vertex)")
    p.add_argument("--region",   default="us-central1")
    p.add_argument("--image",    default=None,
                   help="Container image URI (required for --vertex)")
    p.add_argument("--machine",  default="n1-standard-4")
    p.add_argument("--job-name", default="scalable-sim-batch")

    args = p.parse_args()

    # --- Vertex submission path ---
    if args.vertex:
        if not args.project or not args.bucket or not args.image:
            print("[ERROR] --vertex requires --project, --bucket, and --image")
            sys.exit(1)
        from cloud.vertex_job import submit_vertex_job
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
        )
        return

    # --- Local batch path ---
    gcs_mirror_fn = None
    if args.bucket:
        from cloud.gcs_mirror import make_gcs_mirror_fn, upload_registry
        gcs_mirror_fn = make_gcs_mirror_fn(bucket=args.bucket, prefix=args.prefix)

    from batch_runner import run_batch
    run_batch(
        catalog_path=args.catalog,
        scenarios=args.scenarios,
        seeds=args.seeds,
        gcs_mirror_fn=gcs_mirror_fn,
    )

    if args.bucket and gcs_mirror_fn is not None:
        upload_registry("runs/registry.csv", bucket=args.bucket, prefix=args.prefix)


if __name__ == "__main__":
    main()
