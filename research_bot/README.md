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
5. **Vector Database Integration**: The search agent now has access to a Supabase vector database for retrieving relevant information from internal sources

## Additional Potential Improvements

- Allow users to attach PDFs or other files as baseline context
- Enable code execution for data analysis

## Environment Variables

The application requires the following environment variables:

```bash
# OpenAI API key for embeddings and language models (fallback)
export OPENAI_API_KEY=your_api_key_here

# Voyage AI API key for legal embeddings
export VOYAGE_API_KEY=your_voyage_api_key_here

# Supabase credentials for vector database access
export SUPABASE_URL=your_supabase_url
export SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

## Debugging

The research bot includes comprehensive debugging functionality to help understand its operation and diagnose issues.

### Debug Mode

Run the research bot with the `--debug` flag to enable debug mode:

```bash
python -m research_bot.main --debug
```

This will:
1. Enable detailed DEBUG level logging to the console
2. Save agent inputs and outputs to the `debug_logs` directory
3. Create performance metrics for all key operations
4. Dump intermediate data structures as JSON files for inspection
5. Capture and log all exceptions with full context

### Debug Log Files

When running in debug mode, the following logs are created in the `debug_logs` directory:

- `*_input.txt` - Inputs sent to agents
- `*_output.txt` - Outputs received from agents
- `*.json` - Dumps of key data structures (search plan, evaluation results, etc.)
- `exception_*.txt` - Detailed exception information with stack traces

### Debug Analysis Tool

The research bot comes with a dedicated debug analysis tool that helps analyze and visualize debug logs. After running the bot in debug mode, you can use the tool to get insights into the bot's operation:

```bash
python -m research_bot.debug_tool --analyze --latest
```

The debug tool provides the following features:

- **Log Analysis**: `--analyze` generates a comprehensive report of the debug session
- **Visualization**: `--visualize` creates charts and diagrams to visualize agent interactions
- **Session Filtering**: `--latest` focuses on only the most recent debug session
- **Log Management**: `--clean` removes old debug logs to free up space

Example usage:

```bash
# Analyze all debug logs
python -m research_bot.debug_tool --analyze

# Analyze and visualize only the latest session
python -m research_bot.debug_tool --analyze --visualize --latest

# Clean up old debug logs
python -m research_bot.debug_tool --clean
```

The tool creates visualizations in the `debug_logs/visualizations/` directory and a summary report in `debug_logs/debug_report.txt`.

### Useful Debug Patterns

#### Tracing Agent Interactions

Look at the input and output files for each agent to understand how they process information:

1. `planner_agent_*_input.txt` / `planner_agent_*_output.txt` - How search plan was created
2. `search_agent_*_input.txt` / `search_agent_*_output.txt` - Search queries and results
3. `evaluator_agent_*_input.txt` / `evaluator_agent_*_output.txt` - Research evaluation
4. `writer_agent_*_input.txt` / `writer_agent_*_output.txt` - Report generation

#### Performance Analysis

Check the debug logs for performance information:
- Function execution times
- Total processing time for each phase
- Times for individual searches

#### Exception Handling

When errors occur, check:
1. Console log for high-level error information
2. `exception_*.txt` files for detailed stack traces and context
3. The most recent input/output files to see what was happening when the error occurred

## Development

### Adding New Debug Features

To enhance the debugging capabilities:

1. Add new decorators or utility functions to `utils/debug.py`
2. Apply them to relevant methods in `manager.py`
3. Update this README to document the new features

### Integration with Monitoring Tools

The debug logs can be integrated with external monitoring solutions:

- Set up log forwarding to centralized logging systems
- Create parsers for the JSON dumps to extract metrics
- Build visualization dashboards for the performance data 