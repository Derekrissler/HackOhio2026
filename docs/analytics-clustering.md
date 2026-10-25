# Phase 5: optional semantic grouping

This describes the original engine. The current input/review, publication and UI
workflow is in [analytics-error-integration.md](analytics-error-integration.md).

The statistical engine is unchanged. Clustering is a separate optional CPU path:

```
validated LERs + explicitly approved error excerpts
  -> prepare_error_texts
  -> local MiniLM ONNX embeddings
  -> DBSCAN cosine clusters / noise / unavailable result
```

No routes, live data retrieval, migrations, database writes, ARR generation or UI
integration are added. Outputs are restricted internal evidence-bearing DTOs;
representative excerpts and learner/source IDs must not be served directly to
unauthorized dashboards. Existing Supabase authorization and aggregate suppression
must be applied at the later delivery boundary.

## Runtime decision

The `sentence-transformers` package itself requires `torch`, including with its
ONNX extra. To respect the project's exclusion, this implementation uses the
Sentence Transformers **published model artifact**, not its Python package:

- Model: `sentence-transformers/all-MiniLM-L6-v2`, Apache-2.0.
- Immutable revision: `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
- Files: `onnx/model.onnx` and `tokenizer.json` from that revision.
- CPU ONNX Runtime; one intra/inter-op thread; no training or export step.
- Attention-mask mean pooling, then L2 normalization; 384 dimensions.
- Maximum 256 tokens including special tokens. Overlong excerpts produce a
  sanitized unavailable reason; the code does not silently analyze truncated text.

Optional versions evaluated on Python 3.14.7 are pinned in
`apps/api/requirements-clustering.txt`: scikit-learn 1.9.1, ONNX Runtime 1.31.0,
tokenizers 0.23.3 and huggingface-hub 1.33.0. Core statistics do not import these
packages. The isolated inference environment has no PyTorch installed.

Sources: [Sentence Transformers dependencies](https://github.com/huggingface/sentence-transformers/blob/master/pyproject.toml),
[model card and pooling](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
[ONNX Runtime Python](https://onnxruntime.ai/docs/get-started/with-python.html),
[DBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html).

## Text input

Use `ApprovedErrorText` from `app.analytics.text_preparation`:

```python
ApprovedErrorText(
    ler_id=ler_uuid,
    error_code="inequality_direction",
    text="The inequality sign is reversed in this constraint.",
    source_kind="instructor_feedback",  # or error_description
    evidence_ref_ids=[source_evidence_uuid],
    privacy_reviewed=True,
)
```

The caller must supply a short error-specific excerpt and explicitly attest that
it has been reviewed for unnecessary personal information. This is not automated
PII detection. Names, emails, student answers and whole submissions must not be
copied into excerpts without review. The adapter does not mine `lers.payload` or
automatically trust AI misconception text. Excerpt references must belong to the
accepted error event's original evidence.

`prepare_error_texts(records, excerpts, config, period)` reuses Phase 3 eligibility,
supersession, deduplication, classification/review policy and period selection.
Independent graded evidence uses primary error selection; practice uses distinct
eligible attempts. Assisted/unknown graded assessments are excluded from this MVP
clustering path. Practice remains partitioned by origin and assistance.

Whitespace and Unicode NFC normalization preserve case, negations and mathematical
symbols. At most one excerpt per LER/error code is selected (shortest then lexical
order); references are preserved. Stable text IDs hash LER, code and normalized
text. Exclusions contain IDs/reason codes, not rejected excerpt text.

## Local inference and caching

Install the optional requirements in the application's environment. The first
download is explicit; normal construction and imports do not download anything:

```python
from pathlib import Path
from app.analytics.embeddings import MiniLMOnnxEmbedder

# Run once to obtain public artifacts; no student text is sent to Hugging Face.
encoder = MiniLMOnnxEmbedder(Path("../../.cache/analytics-models"), local_files_only=False)
metadata = encoder.metadata

# Normal operation is offline/local-cache-only by default.
encoder = MiniLMOnnxEmbedder(Path("../../.cache/analytics-models"))
```

Paths above assume execution from `apps/api`. `.cache/` is gitignored. Public model
requests explicitly disable auth tokens; no project secret is used. Model caching
is on disk; excerpt embeddings use a bounded in-memory LRU (512 entries), keyed by
model/tokenizer hashes, preprocessing/runtime metadata, and a text hash. Raw text
is not written to this cache. Cache clearing/retention beyond process lifetime is
not implemented because vectors are not persisted.

## Grouping policy and provenance

```python
from app.analytics.clustering import discover_misconceptions
from app.analytics.text_preparation import prepare_error_texts

prepared = prepare_error_texts(records, approved_excerpts, config)
result = discover_misconceptions(
    prepared, run_id=run_uuid, embedder=encoder, config=config,
)
```

Partition by course, assessment origin and assistance. Require at least six
distinct LER observations in each partition; otherwise return unassigned items
without loading a model. DBSCAN uses cosine distances, `min_samples=3` and default
`eps=0.25`. No number of clusters is specified. Groups backed by fewer than three
distinct LERs are rejected even if multiple error tags appear in one LER. A default
2,000-text partition cap bounds the quadratic distance-matrix allocation; oversized
partitions are reported rather than silently sampled.

Results retain member assignments (including noise), run-local cluster IDs,
distinct evidence/student/question counts, explicit outcomes, source references,
an existing representative error code and a medoid excerpt selected from members.
IDs are not permanent semantic category identities across runs. Mean pairwise
cosine similarity is descriptive cohesion, not confidence or proof of a shared
misconception. Silhouette is computed only for 2..n-1 clusters among non-noise
observations. Insufficient data, missing optional packages/models and invalid
vectors have explicit statuses. There is no fabricated embedding fallback.

Run metadata includes an input/config/model/runtime snapshot hash, model revision,
artifact SHA-256 digests, package versions and timestamp. Assignment order is stable
under input permutations. Run ID/time are separated from the content hash.
The model artifacts observed in verification were:

```
onnx/model.onnx  6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452
tokenizer.json   be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037
```

## Evaluation and limits

Unit tests use explicit vectors to verify grouping mechanics separately from
language-model quality. The opt-in real-model test uses seven fictional comments:
three inequality-direction errors, three meter/centimeter conversion errors and
one bibliography error. Observed threshold sensitivity:

| Cosine-distance epsilon | Cluster sizes | Noise | Non-noise silhouette |
|---|---|---|---|
| 0.25 (default) | 3 | 4 | null |
| 0.35 | 3, 3 | 1 | about 0.6853 |
| 0.45 | 3, 3 | 1 | about 0.6853 |

At 0.35, the intended groups formed separately and the unrelated bibliography
comment remained noise. The more conservative 0.25 default is retained. This tiny
synthetic evaluation is not validation on course data; tune thresholds on reviewed,
authorized examples and examine chaining/false mergers and sensitivity. The model
is general English and can miss mathematical or domain-specific distinctions.

Normal tests never download models. To run the real-model evaluation after an
explicit download, from `apps/api` in PowerShell:

```powershell
$env:ANALYTICS_MODEL_CACHE = (Resolve-Path '../../.cache/analytics-models').Path
python -m pytest --confcutdir tests/analytics tests/analytics/test_clustering_model.py -q -s
```

When `ANALYTICS_MODEL_CACHE` is unset this test is skipped. Statistical analytics
continue to function even when semantic analysis is unavailable. Phase 6 maps
internal results to versioned ARRs; the integration guide describes the required
text and cluster interpretation reviews for new live ML publication.
