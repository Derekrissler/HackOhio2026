"""Optional, lazy CPU inference of the published MiniLM ONNX model. No PyTorch.

Only public model artifacts may be downloaded on explicit opt-in. Excerpt text
is processed locally. Embedding cache is bounded, in-memory, and keyed by hashes.
"""

from collections import OrderedDict
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
from typing import Protocol

import numpy as np
from pydantic import Field

from .contracts import Contract

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
MODEL_FILE = "onnx/model.onnx"


class EmbeddingUnavailable(RuntimeError):
    """A sanitized reason code; never include a source excerpt or credentials."""


class EmbeddingMetadata(Contract):
    model_id: str
    revision: str
    backend: str
    dimensions: int = Field(gt=0)
    pooling: str
    normalization: str
    max_tokens: int = Field(gt=0)
    artifact_sha256: dict[str, str]
    package_versions: dict[str, str]


class EmbeddingProvider(Protocol):
    @property
    def metadata(self) -> EmbeddingMetadata: ...

    def encode(self, texts: list[str]) -> np.ndarray: ...


class MiniLMOnnxEmbedder:
    def __init__(self, cache_dir: Path, *, local_files_only=True, batch_size=16, cache_size=512):
        if batch_size < 1 or cache_size < 0:
            raise ValueError("invalid embedding batch/cache size")
        self.cache_dir = Path(cache_dir)
        self.local_files_only = local_files_only
        self.batch_size, self.cache_size = batch_size, cache_size
        self._session = self._tokenizer = self._metadata = None
        self._cache = OrderedDict()

    @property
    def metadata(self):
        self._load()
        return self._metadata

    def _load(self):
        if self._session is not None:
            return
        try:
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer
        except ImportError:
            raise EmbeddingUnavailable("embedding_dependencies_unavailable") from None
        try:
            paths = {
                name: Path(hf_hub_download(
                    repo_id=MODEL_ID, filename=name, revision=MODEL_REVISION,
                    cache_dir=str(self.cache_dir), local_files_only=self.local_files_only, token=False,
                )) for name in (MODEL_FILE, "tokenizer.json")
            }
            tokenizer = Tokenizer.from_file(str(paths["tokenizer.json"]))
            tokenizer.enable_truncation(max_length=256)
            tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
            options = ort.SessionOptions()
            options.intra_op_num_threads = options.inter_op_num_threads = 1
            session = ort.InferenceSession(str(paths[MODEL_FILE]), sess_options=options,
                                           providers=["CPUExecutionProvider"])
            outputs = session.get_outputs()
            if len(outputs[0].shape) != 3 or outputs[0].shape[-1] != 384:
                raise ValueError("unsupported model output")
            metadata = EmbeddingMetadata(
                model_id=MODEL_ID, revision=MODEL_REVISION, backend="onnxruntime_cpu",
                dimensions=384, pooling="attention_mask_mean_v1", normalization="l2",
                max_tokens=256,
                artifact_sha256={name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()},
                package_versions={name: version(name) for name in (
                    "onnxruntime", "tokenizers", "huggingface-hub", "numpy",
                )},
            )
            self._tokenizer, self._session, self._metadata = tokenizer, session, metadata
        except Exception:
            raise EmbeddingUnavailable("model_missing_or_unloadable") from None

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
        self._load()
        fingerprint = self.metadata.model_dump_json()
        vectors = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start:start + self.batch_size]
            keys = [hashlib.sha256(json.dumps([fingerprint, text]).encode()).hexdigest() for text in batch]
            missing = sorted({key: text for key, text in zip(keys, batch) if key not in self._cache}.items())
            fresh = {}
            if missing:
                try:
                    encoded = self._tokenizer.encode_batch([text for _, text in missing])
                    if any(item.overflowing for item in encoded):
                        raise EmbeddingUnavailable("text_token_limit_exceeded")
                    feeds = {
                        "input_ids": np.asarray([item.ids for item in encoded], dtype=np.int64),
                        "attention_mask": np.asarray([item.attention_mask for item in encoded], dtype=np.int64),
                        "token_type_ids": np.asarray([item.type_ids for item in encoded], dtype=np.int64),
                    }
                    inputs = {item.name: feeds[item.name] for item in self._session.get_inputs()}
                    tokens = self._session.run(None, inputs)[0]
                    mask = feeds["attention_mask"][..., None].astype(np.float32)
                    pooled = (tokens * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
                    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
                    if not np.isfinite(pooled).all() or (norms <= 0).any():
                        raise EmbeddingUnavailable("invalid_model_output")
                    fresh = {key: vector for (key, _), vector in zip(missing, pooled / norms)}
                except EmbeddingUnavailable:
                    raise
                except Exception:
                    raise EmbeddingUnavailable("embedding_inference_failed") from None
            for key in keys:
                vector = fresh[key] if key in fresh else self._cache[key]
                vectors.append(vector.copy())
            for key, vector in fresh.items():
                self._cache[key] = vector.copy()
            for key in keys:
                if key in self._cache:
                    self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return np.asarray(vectors, dtype=np.float32)
