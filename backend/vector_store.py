import os
import json
import chromadb
from chromadb import EmbeddingFunction
from langchain_upstage import UpstageEmbeddings
from pathlib import Path

CHROMA_DATA_DIR = Path(__file__).parent / "chroma_data"
COLLECTION_NAME = "mentorings"

# Upstage Embeddings 래퍼
class UpstageChromaEmbedding(EmbeddingFunction):
    def __init__(self):
        self.underlying_embeddings = UpstageEmbeddings(
            model="solar-embedding-1-large",
            api_key=os.environ.get("UPSTAGE_API_KEY", "")
        )

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.underlying_embeddings.embed_documents(input)

    @staticmethod
    def name() -> str:
        return "upstage-solar"

_client = None

def get_chroma_client() -> chromadb.ClientAPI:
    global _client
    if _client is not None:
        return _client
    _client = chromadb.PersistentClient(path=str(CHROMA_DATA_DIR))
    return _client

def _get_collection():
    client = get_chroma_client()
    embedding_fn = UpstageChromaEmbedding()
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn
    )

def sync_mentorings_to_vector_db(items: list[dict]):
    """SQLite의 멘토링 목록 데이터를 ChromaDB 벡터 스토어에 업서트한다.
    기존에 동기화되었던 모든 벡터 데이터를 비우고 새로운 데이터로 전체 갱신(Sync)합니다."""
    collection = _get_collection()
    
    # 기존 데이터 전체 삭제 (일관성 보장)
    try:
        if collection.count() > 0:
            existing = collection.get()
            if existing and existing.get("ids"):
                collection.delete(ids=existing["ids"])
    except Exception as e:
        print(f"[SoMa Mate VectorStore] 기존 벡터 데이터 삭제 중 오류 발생: {str(e)}")
    
    if not items:
        print("[SoMa Mate VectorStore] 동기화할 데이터가 없어 ChromaDB 컬렉션을 비웠습니다.")
        return {
            "input_count": 0,
            "valid_vector_count": 0,
            "unique_id_count": 0,
            "collection_count": collection.count(),
        }

    ids = []
    documents = []
    metadatas = []
    seen_ids = set()
    duplicate_ids = set()

    for item in items:
        if item.get("qualityStatus") == "invalid":
            continue
        # 1. 고유 ID
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            item_id = f"missing-id:{len(ids)}"
        if item_id in seen_ids:
            duplicate_ids.add(item_id)
            continue
        seen_ids.add(item_id)
        ids.append(item_id)
        
        # 2. 임베딩용 텍스트 문서 구성
        title = item.get("title", "")
        author = item.get("author", "")
        location = item.get("location", "")
        delivery = item.get("deliveryMethod", "")
        status = item.get("status", "")
        desc = item.get("canonicalText") or item.get("description", "")
        date_str = item.get("startAt") or item.get("dateStr", "")
        time_str = item.get("endAt") or item.get("timeRangeStr", "")
        
        doc_text = f"""구분: {item.get('type', 'lecture')}
제목: {title}
작성자/멘토: {author}
일정: {date_str} {time_str}
장소: {location}
진행방식: {delivery}
상태: {status}
정원: {item.get('currentParticipants', item.get('current_participants', 0))}/{item.get('maxParticipants', item.get('max_participants', 0))}
상세 설명: {desc}"""
        
        documents.append(doc_text)
        
        # 3. 메타데이터 (필터링 및 후처리용)
        metadatas.append({
            "id": item_id,
            "type": item.get("type", ""),
            "status": status,
            "isOnline": 1 if "온라인" in delivery or item.get("isOnline") else 0,
            "mentor": author,
            "title": title
        })

    # ChromaDB에 벌크 업서트 수행
    if not ids:
        print("[SoMa Mate VectorStore] 유효한 데이터가 없어 ChromaDB 업서트를 건너뜁니다.")
        return {
            "input_count": len(items),
            "valid_vector_count": 0,
            "unique_id_count": 0,
            "duplicate_id_count": 0,
            "collection_count": collection.count(),
        }

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas
    )
    collection_count = collection.count()
    stats = {
        "input_count": len(items),
        "valid_vector_count": len(ids),
        "unique_id_count": len(seen_ids),
        "duplicate_id_count": len(duplicate_ids),
        "collection_count": collection_count,
    }
    print(
        "[SoMa Mate VectorStore] ChromaDB 동기화 완료: "
        f"입력 {stats['input_count']}건, 벡터 대상 {stats['valid_vector_count']}건, "
        f"고유 ID {stats['unique_id_count']}건, 실제 컬렉션 {stats['collection_count']}건"
    )
    if collection_count != len(seen_ids):
        print(
            "[SoMa Mate VectorStore] 경고: ChromaDB 실제 컬렉션 수가 고유 ID 수와 다릅니다. "
            f"중복 ID {stats['duplicate_id_count']}건 여부를 확인하세요."
        )
    return stats

def search_vector_mentorings(query: str, n_results: int = 15) -> list[dict]:
    """사용자 질의와 의미론적으로 가장 유사한 멘토링/특강 리스트를 검색한다."""
    collection = _get_collection()
    if collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    documents = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i] if results["metadatas"] else {}
            distance = results["distances"][0][i] if results["distances"] else None
            documents.append({
                "id": results["ids"][0][i],
                "content": doc,
                "metadata": metadata,
                "distance": distance
            })
    return documents
