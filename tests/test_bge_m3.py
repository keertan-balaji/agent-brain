"""BGE-M3 dense embedding: shape, determinism, batching."""

import numpy as np

from brain.embed.bge_m3 import BgeM3Embedder, embed_texts


def test_embed_single_text_returns_1024d(bge_m3_embedder: BgeM3Embedder) -> None:
    vec = bge_m3_embedder.embed_one("hello world")
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (1024,)
    assert vec.dtype in (np.float32, np.float16)


def test_embed_is_deterministic(bge_m3_embedder: BgeM3Embedder) -> None:
    a = bge_m3_embedder.embed_one("identical input")
    b = bge_m3_embedder.embed_one("identical input")
    np.testing.assert_allclose(a, b, rtol=1e-5)


def test_embed_batch_matches_singletons(bge_m3_embedder: BgeM3Embedder) -> None:
    inputs = ["alpha", "beta", "gamma"]
    batch = bge_m3_embedder.embed_many(inputs)
    assert batch.shape == (3, 1024)
    for i, txt in enumerate(inputs):
        singleton = bge_m3_embedder.embed_one(txt)
        np.testing.assert_allclose(batch[i], singleton, rtol=1e-4)


def test_module_level_embed_texts_helper(bge_m3_embedder: BgeM3Embedder) -> None:
    result = embed_texts(["x", "y"], embedder=bge_m3_embedder)
    assert result.shape == (2, 1024)


def test_model_id_and_ver_accessors(bge_m3_embedder: BgeM3Embedder) -> None:
    assert bge_m3_embedder.model_id == "bge-m3"
    assert bge_m3_embedder.model_ver
    assert bge_m3_embedder.dim == 1024
