#!/usr/bin/env python
"""
Stage Runner Wrapper

This script initializes Django once and then runs all stage scripts in sequence
within the same process, avoiding the need to reinitialize Django for each stage.

Usage:
  python run_stages_wrapper.py --year 2025 [--debug]
"""

import os
import sys
import argparse
import importlib.util
import time
from datetime import datetime

# Parse command line arguments
parser = argparse.ArgumentParser(description="Run all stage scripts in sequence")
parser.add_argument("--year", type=int, required=True, help="Year to process")
parser.add_argument("--court", type=str, help="Court code to process (optional)")
parser.add_argument("--debug", action="store_true", help="Enable debug output")
parser.add_argument("--stage", type=int, help="Run only this specific stage (1-8)")
args = parser.parse_args()

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zalr_backend.settings.github_actions")
import django
django.setup()
print("Django successfully initialized with settings:", os.environ.get("DJANGO_SETTINGS_MODULE"))

# Stage script paths
stage_scripts = [
    "stages/stage1_scrape_judgments.py",
    "stages/stage2_fix_metadata.py",
    "stages/stage3_chunk_judgments.py",
    "stages/stage4_generate_embeddings.py",
    "stages/stage5_generate_short_summaries.py",
    "stages/stage6_calculate_reportability.py",
    "stages/stage7_generate_long_summaries.py",
    "stages/stage8_classify_practice_areas.py"
]

def import_module_from_file(file_path):
    """Import a Python file as a module."""
    module_name = os.path.basename(file_path).replace('.py', '')
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_stage_script(script_path, stage_num):
    """Run a stage script by importing it and calling its main function."""
    print(f"\n{'='*50}")
    print(f"RUNNING STAGE {stage_num}: {os.path.basename(script_path)}")
    print(f"{'='*50}")
    
    try:
        # Import the script as a module
        module = import_module_from_file(script_path)
        
        # Check if the module has a main function
        if hasattr(module, 'main'):
            # Call the main function with our arguments
            kwargs = {
                'year': args.year
            }
            if args.court:
                kwargs['court'] = args.court
            if args.debug:
                kwargs['debug'] = True
                
            module.main(**kwargs)
            return True
        else:
            # Default approach - look for a Command class (Django style)
            if hasattr(module, 'Command'):
                cmd = module.Command()
                cmd_args = {
                    'year': args.year
                }
                if args.court:
                    cmd_args['court'] = args.court
                if args.debug:
                    cmd_args['debug'] = True
                
                cmd.handle(**cmd_args)
                return True
            else:
                print(f"Error: No main function or Command class found in {script_path}")
                return False
    except Exception as e:
        print(f"Error running {script_path}: {str(e)}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return False

def main():
    start_time = time.time()
    print(f"Starting all stages at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Processing year: {args.year}")
    if args.court:
        print(f"Processing court: {args.court}")
    else:
        print("Processing all courts")
    
    # Run single stage if specified
    if args.stage:
        if 1 <= args.stage <= len(stage_scripts):
            script_path = stage_scripts[args.stage - 1]
            success = run_stage_script(script_path, args.stage)
            print(f"Stage {args.stage} {'completed successfully' if success else 'failed'}")
        else:
            print(f"Error: Invalid stage number {args.stage}. Must be between 1 and {len(stage_scripts)}")
        return
    
    # Run all stages in sequence
    success_count = 0
    for i, script_path in enumerate(stage_scripts):
        stage_num = i + 1
        stage_start = time.time()
        
        if run_stage_script(script_path, stage_num):
            success_count += 1
            stage_end = time.time()
            print(f"Stage {stage_num} completed in {stage_end - stage_start:.2f} seconds")
        else:
            print(f"Stage {stage_num} failed. Stopping pipeline.")
            break
    
    end_time = time.time()
    total_time = end_time - start_time
    minutes, seconds = divmod(total_time, 60)
    
    print(f"\nPipeline finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Successfully ran {success_count}/{len(stage_scripts)} stages")
    print(f"Total runtime: {int(minutes)} minutes and {int(seconds)} seconds")

if __name__ == "__main__":
    main() 