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
    for name in ("readiness", "analyze"):
        command = commands.add_parser(name)
        command.add_argument("--course", type=UUID, required=True)
        command.add_argument("--input", type=Path, help="offline fictional envelope array; no database connection")
        command.add_argument("--config", type=Path)
        command.add_argument("--period-start")
        command.add_argument("--period-end")
        if name == "analyze":
            command.add_argument("--save-bundle", action="store_true")
            command.add_argument("--cluster", action="store_true")
            command.add_argument("--excerpts", type=Path, help="explicitly approved excerpt array")
            command.add_argument("--model-cache", type=Path)
    publish = commands.add_parser("publish")
    publish.add_argument("--bundle", type=Path, required=True)
    publish.add_argument("--exclusive-course-access", action="store_true",
                         help="attest that ingestion and metadata writers are paused/serialized for this course")
    args = parser.parse_args(argv)
    try:
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
        if bool(args.period_start) != bool(args.period_end):
            raise ValueError("both period bounds are required")
        period = AnalysisPeriod(start=args.period_start, end=args.period_end) if args.period_start else None
        if args.input:
            source = FileEvidenceSource(args.input)
        else:
            from .repository import SupabaseAnalysisRepository
            from .supabase_clients import create_pipeline_client
            source = SupabaseAnalysisRepository(create_pipeline_client())
        if args.command == "readiness":
            print(check_readiness(source, args.course, config, period).model_dump_json(indent=2))
            return 0
        excerpts, embedder = [], None
        if args.excerpts:
            from .text_preparation import ApprovedErrorText
            excerpts = [ApprovedErrorText.model_validate(row) for row in json.loads(args.excerpts.read_text(encoding="utf-8"))]
        if args.model_cache:
            from .embeddings import MiniLMOnnxEmbedder
            embedder = MiniLMOnnxEmbedder(args.model_cache)  # offline only; never auto-download
        bundle = analyze_course(source, args.course, config=config, period=period, cluster=args.cluster,
                                approved_excerpts=excerpts, embedder=embedder)
        output = {"run_id": str(bundle.run_id), "input_snapshot": bundle.input_snapshot,
                  "readiness": bundle.readiness.model_dump(), "arr_count": len(bundle.documents), "persisted": False}
        if args.save_bundle:
            folder = Path(__file__).resolve().parents[4] / "data" / "analytics-runs"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{bundle.run_id}.json"
            with path.open("x", encoding="utf-8") as handle:
                handle.write(bundle.model_dump_json(indent=2))
            output["private_bundle"] = str(path)
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
