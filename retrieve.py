import chromadb
from sentence_transformers import SentenceTransformer


# Load embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")


# Connect to existing ChromaDB
client = chromadb.PersistentClient(
    path="data/chroma"
)


# Get our collection
collection = client.get_collection(
    name="azure_devops"
)


def retrieve_documents(query, top_k=3):

    # Convert user question into embedding
    query_embedding = model.encode(query).tolist()

    # Search ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )

    return results


if __name__ == "__main__":

    question = "How can I manage packages in Azure DevOps?"

    results = retrieve_documents(
        question,
        top_k=3
    )

    print("\nUSER QUESTION")
    print(question)

    print("\n" + "=" * 80)
    print("RETRIEVED DOCUMENTS")
    print("=" * 80)

    for i, document in enumerate(results["documents"][0]):

        print(f"\nRESULT {i + 1}")
        print("-" * 80)

        print(document)

        print(
            f"\nDistance: "
            f"{results['distances'][0][i]}"
        )

        print(
            f"Metadata: "
            f"{results['metadatas'][0][i]}"
        )