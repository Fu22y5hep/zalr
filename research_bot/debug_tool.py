#!/usr/bin/env python
"""
Debug Tool for Research Bot

This script provides utilities for analyzing debug logs and diagnosing issues
with the research bot. It can be run after a research session to process
and visualize the debug data.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from rich.tree import Tree


DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_logs")


def parse_args():
    parser = argparse.ArgumentParser(description="Debug Tool for Research Bot")
    parser.add_argument("--analyze", action="store_true", help="Analyze debug logs and generate a report")
    parser.add_argument("--visualize", action="store_true", help="Create visualizations from debug logs")
    parser.add_argument("--latest", action="store_true", help="Only analyze the latest debug session")
    parser.add_argument("--clean", action="store_true", help="Clean debug logs (will prompt for confirmation)")
    return parser.parse_args()


def get_latest_session() -> Optional[Tuple[List[str], datetime]]:
    """Get the latest debug session files based on timestamps"""
    if not os.path.exists(DEBUG_DIR):
        return None
    
    files = os.listdir(DEBUG_DIR)
    if not files:
        return None
    
    # Extract timestamps from filenames
    file_times = {}
    for file in files:
        match = re.search(r'_(\d+)_', file) or re.search(r'_(\d+)\.', file)
        if match:
            timestamp = int(match.group(1))
            file_times.setdefault(timestamp, []).append(file)
    
    if not file_times:
        return None
    
    # Get the most recent timestamp
    latest_timestamp = max(file_times.keys())
    latest_datetime = datetime.fromtimestamp(latest_timestamp)
    latest_files = file_times[latest_timestamp]
    
    # Include all files within 10 minutes of the latest timestamp
    session_files = []
    for timestamp, files in file_times.items():
        if latest_timestamp - timestamp < 600:  # 10 minutes in seconds
            session_files.extend(files)
    
    return session_files, latest_datetime


def analyze_performance(files: List[str]) -> Dict:
    """Analyze performance metrics from debug logs"""
    perf_data = {
        "planning": [],
        "searching": [],
        "evaluation": [],
        "report_writing": [],
        "total_time": 0
    }
    
    for file in files:
        if "planner_agent" in file and "output" in file:
            # Extract planning time
            file_path = os.path.join(DEBUG_DIR, file)
            with open(file_path, 'r') as f:
                timestamp_match = re.search(r'_(\d+)_', file)
                if timestamp_match:
                    timestamp = int(timestamp_match.group(1))
                    perf_data["planning"].append(timestamp)
        
        # Extract other performance data from log files
        # This is a simplified example
    
    return perf_data


def create_agent_interaction_diagram(files: List[str], output_path: str):
    """Create a diagram showing agent interactions"""
    # Parse input and output files to determine the sequence of agent interactions
    interactions = []
    
    for file in files:
        if "_input.txt" in file or "_output.txt" in file:
            timestamp_match = re.search(r'_(\d+)_', file)
            if timestamp_match:
                timestamp = int(timestamp_match.group(1))
                agent_name = file.split('_')[0]
                io_type = "input" if "_input" in file else "output"
                interactions.append((timestamp, agent_name, io_type))
    
    # Sort by timestamp
    interactions.sort()
    
    # Create the visualization
    fig, ax = plt.subplots(figsize=(12, 6))
    
    agents = sorted(set(agent for _, agent, _ in interactions))
    agent_positions = {agent: i for i, agent in enumerate(agents)}
    
    for i, (timestamp, agent, io_type) in enumerate(interactions):
        pos = agent_positions[agent]
        color = 'blue' if io_type == 'input' else 'green'
        
        # Convert timestamp to a more readable format
        dt = datetime.fromtimestamp(timestamp)
        readable_time = dt.strftime('%H:%M:%S')
        
        ax.scatter(i, pos, color=color, s=100)
        if i > 0:
            prev_timestamp, prev_agent, _ = interactions[i-1]
            prev_pos = agent_positions[prev_agent]
            ax.plot([i-1, i], [prev_pos, pos], 'k-', alpha=0.3)
    
    ax.set_yticks(range(len(agents)))
    ax.set_yticklabels(agents)
    ax.set_xlabel('Sequence')
    ax.set_title('Agent Interaction Sequence')
    
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()


def visualize_data(files: List[str]):
    """Create visualizations from debug logs"""
    os.makedirs(os.path.join(DEBUG_DIR, "visualizations"), exist_ok=True)
    
    # Create agent interaction diagram
    create_agent_interaction_diagram(
        files, 
        os.path.join(DEBUG_DIR, "visualizations", "agent_interactions.png")
    )
    
    # Add more visualizations here
    console = Console()
    console.print("[green]Visualizations created in debug_logs/visualizations/")


def analyze_logs(files: List[str], session_datetime: datetime):
    """Analyze debug logs and generate a report"""
    console = Console()
    
    # Count file types
    file_types = {
        "input": 0,
        "output": 0,
        "json": 0,
        "exception": 0
    }
    
    for file in files:
        if "_input.txt" in file:
            file_types["input"] += 1
        elif "_output.txt" in file:
            file_types["output"] += 1
        elif file.endswith(".json"):
            file_types["json"] += 1
        elif "exception" in file:
            file_types["exception"] += 1
    
    # Create a summary table
    table = Table(title=f"Debug Session Summary - {session_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
    
    table.add_column("Category", style="cyan")
    table.add_column("Count", style="magenta")
    
    for category, count in file_types.items():
        table.add_row(category.capitalize(), str(count))
    
    console.print(table)
    
    # Check for exceptions
    if file_types["exception"] > 0:
        console.print("[bold red]Exceptions detected in this session!")
        for file in files:
            if "exception" in file:
                file_path = os.path.join(DEBUG_DIR, file)
                with open(file_path, 'r') as f:
                    console.print(f"[bold red]Exception in {file}:")
                    console.print(f.read())
    
    # Create a tree with agent interactions
    tree = Tree("Research Flow")
    
    planning_node = tree.add("Planning")
    search_node = tree.add("Searching")
    eval_node = tree.add("Evaluation")
    report_node = tree.add("Report Generation")
    
    # Add details to the tree
    for file in files:
        file_path = os.path.join(DEBUG_DIR, file)
        
        if "planner_agent" in file and "_output" in file:
            # Extract search plan details
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    # Very simplified parsing
                    search_count = content.count("query")
                    planning_node.add(f"[blue]{search_count} searches planned")
            except:
                pass
        
        elif "search_agent" in file and "_output" in file:
            search_node.add(f"[green]{os.path.basename(file)}")
            
        elif "evaluator_agent" in file and "_output" in file:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                    # Very simplified parsing
                    if "quality_score" in content:
                        match = re.search(r'quality_score["\']:\s*(\d+)', content)
                        if match:
                            quality = match.group(1)
                            eval_node.add(f"[yellow]Quality score: {quality}/10")
            except:
                pass
            
        elif "writer_agent" in file and "_output" in file:
            report_node.add(f"[magenta]{os.path.basename(file)}")
    
    console.print(tree)
    
    # Save the report
    report_path = os.path.join(DEBUG_DIR, "debug_report.txt")
    with open(report_path, 'w') as f:
        f.write(f"Debug Session Report - {session_datetime.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Files analyzed: {len(files)}\n")
        f.write(f"Input files: {file_types['input']}\n")
        f.write(f"Output files: {file_types['output']}\n")
        f.write(f"JSON dumps: {file_types['json']}\n")
        f.write(f"Exceptions: {file_types['exception']}\n")
    
    console.print(f"[green]Report saved to {report_path}")


def clean_logs():
    """Clean debug logs"""
    console = Console()
    
    if not os.path.exists(DEBUG_DIR):
        console.print("[yellow]No debug logs to clean.")
        return
    
    files = os.listdir(DEBUG_DIR)
    if not files:
        console.print("[yellow]No debug logs to clean.")
        return
    
    confirm = input(f"This will delete {len(files)} log files. Are you sure? (y/n): ")
    if confirm.lower() != 'y':
        console.print("[yellow]Cleanup cancelled.")
        return
    
    with Progress() as progress:
        task = progress.add_task("[red]Cleaning logs...", total=len(files))
        for file in files:
            file_path = os.path.join(DEBUG_DIR, file)
            if os.path.isfile(file_path):
                os.remove(file_path)
            progress.update(task, advance=1)
    
    console.print("[green]Debug logs cleaned successfully.")


def main():
    args = parse_args()
    console = Console()
    
    if not os.path.exists(DEBUG_DIR):
        console.print("[bold red]No debug logs found. Run the research bot with --debug first.")
        return
    
    all_files = os.listdir(DEBUG_DIR)
    
    if args.latest:
        session_info = get_latest_session()
        if not session_info:
            console.print("[bold red]No debug session found.")
            return
        files, session_datetime = session_info
    else:
        files = all_files
        session_datetime = datetime.now()
    
    if args.analyze:
        console.print(f"[bold]Analyzing {len(files)} debug log files...")
        analyze_logs(files, session_datetime)
    
    if args.visualize:
        console.print(f"[bold]Creating visualizations from {len(files)} debug log files...")
        visualize_data(files)
    
    if args.clean:
        clean_logs()
    
    if not any([args.analyze, args.visualize, args.clean]):
        console.print("[yellow]No action specified. Use --analyze, --visualize, or --clean.")
        console.print("For help, use --help")


if __name__ == "__main__":
    main() 