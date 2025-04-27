#!/usr/bin/env python3
"""
ZALR CLI - Unified Command Line Interface for ZALR Processing Pipeline

This script provides a consolidated interface for running all stages of the 
ZALR processing pipeline. It replaces the individual wrapper scripts and 
provides a simpler, more consistent interface.

Example usage:
  # Run a specific stage
  python zalr_cli.py run --stage 1 --year 2023 --court ZACC
  
  # Run multiple stages
  python zalr_cli.py run --stages 1,2,3 --year 2023 --court ZACC
  
  # Run all stages
  python zalr_cli.py run-all --year 2023 --court ZACC
  
  # Run all stages and prevent sleep
  python zalr_cli.py run-all --year 2023 --court ZACC --prevent-sleep
"""

import os
import sys
import argparse
import time
import platform
import subprocess
import signal
from datetime import datetime
from dotenv import load_dotenv
import importlib

# Add parent directory to Python path to find Django project
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Load environment variables from parent directory
env_file = os.path.join(parent_dir, '.env')
load_dotenv(env_file)

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zalr_backend.settings')
import django
django.setup()

# Global variable to store the caffeinate process
caffeinate_process = None

# Stage configurations
STAGES = {
    1: {
        "name": "stage1_scrape_judgments",
        "description": "Scrape judgments",
        "module": "semantis_app.management.commands.stage1_scrape_judgments",
        "default_args": {
            "batch_size": 10,
            "timeout": 30,
            "max_retries": 3
        }
    },
    2: {
        "name": "stage2_fix_metadata",
        "description": "Fix and enhance judgment metadata",
        "module": "semantis_app.management.commands.stage2_fix_metadata",
        "default_args": {
            "batch_size": 50
        }
    },
    3: {
        "name": "stage3_chunk_judgments",
        "description": "Split judgments into chunks",
        "module": "semantis_app.management.commands.stage3_chunk_judgments",
        "default_args": {
            "batch_size": 50,
            "chunk_size": 1000,
            "overlap": 100
        }
    },
    4: {
        "name": "stage4_generate_embeddings",
        "description": "Generate embeddings for judgment chunks",
        "module": "semantis_app.management.commands.stage4_generate_embeddings",
        "default_args": {
            "batch_size": 10,
            "model": "gpt-4o-mini",
            "max_retries": 3
        }
    },
    5: {
        "name": "stage5_generate_short_summaries",
        "description": "Generate short summaries for judgments",
        "module": "semantis_app.management.commands.stage5_generate_short_summaries",
        "default_args": {
            "batch_size": 10,
            "model": "gpt-4o-mini"
        }
    },
    6: {
        "name": "stage6_calculate_reportability",
        "description": "Calculate reportability scores",
        "module": "semantis_app.management.commands.stage6_calculate_reportability",
        "default_args": {
            "batch_size": 10,
            "model": "gpt-4o-mini"
        }
    },
    7: {
        "name": "stage7_generate_long_summaries",
        "description": "Generate detailed summaries",
        "module": "semantis_app.management.commands.stage7_generate_long_summaries",
        "default_args": {
            "batch_size": 10,
            "model": "gpt-4o-mini",
            "max_tokens": 500,
            "min_reportability": 75
        }
    },
    8: {
        "name": "stage8_classify_practice_areas",
        "description": "Classify practice areas",
        "module": "semantis_app.management.commands.stage8_classify_practice_areas",
        "default_args": {
            "batch_size": 10,
            "model": "gpt-4o-mini"
        }
    }
}

def start_caffeinate():
    """Start the caffeinate process to prevent sleep on macOS"""
    global caffeinate_process
    
    if platform.system() != 'Darwin':
        print("Note: Sleep prevention is only supported on macOS")
        return None
    
    try:
        # Start caffeinate process with options:
        # -d: prevent display sleep
        # -i: prevent system idle sleep
        # -m: prevent disk from sleeping
        caffeinate_process = subprocess.Popen(['caffeinate', '-dim'], 
                                           stdout=subprocess.DEVNULL, 
                                           stderr=subprocess.DEVNULL)
        print("Sleep prevention activated")
        return caffeinate_process
    except Exception as e:
        print(f"Warning: Failed to start caffeinate: {e}")
        return None

