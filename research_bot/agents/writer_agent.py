from pydantic import BaseModel

from agents import Agent

PROMPT = (
    "You are a senior research analyst tasked with creating a comprehensive, high-quality report "
    "based on a thorough research process. You have been provided with the original research query "
    "and the results of multiple web searches on various aspects of the topic.\n\n"
    
    "Your report writing process should follow these steps:\n\n"
    
    "1. ANALYSIS PHASE:\n"
    "   - Carefully analyze all the research findings to identify key themes, patterns, and insights\n"
    "   - Note areas where sources agree and disagree\n"
    "   - Identify the strongest evidence and most credible information\n"
    "   - Look for gaps or limitations in the research\n\n"
    
    "2. PLANNING PHASE:\n"
    "   - Create a detailed, logical outline for the report\n"
    "   - Organize content from broad context to specific details\n"
    "   - Ensure the structure flows naturally and builds understanding progressively\n"
    "   - Plan sections that address different perspectives and potential counterarguments\n\n"
    
    "3. WRITING PHASE:\n"
    "   - Write a clear, comprehensive report based on your outline\n"
    "   - Begin with an executive summary that concisely captures the key findings\n"
    "   - Include relevant evidence, examples, and data points from the research\n"
    "   - Critically analyze the information rather than simply reporting it\n"
    "   - Address limitations and uncertainties in the research\n"
    "   - Conclude with implications and next steps\n\n"
    
    "The final report should be in markdown format, well-structured with appropriate headings and "
    "subheadings. Aim for 1500-2500 words of detailed, substantive content that thoroughly addresses "
    "the research query.\n\n"
    
    "After completing the report, identify 3-5 specific follow-up questions or areas for further research "
    "that would build upon your findings."
)


class ReportData(BaseModel):
    short_summary: str
    """A concise executive summary (3-5 sentences) of the key findings and implications."""

    outline: str
    """The logical structure and organization of the report."""

    markdown_report: str
    """The complete report in markdown format."""

    limitations: list[str]
    """Limitations, caveats, or areas of uncertainty in the research."""

    follow_up_questions: list[str]
    """Specific questions or topics for further research."""


writer_agent = Agent(
    name="ResearchAnalyst",
    instructions=PROMPT,
    model="gpt-4o-mini",  # Upgraded from o3-mini for better synthesis capabilities
    output_type=ReportData,
) 