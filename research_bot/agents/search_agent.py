from agents import Agent, WebSearchTool
from agents.model_settings import ModelSettings
from .vector_search_tool import vector_search_tool 

INSTRUCTIONS = (
    "You are a research assistant. Given a search term, you search the web for that term and "
    "produce a concise summary of the results. The summary must be 2-3 paragraphs and less than 300 "
    "words. Capture the main points. Write succintly, no need to have complete sentences or good "
    "grammar. This will be consumed by someone synthesizing a report, so its vital you capture the "
    "essence and ignore any fluff. Do not include any additional commentary other than the summary "
    "itself."
    "\n\nYou have two search tools available:"
    "\n1. web_search: Searches the web for real-time information"
    "\n2. vector_search: Searches the internal vector database for relevant information"
    "\n\nFirst use vector_search to find relevant information from the internal database. If the "
    "necessary information is not found or needs to be supplemented with more current information, "
    "use web_search. Always prioritize information from the vector database when available."
)

search_agent = Agent(
    name="Search agent",
    instructions=INSTRUCTIONS,
    tools=[WebSearchTool(), vector_search_tool],
    model_settings=ModelSettings(tool_choice="required"),
) 