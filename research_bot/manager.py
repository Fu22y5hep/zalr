from __future__ import annotations

import asyncio
import time
from typing import Dict, List

from rich.console import Console

from agents import Runner, custom_span, gen_trace_id, trace

from .agents.evaluator_agent import EvaluationResult, ResearchGap, evaluator_agent
from .agents.planner_agent import WebSearchItem, WebSearchPlan, planner_agent
from .agents.search_agent import search_agent
from .agents.writer_agent import ReportData, writer_agent
from .printer import Printer


class ResearchManager:
    def __init__(self):
        self.console = Console()
        self.printer = Printer(self.console)
        self.search_results: Dict[str, str] = {}
        self.max_research_iterations = 3

    async def run(self, query: str) -> None:
        trace_id = gen_trace_id()
        with trace("Research trace", trace_id=trace_id):
            self.printer.update_item(
                "trace_id",
                f"View trace: https://platform.openai.com/traces/{trace_id}",
                is_done=True,
                hide_checkmark=True,
            )

            self.printer.update_item(
                "starting",
                "Starting research...",
                is_done=True,
                hide_checkmark=True,
            )
            
            # Initial research phase
            search_plan = await self._plan_searches(query)
            search_results = await self._perform_searches(search_plan)
            
            # Store results with their queries
            for i, result in enumerate(search_results):
                if i < len(search_plan.searches):
                    self.search_results[search_plan.searches[i].query] = result
            
            # Evaluation and refinement loop
            iteration = 1
            while iteration <= self.max_research_iterations:
                self.printer.update_item(
                    "evaluation", 
                    f"Evaluating research quality (iteration {iteration}/{self.max_research_iterations})...",
                )
                
                evaluation = await self._evaluate_research(query, search_results)
                
                if not evaluation.needs_additional_research:
                    self.printer.update_item(
                        "evaluation",
                        f"Research evaluation complete: Quality score {evaluation.quality_score}/10, Completeness score {evaluation.completeness_score}/10",
                        is_done=True,
                    )
                    break
                
                self.printer.update_item(
                    "evaluation",
                    f"Identified {len(evaluation.identified_gaps)} research gaps (iteration {iteration}/{self.max_research_iterations})",
                    is_done=True,
                )
                
                # Perform additional searches to fill gaps
                additional_results = await self._follow_up_searches(evaluation.identified_gaps)
                search_results.extend(additional_results)
                
                iteration += 1
                
                # Stop if we've reached max iterations
                if iteration > self.max_research_iterations:
                    self.printer.update_item(
                        "max_iterations",
                        f"Reached maximum research iterations ({self.max_research_iterations})",
                        is_done=True,
                    )
            
            # Final report generation
            report = await self._write_report(query, search_results)

            final_report = f"Report summary\n\n{report.short_summary}"
            self.printer.update_item("final_report", final_report, is_done=True)

            self.printer.end()

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

    async def _plan_searches(self, query: str) -> WebSearchPlan:
        self.printer.update_item("planning", "Planning comprehensive research strategy...")
        result = await Runner.run(
            planner_agent,
            f"Query: {query}",
        )
        self.printer.update_item(
            "planning",
            f"Research plan created with {len(result.final_output.searches)} searches across {len(result.final_output.main_topics)} main topics",
            is_done=True,
        )
        return result.final_output_as(WebSearchPlan)

    async def _perform_searches(self, search_plan: WebSearchPlan) -> list[str]:
        with custom_span("Search the web"):
            self.printer.update_item("searching", "Executing search plan...")
            
            # Sort searches by priority
            sorted_searches = sorted(search_plan.searches, key=lambda x: x.priority)
            
            num_completed = 0
            tasks = [asyncio.create_task(self._search(item)) for item in sorted_searches]
            results = []
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                num_completed += 1
                self.printer.update_item(
                    "searching", f"Searching... {num_completed}/{len(tasks)} completed"
                )
            self.printer.mark_item_done("searching")
            return results

    async def _search(self, item: WebSearchItem) -> str | None:
        input = f"Search term: {item.query}\nReason for searching: {item.reason}\nPriority: {item.priority}"
        try:
            result = await Runner.run(
                search_agent,
                input,
            )
            return str(result.final_output)
        except Exception:
            return None
            
    async def _evaluate_research(self, query: str, search_results: List[str]) -> EvaluationResult:
        with custom_span("Evaluate research"):
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
            
            return result.final_output_as(EvaluationResult)
    
    async def _follow_up_searches(self, gaps: List[ResearchGap]) -> List[str]:
        with custom_span("Follow-up research"):
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
            
            num_completed = 0
            tasks = [asyncio.create_task(self._search(item)) for item in search_items]
            results = []
            
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                num_completed += 1
                self.printer.update_item(
                    "follow_up", f"Follow-up research... {num_completed}/{len(tasks)} completed"
                )
            
            self.printer.mark_item_done("follow_up")
            return results

    async def _write_report(self, query: str, search_results: list[str]) -> ReportData:
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
        async for _ in result.stream_events():
            if time.time() - last_update > 5 and next_message < len(update_messages):
                self.printer.update_item("writing", update_messages[next_message])
                next_message += 1
                last_update = time.time()

        self.printer.mark_item_done("writing")
        return result.final_output_as(ReportData) 