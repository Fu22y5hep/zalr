from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List

from rich.console import Console

from agents import Runner, custom_span, gen_trace_id, trace

from .agents.evaluator_agent import EvaluationResult, ResearchGap, evaluator_agent
from .agents.planner_agent import WebSearchItem, WebSearchPlan, planner_agent
from .agents.search_agent import search_agent
from .agents.writer_agent import ReportData, writer_agent
from .printer import Printer
from .utils.debug import time_async_function, log_agent_inputs, dump_object, capture_exception


def setup_logging(debug=False):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    return logging.getLogger("research_bot")


class ResearchManager:
    def __init__(self, debug=False):
        self.console = Console()
        self.printer = Printer(self.console)
        self.search_results: Dict[str, str] = {}
        self.max_research_iterations = 3
        self.debug = debug
        self.logger = setup_logging(debug)

    @time_async_function
    async def run(self, query: str) -> None:
        self.logger.info(f"Starting research for query: {query}")
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            self.printer.update_item(
                "trace_id",
                f"View trace: https://platform.openai.com/traces/{trace_id}",
                is_done=True,
                hide_checkmark=True,
            )
            self.logger.debug(f"Trace ID: {trace_id}")

            self.printer.update_item(
                "starting",
                "Starting research...",
                is_done=True,
                hide_checkmark=True,
            )
            
            try:
                # Initial research phase
                self.logger.debug("Starting initial research phase")
                search_plan = await self._plan_searches(query)
                
                if self.debug:
                    dump_object(search_plan, "search_plan")
                    
                search_results = await self._perform_searches(search_plan)
                
                # Store results with their queries
                for i, result in enumerate(search_results):
                    if i < len(search_plan.searches):
                        self.search_results[search_plan.searches[i].query] = result
                
                # Evaluation and refinement loop
                iteration = 1
                while iteration <= self.max_research_iterations:
                    self.logger.debug(f"Starting evaluation iteration {iteration}/{self.max_research_iterations}")
                    self.printer.update_item(
                        "evaluation", 
                        f"Evaluating research quality (iteration {iteration}/{self.max_research_iterations})...",
                    )
                    
                    evaluation = await self._evaluate_research(query, search_results)
                    
                    if self.debug:
                        dump_object(evaluation, f"evaluation_iteration_{iteration}")
                    
                    if not evaluation.needs_additional_research:
                        self.logger.info(f"Research complete. Quality: {evaluation.quality_score}/10, Completeness: {evaluation.completeness_score}/10")
                        self.printer.update_item(
                            "evaluation",
                            f"Research evaluation complete: Quality score {evaluation.quality_score}/10, Completeness score {evaluation.completeness_score}/10",
                            is_done=True,
                        )
                        break
                    
                    self.logger.debug(f"Found {len(evaluation.identified_gaps)} research gaps that need filling")
                    self.printer.update_item(
                        "evaluation",
                        f"Identified {len(evaluation.identified_gaps)} research gaps (iteration {iteration}/{self.max_research_iterations})",
                        is_done=True,
                    )
                    
                    # Perform additional searches to fill gaps
                    additional_results = await self._follow_up_searches(evaluation.identified_gaps)
                    search_results.extend(additional_results)
                    self.logger.debug(f"Added {len(additional_results)} additional search results")
                    
                    iteration += 1
                    
                    # Stop if we've reached max iterations
                    if iteration > self.max_research_iterations:
                        self.logger.info(f"Reached maximum research iterations ({self.max_research_iterations})")
                        self.printer.update_item(
                            "max_iterations",
                            f"Reached maximum research iterations ({self.max_research_iterations})",
                            is_done=True,
                        )
                
                # Final report generation
                self.logger.info("Starting report generation")
                report = await self._write_report(query, search_results)
                
                if self.debug:
                    dump_object(report, "final_report")

                final_report = f"Report summary\n\n{report.short_summary}"
                self.printer.update_item("final_report", final_report, is_done=True)

                self.printer.end()
                self.logger.info("Research process completed")
            
            except Exception as e:
                capture_exception(e, f"Research process for query: {query}")
                self.printer.update_item(
                    "error",
                    f"Error occurred during research: {str(e)}",
                    is_done=True,
                )
                self.printer.end()
                raise

        print("\n\n=====REPORT SUMMARY=====\n\n")
        print(report.short_summary)
        
        print("\n\n=====REPORT OUTLINE=====\n\n")
        print(report.outline)
        
        print("\n\n=====FULL REPORT=====\n\n")
        print(report.markdown_report)
        
        print("\n\n=====RESEARCH LIMITATIONS=====\n\n")
        limitations = "\n".join([f"- {limitation}" for limitation in report.limitations])
        print(limitations)
        
        print("\n\n=====FOLLOW UP QUESTIONS=====\n\n")
        follow_up_questions = "\n".join([f"- {question}" for question in report.follow_up_questions])
        print(follow_up_questions)

    @time_async_function
    @log_agent_inputs
    async def _plan_searches(self, query: str) -> WebSearchPlan:
        self.logger.debug(f"Planning searches for query: {query}")
        start_time = time.time()
        self.printer.update_item("planning", "Planning comprehensive research strategy...")
        result = await Runner.run(
            planner_agent,
            f"Query: {query}",
        )
        elapsed = time.time() - start_time
        self.logger.debug(f"Planning completed in {elapsed:.2f}s")
        
        plan = result.final_output_as(WebSearchPlan)
        self.logger.debug(f"Research plan created with {len(plan.searches)} searches across {len(plan.main_topics)} main topics")
        
        self.printer.update_item(
            "planning",
            f"Research plan created with {len(plan.searches)} searches across {len(plan.main_topics)} main topics",
            is_done=True,
        )
        return plan

    @time_async_function
    async def _perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        with custom_span("Search the web"):
            self.logger.debug(f"Starting searches execution with {len(search_plan.searches)} search items")
            self.printer.update_item("searching", "Executing search plan...")
            
            # Sort searches by priority
            sorted_searches = sorted(search_plan.searches, key=lambda x: x.priority)
            if self.debug:
                for i, search in enumerate(sorted_searches):
                    self.logger.debug(f"Search {i+1}: Query='{search.query}', Priority={search.priority}")
            
            num_completed = 0
            tasks = [asyncio.create_task(self._search(item)) for item in sorted_searches]
            results = []
            for task in asyncio.as_completed(tasks):
                try:
                    result = await task
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    capture_exception(e, "Processing search result")
                    self.logger.error(f"Error processing search result: {str(e)}")
                
                num_completed += 1
                self.printer.update_item(
                    "searching", f"Searching... {num_completed}/{len(tasks)} completed"
                )
            self.printer.mark_item_done("searching")
            self.logger.debug(f"Search execution complete. Retrieved {len(results)}/{len(tasks)} results")
            return results

    @time_async_function
    @log_agent_inputs
    async def _search(self, item: WebSearchItem) -> str | None:
        start_time = time.time()
        self.logger.debug(f"Starting search for: '{item.query}'")
        input = f"Search term: {item.query}\nReason for searching: {item.reason}\nPriority: {item.priority}"
        try:
            result = await Runner.run(
                search_agent,
                input,
            )
            elapsed = time.time() - start_time
            self.logger.debug(f"Search for '{item.query}' completed in {elapsed:.2f}s")
            return str(result.final_output)
        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error(f"Search for '{item.query}' failed after {elapsed:.2f}s: {str(e)}")
            capture_exception(e, f"Search query: {item.query}")
            return None
            
    @time_async_function
    @log_agent_inputs
    async def _evaluate_research(self, query: str, search_results: List[str]) -> EvaluationResult:
        with custom_span("Evaluate research"):
            self.logger.debug(f"Evaluating research with {len(search_results)} search results")
            start_time = time.time()
            
            search_summaries = "\n\n".join([
                f"Search Result {i+1}: {result}" 
                for i, result in enumerate(search_results)
            ])
            
            input_text = f"""
            Original Query: {query}
            
            Search Results:
            {search_summaries}
            """
            
            result = await Runner.run(
                evaluator_agent,
                input_text,
            )
            
            evaluation = result.final_output_as(EvaluationResult)
            elapsed = time.time() - start_time
            
            self.logger.debug(
                f"Evaluation completed in {elapsed:.2f}s. Quality: {evaluation.quality_score}/10, "
                f"Completeness: {evaluation.completeness_score}/10, "
                f"Needs more research: {evaluation.needs_additional_research}, "
                f"Gaps identified: {len(evaluation.identified_gaps)}"
            )
            
            return evaluation
    
    @time_async_function
    async def _follow_up_searches(self, gaps: List[ResearchGap]) -> List[str]:
        with custom_span("Follow-up research"):
            self.logger.debug(f"Starting follow-up research for {len(gaps)} gaps")
            start_time = time.time()
            self.printer.update_item("follow_up", "Conducting follow-up research to fill gaps...")
            
            # Create search items from gaps
            search_items = []
            for gap in gaps:
                for i, query in enumerate(gap.suggested_queries):
                    search_items.append(WebSearchItem(
                        query=query,
                        reason=f"To address gap: {gap.topic}. {gap.reason}",
                        priority=i+1  # Prioritize the first suggestions higher
                    ))
            
            self.logger.debug(f"Created {len(search_items)} follow-up search queries")
            if self.debug:
                for i, item in enumerate(search_items):
                    self.logger.debug(f"Follow-up search {i+1}: '{item.query}', Priority={item.priority}")
                dump_object(search_items, "follow_up_search_items")
            
            num_completed = 0
            tasks = [asyncio.create_task(self._search(item)) for item in search_items]
            results = []
            
            for task in asyncio.as_completed(tasks):
                try:
                    result = await task
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    capture_exception(e, "Follow-up search")
                    self.logger.error(f"Error in follow-up search: {str(e)}")
                
                num_completed += 1
                self.printer.update_item(
                    "follow_up", f"Follow-up research... {num_completed}/{len(tasks)} completed"
                )
            
            self.printer.mark_item_done("follow_up")
            
            elapsed = time.time() - start_time
            self.logger.debug(f"Follow-up research completed in {elapsed:.2f}s. Retrieved {len(results)}/{len(tasks)} results")
            return results

    @time_async_function
    @log_agent_inputs
    async def _write_report(self, query: str, search_results: list[str]) -> ReportData:
        self.logger.debug("Starting report writing")
        start_time = time.time()
        self.printer.update_item("writing", "Thinking about report...")
        input = f"Original query: {query}\nSummarized search results: {search_results}"
        result = Runner.run_streamed(
            writer_agent,
            input,
        )
        update_messages = [
            "Thinking about report...",
            "Planning report structure...",
            "Creating detailed outline...",
            "Synthesizing research findings...",
            "Writing main sections...",
            "Adding supporting evidence...",
            "Refining arguments and conclusions...",
            "Finalizing report...",
        ]

        last_update = time.time()
        next_message = 0
        try:
            async for _ in result.stream_events():
                if time.time() - last_update > 5 and next_message < len(update_messages):
                    self.printer.update_item("writing", update_messages[next_message])
                    self.logger.debug(f"Report writing status: {update_messages[next_message]}")
                    next_message += 1
                    last_update = time.time()
        except Exception as e:
            capture_exception(e, "Report generation stream")
            self.logger.error(f"Error in report generation stream: {str(e)}")

        self.printer.mark_item_done("writing")
        elapsed = time.time() - start_time
        self.logger.debug(f"Report writing completed in {elapsed:.2f}s")
        return result.final_output_as(ReportData) 