def stop_caffeinate():
    """Stop the caffeinate process if it's running"""
    global caffeinate_process
    
    if caffeinate_process is not None:
        try:
            caffeinate_process.terminate()
            caffeinate_process = None
            print("Sleep prevention deactivated")
        except Exception as e:
            print(f"Warning: Failed to stop caffeinate: {e}")

def setup_signal_handlers():
    """Set up signal handlers to ensure caffeinate is stopped on exit"""
    def signal_handler(sig, frame):
        stop_caffeinate()
        if sig == signal.SIGINT:
            print("\nProcess interrupted by user")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def run_stage(stage_num, year, court=None, prevent_sleep=False, **kwargs):
    """Run a specific stage with the given parameters"""
    if stage_num not in STAGES:
        print(f"Error: Invalid stage number {stage_num}")
        return False
    
    # Start caffeinate if requested
    if prevent_sleep and caffeinate_process is None:
        start_caffeinate()
    
    stage = STAGES[stage_num]
    print(f"Running Stage {stage_num}: {stage['description']}...")
    
    # Create a dictionary of arguments with defaults first, then override with kwargs
    args = stage["default_args"].copy()
    args.update({k: v for k, v in kwargs.items() if v is not None})
    
    # Add required arguments
    args["year"] = year
    if court:
        args["court"] = court
    
    # Add prevent_sleep parameter for stage 1 if it supports it
    if stage_num == 1 and prevent_sleep:
        args["prevent_sleep"] = True
    
    # Import the command module and create an instance
    try:
        module = importlib.import_module(stage["module"])
        command = module.Command()
        
        # Run the command with arguments
        start_time = time.time()
        command.handle(**args)
        end_time = time.time()
        
        runtime = end_time - start_time
        print(f"Stage {stage_num} completed in {runtime:.2f} seconds")
        return True
        
    except ImportError as e:
        print(f"Error: Failed to import module {stage['module']}: {e}")
        return False
    except Exception as e:
        print(f"Error: Failed to run stage {stage_num}: {e}")
        return False

