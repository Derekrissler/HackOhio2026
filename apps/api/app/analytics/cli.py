"""Readiness/dry runs by default. Publication is a separate explicit command."""

import argparse
import json
from pathlib import Path
from uuid import UUID

from .config import AnalyticsConfig
from .contracts import AnalysisPeriod
from .evidence_repository import EvidenceBatch, RepositoryError
from .service import AnalysisBundle, analyze_course, check_readiness, persist_analysis


class FileEvidenceSource:
    source_kind = "offline_fixture"

    def __init__(self, path):
        self.path = Path(path)

    def load_course(self, course_id):
        envelopes = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(envelopes, list):
            raise ValueError("input file must contain an array of joined LER envelopes")
        return EvidenceBatch(course_id=course_id, envelopes=envelopes,
                             source_manifest={"lers": [row.get("ler", {}) for row in envelopes]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("courses", help="read-only discovery of course UUIDs and Canvas IDs")
    repair = commands.add_parser('repair-plan', help='private source-grounded evidence repair preview; no database writes')
    repair.add_argument('--course', type=UUID, required=True)
    repair.add_argument('--review', type=Path, help='completed private review packet or decisions object')
    repair.add_argument('--output', type=Path, required=True)
    apply = commands.add_parser('repair-apply', help='apply the exact reviewed repair plan; creates LER revisions')
    apply.add_argument('--plan', type=Path, required=True)
    apply.add_argument('--exclusive-course-access', action='store_true')
    for name in ("readiness", "analyze"):
        command = commands.add_parser(name)
        command.add_argument("--course", type=UUID, required=True)
        command.add_argument("--input", type=Path, help="offline fictional envelope array; no database connection")
        command.add_argument("--config", type=Path)
        command.add_argument("--period-start")
        command.add_argument("--period-end")
        command.add_argument("--cluster", action="store_true")
        command.add_argument("--excerpts", type=Path, help="versioned reviewed export; legacy arrays for dry runs")
        command.add_argument("--model-cache", type=Path)
        if name == "analyze":
            command.add_argument("--save-bundle", action="store_true")
            command.add_argument("--cluster-review", type=Path, help="completed group-review manifest")
    publish = commands.add_parser("publish")
    publish.add_argument("--bundle", type=Path, required=True)
    publish.add_argument("--exclusive-course-access", action="store_true",
                         help="attest that ingestion and metadata writers are paused/serialized for this course")
    args = parser.parse_args(argv)
    try:
        if args.command in ('repair-plan', 'repair-apply'):
            from .source_repairs import RepairPlan, apply_plan, build_plan, read_source, review_packet
            from .supabase_clients import create_pipeline_client
            client = create_pipeline_client()
            if args.command == 'repair-apply':
                plan = RepairPlan.model_validate_json(args.plan.read_text(encoding='utf-8'))
                result = apply_plan(client, plan, exclusive_course_access=args.exclusive_course_access)
                if plan.reviewed_excerpts:
                    from .reviewed_excerpts import ReviewedExcerptExport
                    export = ReviewedExcerptExport(schema_version='1.0',course_id=plan.course_id,
                        extraction_version=plan.method,reviewer_ref=plan.review.reviewer_ref,
                        reviewed_at=plan.review.reviewed_at,review_revision=str(plan.id),entries=plan.reviewed_excerpts)
                    private_root = Path(__file__).resolve().parents[4] / 'data' / 'analytics-runs'
                    private_root.mkdir(parents=True,exist_ok=True)
                    path = private_root / (str(plan.id)+'.reviewed-excerpts.json')
                    if path.exists() and path.read_text(encoding='utf-8') != export.model_dump_json(indent=2):
                        raise ValueError('reviewed excerpt export conflict')
                    if not path.exists():
                        with path.open('x',encoding='utf-8') as handle:
                            handle.write(export.model_dump_json(indent=2))
                    result['private_reviewed_excerpts'] = str(path)
                print(json.dumps(result,indent=2))
            else:
                review = json.loads(args.review.read_text(encoding='utf-8')) if args.review else None
                if review and 'decisions' in review:
                    review = review['decisions']
                plan = build_plan(read_source(client, args.course), review)
                # Private source/feedback text must stay in the ignored operator area.
                private_root = Path(__file__).resolve().parents[4] / 'data' / 'analytics-runs'
                output = args.output.resolve()
                if not output.is_relative_to(private_root.resolve()):
                    raise ValueError('repair exports belong under data/analytics-runs')
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open('x',encoding='utf-8') as handle:
                    handle.write(plan.model_dump_json(indent=2))
                packet_path = output.with_name(output.stem + '.review.json')
                with packet_path.open('x',encoding='utf-8') as handle:
                    handle.write(json.dumps(review_packet(plan),indent=2,ensure_ascii=False))
                print(json.dumps(plan.summary() | {'private_plan':str(output),'private_review_packet':str(packet_path)},indent=2))
            return 0
        if args.command == "courses":
            from .evidence_repository import read_pages
            from .supabase_clients import create_pipeline_client
            rows = read_pages(create_pipeline_client(), "courses", "id,code,canvas_id")
            print(json.dumps({"courses": rows}, indent=2))
            return 0
        if args.command == "publish":
            bundle = AnalysisBundle.model_validate_json(args.bundle.read_text(encoding="utf-8"))
            if not args.exclusive_course_access or bundle.source_kind != "supabase":
                raise ValueError("publication preconditions not met")
            from .repository import SupabaseAnalysisRepository
            from .supabase_clients import create_pipeline_client
            status = persist_analysis(SupabaseAnalysisRepository(create_pipeline_client()), bundle,
                                      exclusive_course_access=True)
            print(json.dumps({"run_id": str(bundle.run_id), "status": status}))
            return 0
        config = AnalyticsConfig.model_validate_json(args.config.read_text(encoding="utf-8")) if args.config else AnalyticsConfig()
        if not args.cluster and (args.excerpts or args.model_cache or getattr(args, 'cluster_review', None)):
            raise ValueError("clustering options require --cluster")
        if bool(args.period_start) != bool(args.period_end):
            raise ValueError("both period bounds are required")
        period = AnalysisPeriod(start=args.period_start, end=args.period_end) if args.period_start else None
        if args.input:
            source = FileEvidenceSource(args.input)
        else:
            from .repository import SupabaseAnalysisRepository
            from .supabase_clients import create_pipeline_client
            source = SupabaseAnalysisRepository(create_pipeline_client())
        excerpts, embedder, reviewed_export = [], None, None
        if args.excerpts:
            from .text_preparation import ApprovedErrorText
            payload = json.loads(args.excerpts.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                from .reviewed_excerpts import ReviewedExcerptExport
                reviewed_export = ReviewedExcerptExport.model_validate(payload)
            else:
                excerpts = [ApprovedErrorText.model_validate(row) for row in payload]
        if args.model_cache:
            from .embeddings import MiniLMOnnxEmbedder
            embedder = MiniLMOnnxEmbedder(args.model_cache)  # offline only; never auto-download
        if args.command == "readiness":
            if not args.cluster:
                print(check_readiness(source, args.course, config, period).model_dump_json(indent=2))
            else:
                from .service import _adapt
                from .ml_readiness import ml_readiness
                batch = source.load_course(args.course)
                records, _, report = _adapt(batch, config, period)
                if reviewed_export:
                    excerpts = reviewed_export.approved_inputs(records, batch, live=source.source_kind == "supabase")
                print(json.dumps({"statistics": report.model_dump(), "clustering": ml_readiness(records, excerpts, config, period, embedder)}, indent=2))
            return 0
        review = None
        if args.cluster_review:
            from .cluster_review import ClusterReview
            review = ClusterReview.model_validate_json(args.cluster_review.read_text(encoding="utf-8"))
        bundle = analyze_course(source, args.course, config=config, period=period, cluster=args.cluster,
                                approved_excerpts=excerpts, embedder=embedder, reviewed_export=reviewed_export, cluster_review=review)
        output = {"run_id": str(bundle.run_id), "input_snapshot": bundle.input_snapshot,
                  "readiness": bundle.readiness.model_dump(), "arr_count": len(bundle.documents), "persisted": False}
        if args.cluster:
            output["clustering"] = [{"status": p["status"], "reason": p["reason"], "groups": len(p["groups"]), "noise": p["noise_count"]} for p in bundle.clustering_report["partitions"]]
            output["reviewed_for_publication"] = review is not None and reviewed_export is not None
        if args.save_bundle:
            folder = Path(__file__).resolve().parents[4] / "data" / "analytics-runs"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{bundle.run_id}.json"
            with path.open("x", encoding="utf-8") as handle:
                handle.write(bundle.model_dump_json(indent=2))
            output["private_bundle"] = str(path)
            if args.cluster:
                review_path = path.with_name(path.stem + '.cluster-review.json')
                with review_path.open('x', encoding='utf-8') as handle:
                    handle.write(json.dumps(bundle.manifest['cluster_review_template'], indent=2))
                output["cluster_review_template"] = str(review_path)
        print(json.dumps(output, indent=2))
        return 0
    except RepositoryError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, ImportError):
        # Never print Pydantic input dumps, raw database messages or env values.
        print(json.dumps({"error": "invalid_input_or_unavailable_configuration"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
