import os
import aiohttp
from supabase import create_client
from pydantic import BaseModel
from typing import List

from openai import AsyncOpenAI
from agents import FunctionTool, RunContextWrapper
from agents.model_settings import ModelSettings
from agents import Agent, WebSearchTool

class VectorSearchArgs(BaseModel):
    query: str
    match_count: int = 5

async def invoke_vector_search(ctx: RunContextWrapper, raw_args: str) -> str:
    """Main vector search logic invoked by the agent."""
    args = VectorSearchArgs.model_validate_json(raw_args)
    query = args.query
    match_count = args.match_count

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        return "Error: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables are not set."

    # Get the embedding
    try:
        embedding = await _get_voyage_embedding(query)
    except Exception as e:
        print(f"Voyage AI embedding failed: {str(e)}. Falling back to OpenAI.")
        embedding = await _get_openai_embedding(query)

    # Query supabase
    try:
        client = create_client(supabase_url, supabase_key)
        results = client.rpc(
            "hybrid_search",
            {
                "query_text": query,
                "query_embedding": embedding,
                "match_count": match_count,
                "full_text_weight": 1.0,
                "semantic_weight": 1.0
            }
        ).execute()
    except Exception as e:
        return f"Error searching vector store: {str(e)}"

    if not results.data:
        return "No results found in the vector store."

    # Format the results
    formatted_results = []
    for item in results.data:
        summary = item.get("short_summary", "No summary available")
        title = item.get("case_name", item.get("title", "Untitled document"))
        date = item.get("date", "Unknown date")
        formatted_results.append(f"Title: {title}\nDate: {date}\nSummary: {summary}")

    return "\n\n".join(formatted_results)

vector_search_tool = FunctionTool(
    name="vector_search",
    description="Search the vector store in Supabase for matching documents using embeddings.",
    # Provide a schema that meets the function-calling requirements:
    params_json_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "match_count": {"type": "integer"}
        },
        "required": ["query", "match_count"],
        "additionalProperties": False  # <- Important
    },
    on_invoke_tool=invoke_vector_search
)

# Rest of your code
async def _get_voyage_embedding(text: str) -> List[float]:
    voyage_api_key = os.getenv("VOYAGE_API_KEY")
    if not voyage_api_key:
        raise ValueError("VOYAGE_API_KEY environment variable is not set.")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            'https://api.voyageai.com/v1/embeddings',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {voyage_api_key}',
            },
            json={'model': 'voyage-law-2', 'input': text}
        ) as response:
            if not response.ok:
                error_data = await response.json()
                raise ValueError(f"Voyage AI error: {error_data.get('error', 'Unknown error')}")

            data = await response.json()
            if data.get('data') and isinstance(data['data'], list) and len(data['data']) > 0:
                if 'embedding' in data['data'][0]:
                    return data['data'][0]['embedding']

    raise ValueError(f"Unexpected response format from Voyage AI: {data}")

async def _get_openai_embedding(text: str) -> List[float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set.")

    client = AsyncOpenAI(api_key=api_key)
    response = await client.embeddings.create(input=text, model="text-embedding-3-small")
    return response.data[0].embedding