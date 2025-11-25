import asyncio
from shared_data_layer.testing.factories.retrieval import ChunkFactory
from shared_data_layer.db.models.retrieval import Chunk

async def main():
    print("Building chunk...")
    chunk = ChunkFactory.build()
    print(f"Chunk embedding len: {len(chunk.embedding) if chunk.embedding else 'None'}")
    print(f"Chunk embedding type: {type(chunk.embedding)}")
    print(f"Chunk embedding sample: {chunk.embedding[:5] if chunk.embedding else 'None'}")

if __name__ == "__main__":
    asyncio.run(main())
