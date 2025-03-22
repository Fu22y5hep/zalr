from pydantic import BaseModel
from typing import List, Optional

from agents import Agent


class ResearchGap(BaseModel):
    topic: str
    """The specific topic or area that needs more information."""

    reason: str
    """Explanation of why this topic needs more research."""

    suggested_queries: List[str]
    """Suggested search queries to fill this gap."""


class EvaluationResult(BaseModel):
    completeness_score: int
    """Score from 1-10 assessing how completely the research covers the original query."""

    quality_score: int
    """Score from 1-10 assessing the quality and relevance of the information gathered."""

    strength_analysis: str
    """Analysis of what aspects of the research are strongest."""

    gap_analysis: str
    """Overall analysis of what's missing from the current research."""

    identified_gaps: List[ResearchGap]
    """Specific gaps identified in the research that should be addressed."""

    needs_additional_research: bool
    """Whether additional research is recommended before proceeding to writing."""


PROMPT = """
You are a critical research evaluator. Your job is to carefully analyze research results and identify gaps, 
inconsistencies, or areas that need more exploration.

Given a research query and the summarized results of initial searches, you will:

1. Assess the completeness of the research (how well it addresses all aspects of the query)
2. Evaluate the quality and relevance of information gathered
3. Identify specific gaps or weaknesses that should be addressed with further research
4. Determine whether additional searches should be conducted before proceeding to the report writing phase

Be thorough and critical in your evaluation. Look for:
- Missing perspectives or counterarguments
- Areas where data or evidence is lacking
- Topics mentioned but not fully explored
- Potential biases in the research
- Areas where more recent information would be valuable

For each gap you identify, provide specific suggested search queries that would help address it.
"""

evaluator_agent = Agent(
    name="EvaluatorAgent",
    instructions=PROMPT,
    model="gpt-4o",
    output_type=EvaluationResult,
) 