def run_multiple_stages(stages, year, court=None, prevent_sleep=False, **kwargs):
    """Run multiple stages in sequence"""
    # Setup signal handlers for clean exit
    setup_signal_handlers()
    
    # Start caffeinate if requested
    if prevent_sleep:
        start_caffeinate()
    
    start_time = time.time()
    
    print(f"Starting process at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Processing year: {year}")
    if court:
        print(f"Processing court: {court}")
    else:
        print(f"Processing all courts")
    print(f"Running stages: {', '.join(map(str, stages))}")
    if prevent_sleep:
        print("Sleep prevention: Enabled")
    print("-------------------------------------")
    
    success = True
    try:
        for stage_num in stages:
            stage_start = time.time()
            
            stage_success = run_stage(stage_num, year, court, prevent_sleep=prevent_sleep, **kwargs)
            if not stage_success:
                print(f"Error: Stage {stage_num} failed. Stopping process.")
                success = False
                break
            
            stage_end = time.time()
            print(f"Stage {stage_num} completed in {stage_end - stage_start:.2f} seconds")
            print("-------------------------------------")
    finally:
        # Always stop caffeinate when done, even if there's an error
        if prevent_sleep:
            stop_caffeinate()
    
    end_time = time.time()
    runtime = end_time - start_time
    minutes = int(runtime // 60)
    seconds = int(runtime % 60)
    
    if success:
        print(f"All stages completed successfully!")
    else:
        print(f"Process completed with errors.")
    print(f"Total runtime: {minutes} minutes and {seconds} seconds")
    return success

def main():
    # Create the main parser
    parser = argparse.ArgumentParser(
        description='ZALR CLI - Unified Command Line Interface for ZALR Processing Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Common arguments
    def add_common_args(p):
        p.add_argument('--year', type=int, required=True, help='Year to process')
        p.add_argument('--court', type=str, help='Court code to process (e.g., ZACC)')
        p.add_argument('--batch-size', type=int, help='Batch size for processing')
        p.add_argument('--prevent-sleep', action='store_true', help='Prevent system from sleeping during processing')
    
    # Parser for the 'run' command (run a specific stage or stages)
    run_parser = subparsers.add_parser('run', help='Run specific stage(s)')
    add_common_args(run_parser)
    stage_group = run_parser.add_mutually_exclusive_group(required=True)
    stage_group.add_argument('--stage', type=int, help='Stage number to run (1-8)')
    stage_group.add_argument('--stages', type=str, help='Comma-separated list of stages to run (e.g., "1,2,3")')
    
    # Additional args for specific stages
    run_parser.add_argument('--timeout', type=int, help='Timeout in seconds (for stage 1)')
    run_parser.add_argument('--max-retries', type=int, help='Max number of retries (for stages 1 and 4)')
    run_parser.add_argument('--chunk-size', type=int, help='Size of each chunk (for stage 3)')
    run_parser.add_argument('--overlap', type=int, help='Overlap between chunks (for stage 3)')
    run_parser.add_argument('--model', type=str, help='Model to use (for stages 4-8)')
    run_parser.add_argument('--max-tokens', type=int, help='Max tokens for summary (for stage 7)')
    run_parser.add_argument('--min-reportability', type=int, help='Minimum reportability score for stage 7 (default: 75)')
    
    # Parser for the 'run-all' command (run all stages)
    run_all_parser = subparsers.add_parser('run-all', help='Run all stages in sequence')
    add_common_args(run_all_parser)
    run_all_parser.add_argument('--timeout', type=int, help='Timeout in seconds (for stage 1)')
    run_all_parser.add_argument('--max-retries', type=int, help='Max number of retries (for stages 1 and 4)')
    run_all_parser.add_argument('--chunk-size', type=int, help='Size of each chunk (for stage 3)')
    run_all_parser.add_argument('--overlap', type=int, help='Overlap between chunks (for stage 3)')
    run_all_parser.add_argument('--model', type=str, help='Model to use (for stages 4-8)')
    run_all_parser.add_argument('--max-tokens', type=int, help='Max tokens for summary (for stage 7)')
    run_all_parser.add_argument('--min-reportability', type=int, help='Minimum reportability score for stage 7 (default: 75)')
    
    # Parser for the 'list' command (list available stages)
    list_parser = subparsers.add_parser('list', help='List available stages')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Handle commands
    if args.command == 'list':
        print("Available stages:")
        for num, stage in STAGES.items():
            print(f"{num}: {stage['description']}")
        return 0
    
    elif args.command == 'run':
        # Get stages to run
        if args.stage:
            stages = [args.stage]
        else:
            try:
                stages = [int(s.strip()) for s in args.stages.split(',')]
                # Check if all stages are valid
                if not all(1 <= s <= 8 for s in stages):
                    print("Error: Stage numbers must be between 1 and 8")
                    return 1
            except ValueError:
                print("Error: Invalid stage numbers. Please provide comma-separated integers.")
                return 1
        
        # Extract kwargs for stage-specific parameters
        kwargs = {
            'batch_size': args.batch_size,
            'timeout': args.timeout,
            'max_retries': args.max_retries,
            'chunk_size': args.chunk_size,
            'overlap': args.overlap,
            'model': args.model,
            'max_tokens': args.max_tokens,
            'min_reportability': args.min_reportability
        }
        
        # Filter out None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        
        # Run the specified stages
        success = run_multiple_stages(stages, args.year, args.court, prevent_sleep=args.prevent_sleep, **kwargs)
        return 0 if success else 1
    
    elif args.command == 'run-all':
        # Extract kwargs for stage-specific parameters
        kwargs = {
            'batch_size': args.batch_size,
            'timeout': args.timeout,
            'max_retries': args.max_retries,
            'chunk_size': args.chunk_size,
            'overlap': args.overlap,
            'model': args.model,
            'max_tokens': args.max_tokens,
            'min_reportability': args.min_reportability
        }
        
        # Filter out None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        
        # Run all stages
        success = run_multiple_stages(range(1, 9), args.year, args.court, prevent_sleep=args.prevent_sleep, **kwargs)
        return 0 if success else 1
    
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    sys.exit(main()) 