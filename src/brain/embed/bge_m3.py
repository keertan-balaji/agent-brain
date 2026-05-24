"""BGE-M3 dense embedder. Phase 2 ships dense-only; sparse + ColBERT in Phase 3c.

Implementation note
-------------------
The plan calls for a FastEmbed wrapper, but BGE-M3 is not in FastEmbed's
``TextEmbedding`` registry at any version >= 0.7. FastEmbed's only path to
BGE-M3 (``add_custom_model``) assumes a single-output ONNX with CLS pooling,
which is incompatible with BGE-M3's tri-output ONNX (dense + sparse + ColBERT).

We therefore call ``onnxruntime`` directly against ``aapot/bge-m3-onnx`` — the
community-standard tri-output export — and read only the ``dense_vecs`` head.
The output is already L2-normalized inside the graph. Dependencies stay the
same (``onnxruntime``, ``tokenizers``, ``huggingface_hub``) because FastEmbed
pulls them transitively — and FastEmbed itself remains in the dep list for
the sparse + ColBERT legs added in Phase 3c.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer


class BgeM3Embedder:
    """Direct-ONNX wrapper around BGE-M3's dense head.

    Lazy-downloads the ONNX weights on first use (~2.3 GB combined).
    Subsequent instantiations reuse the local Hugging Face cache.
    """

    MODEL_ID = "bge-m3"
    MODEL_VER = "2024-06"
    DIM = 1024

    _HF_REPO = "aapot/bge-m3-onnx"
    _MODEL_FILE = "model.onnx"
    _MODEL_DATA_FILE = "model.onnx.data"
    _TOKENIZER_FILE = "tokenizer.json"
    _DENSE_OUTPUT_NAME = "dense_vecs"
    _PAD_ID = 1  # XLM-RoBERTa <pad>
    _PAD_TOKEN = "<pad>"

    def __init__(self) -> None:
        model_path = self._download(self._MODEL_FILE)
        # Side-file for ONNX external-data; downloaded but not passed to session.
        self._download(self._MODEL_DATA_FILE)
        tok_path = self._download(self._TOKENIZER_FILE)

        self._tokenizer: Tokenizer = Tokenizer.from_file(tok_path)
        self._tokenizer.enable_padding(pad_id=self._PAD_ID, pad_token=self._PAD_TOKEN)
        self._tokenizer.enable_truncation(max_length=8192)

        self._session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )

    @staticmethod
    def _download(filename: str) -> str:
        path: str = hf_hub_download(BgeM3Embedder._HF_REPO, filename)
        # huggingface_hub returns a string path; normalize via Path for safety.
        return str(Path(path))

    @property
    def model_id(self) -> str:
        return self.MODEL_ID

    @property
    def model_ver(self) -> str:
        return self.MODEL_VER

    @property
    def dim(self) -> int:
        return self.DIM

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Sequence[str]) -> np.ndarray:
        encodings = self._tokenizer.encode_batch(list(texts))
        input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        (dense,) = self._session.run(
            [self._DENSE_OUTPUT_NAME],
            {"input_ids": input_ids, "attention_mask": attention_mask},
        )
        return np.asarray(dense, dtype=np.float32)


def embed_texts(texts: Sequence[str], *, embedder: BgeM3Embedder) -> np.ndarray:
    """Module-level helper. Caller provides the embedder (injectable for tests)."""
    return embedder.embed_many(texts)
