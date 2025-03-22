# Enhanced Research Bot

A Python-based research bot using the OpenAI Agents SDK to help with web research, featuring an iterative research refinement process.

## Architecture

The enhanced research flow is:

1. User enters their research topic
2. The planner_agent creates a comprehensive research strategy, breaking down the topic into subtopics and generating prioritized search queries
3. For each search item, the search_agent uses the Web Search tool to search for that term and summarize the results, running searches in parallel
4. The evaluator_agent critically assesses the research results, identifies gaps and suggests additional searches
5. The bot conducts follow-up searches to fill the identified gaps (up to 3 iterations)
6. Finally, the writer_agent analyzes all findings and synthesizes them into a comprehensive report

## Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Configure your OpenAI API key:

```bash
export OPENAI_API_KEY=your_api_key_here
```

## Usage

Run the bot:

```bash
cd research_bot
python main.py
```

Then enter your research topic when prompted.

## Components

- **planner_agent**: Creates a comprehensive research strategy with prioritized searches
- **search_agent**: Performs web searches and summarizes findings
- **evaluator_agent**: Assesses research quality, identifies gaps, and suggests follow-up searches
- **writer_agent**: Synthesizes all research into a well-structured, detailed report
- **ResearchManager**: Coordinates the iterative research workflow
- **Printer**: Provides a nice UI for status updates

## Key Improvements

1. **Smarter Planning**: The planner now breaks down topics into subtopics and prioritizes searches
2. **Iterative Refinement**: The evaluator identifies research gaps and triggers follow-up searches
3. **Quality Assessment**: Research is scored on completeness and quality
4. **Comprehensive Report Generation**: The writer now creates a detailed outline and addresses limitations

## Additional Potential Improvements

- Add support for fetching relevant information from a vector store
- Allow users to attach PDFs or other files as baseline context
- Enable code execution for data analysis 