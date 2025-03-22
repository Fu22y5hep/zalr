from pydantic import BaseModel

from agents import Agent

PROMPT = (
    "You are a research strategist tasked with creating a comprehensive research plan. "
    "Given a query, develop an in-depth search strategy that will thoroughly explore the topic.\n\n"
    "Your research plan should:\n"
    "1. Break down the topic into key aspects and subtopics that need exploration\n"
    "2. Consider different perspectives, counterarguments, and potential biases\n"
    "3. Include both broad search terms for general understanding and specific targeted queries\n"
    "4. Prioritize searches by importance to answering the core question\n"
    "5. Include search terms for background context, current developments, expert opinions, "
    "statistical data, and case studies when relevant\n\n"
    "Output between 8 and 20 search queries, ensuring comprehensive coverage of the topic."
)


class WebSearchItem(BaseModel):
    reason: str
    "Your reasoning for why this search is important to the query."

    query: str
    "The search term to use for the web search."

    priority: int
    "Priority of this search (1-10, where 1 is highest priority)"


class WebSearchPlan(BaseModel):
    main_topics: list[str]
    """The main subtopics or aspects of the research query that need to be addressed."""
    
    searches: list[WebSearchItem]
    """A list of web searches to perform to best answer the query."""


planner_agent = Agent(
    name="PlannerAgent",
    instructions=PROMPT,
    model="gpt-4o",
    output_type=WebSearchPlan,
) 