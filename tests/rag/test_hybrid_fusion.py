"""Unit tests for Reciprocal Rank Fusion (RRF)."""

from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.rag.hybrid_fusion import reciprocal_rank_fusion


def create_doc(doc_id: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=doc_id,
        text_content=f"Content for {doc_id}",
        metadata=ChunkMetadata(
            document_id=f"doc_{doc_id}",
            category="general",
            document_name="Doc Name",
        ),
    )


def test_rrf_combines_and_boosts_intersecting_documents():
    # docA is rank 1 in dense, rank 2 in lexical
    # docB is rank 2 in dense, absent in lexical
    # docC is absent in dense, rank 1 in lexical
    docA = create_doc("docA")
    docB = create_doc("docB")
    docC = create_doc("docC")

    dense = [docA, docB]
    lexical = [docC, docA]

    fused = reciprocal_rank_fusion(dense, lexical, k=60, top_n=10)

    # docA score: 1/(60+1) + 1/(60+2) = 1/61 + 1/62 = 0.01639 + 0.01613 = 0.03252
    # docC score: 1/(60+1) = 1/61 = 0.01639
    # docB score: 1/(60+2) = 1/62 = 0.01613
    assert len(fused) == 3
    assert fused[0].id == "docA"
    assert fused[1].id == "docC"
    assert fused[2].id == "docB"
    assert fused[0].score > fused[1].score > fused[2].score


def test_rrf_truncates_to_top_n():
    dense = [create_doc(f"dense_{i}") for i in range(10)]
    lexical = [create_doc(f"lexical_{i}") for i in range(10)]

    fused = reciprocal_rank_fusion(dense, lexical, k=60, top_n=5)
    assert len(fused) == 5


def test_rrf_empty_inputs():
    assert reciprocal_rank_fusion([], []) == []
    doc = create_doc("single")
    assert len(reciprocal_rank_fusion([doc], [])) == 1
