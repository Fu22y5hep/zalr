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
import shutil
from datetime import datetime

# Parse command line arguments
parser = argparse.ArgumentParser(description="Run all stage scripts in sequence")
parser.add_argument("--year", type=int, required=True, help="Year to process")
parser.add_argument("--court", type=str, help="Court code to process (optional)")
parser.add_argument("--debug", action="store_true", help="Enable debug output")
parser.add_argument("--stage", type=int, help="Run only this specific stage (1-8)")
args = parser.parse_args()

# Get the absolute path of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = current_dir

# Ensure court_config.yaml is accessible in the expected location
court_config_path = os.path.join(current_dir, 'court_config.yaml')
if os.path.exists(court_config_path):
    print(f"court_config.yaml found in {current_dir}")
else:
    # Try to find the file in various locations
    possible_locations = [
        os.path.join(root_dir, 'court_config.yaml'),
        os.path.join(root_dir, 'stages', 'court_config.yaml'),
        os.path.join(root_dir, 'semantis_app', 'court_config.yaml'),
        os.path.join(root_dir, 'zalr_backend', 'court_config.yaml'),
    ]
    
    found = False
    for loc in possible_locations:
        if os.path.exists(loc):
            shutil.copy2(loc, court_config_path)
            print(f"Copied court_config.yaml from {loc} to {current_dir}")
            found = True
            break
    
    # If we still couldn't find it, check recursively
    if not found:
        found_paths = []
        for root, dirs, files in os.walk(root_dir):
            if 'court_config.yaml' in files:
                found_paths.append(os.path.join(root, 'court_config.yaml'))
        
        if found_paths:
            # Use the first found instance
            source_path = found_paths[0]
            shutil.copy2(source_path, court_config_path)
            print(f"Copied court_config.yaml from {source_path} to {current_dir}")
            found = True
    
    # If we still can't find it, create a default one
    if not found:
        print("WARNING: court_config.yaml not found in repository, creating default version")
        default_court_config = """# Court Configuration
courts:
  - code: ZACC
    name: Constitutional Court of South Africa
    url: https://www.saflii.org/za/cases/ZACC/
    priority: 1
    scrape_method: saflii
  - code: ZASCA
    name: Supreme Court of Appeal
    url: https://www.saflii.org/za/cases/ZASCA/
    priority: 2
    scrape_method: saflii
  - code: ZAGPPHC
    name: Gauteng Division, Pretoria
    url: https://www.saflii.org/za/cases/ZAGPPHC/
    priority: 3
    scrape_method: saflii
  - code: ZAWCHC
    name: Western Cape Division, Cape Town
    url: https://www.saflii.org/za/cases/ZAWCHC/
    priority: 4
    scrape_method: saflii
  - code: ZAKZDHC
    name: KwaZulu-Natal Division, Durban
    url: https://www.saflii.org/za/cases/ZAKZDHC/
    priority: 5
    scrape_method: saflii
"""
        with open(court_config_path, 'w') as f:
            f.write(default_court_config)
        print(f"Created default court_config.yaml at {court_config_path}")
        
# Copy to stages directory as well to ensure scripts can find it there
stages_dir = os.path.join(root_dir, 'stages')
if os.path.exists(stages_dir) and os.path.exists(court_config_path):
    stages_config_path = os.path.join(stages_dir, 'court_config.yaml')
    shutil.copy2(court_config_path, stages_config_path)
    print(f"Copied court_config.yaml to stages directory at {stages_config_path}")

# Set up Django
try:
    print("Python path before import:", sys.path)
    # Add the current directory to the Python path
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    
    # Print the files in the current directory to ensure zalr_backend exists
    print("Files in current directory:", os.listdir(os.path.dirname(__file__)))
    
    # If the zalr_backend directory exists, print its contents
    backend_dir = os.path.join(os.path.dirname(__file__), 'zalr_backend')
    if os.path.exists(backend_dir):
        print("Files in zalr_backend directory:", os.listdir(backend_dir))
        
    # Print environment variables
    print("DJANGO_SETTINGS_MODULE =", os.environ.get("DJANGO_SETTINGS_MODULE"))
    
    # Use the right settings module
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "zalr_backend.github_actions")
    
    # Try to import django and set it up
    import django
    django.setup()
    print("Django successfully initialized with settings:", os.environ.get("DJANGO_SETTINGS_MODULE"))
    
    # Verify Django is working by importing a model
    from django.conf import settings
    print("Django settings loaded:", settings.INSTALLED_APPS)
    
except Exception as e:
    print(f"Error setting up Django: {str(e)}")
    import traceback
    traceback.print_exc()
    print("\nTrying to continue anyway...\n")

# Check for required API keys
required_keys = {
    "OPENAI_API_KEY": "OpenAI API key for text generation",
    "VOYAGE_API_KEY": "Voyage AI API key for embeddings in stage 3",
    "SUPABASE_URL": "Supabase URL for database access",
    "SUPABASE_PUBLIC_KEY": "Supabase public key for database access"
}

missing_keys = []
for key, description in required_keys.items():
    if not os.environ.get(key):
        missing_keys.append(f"{key} ({description})")

if missing_keys:
    print("\n⚠️ WARNING: The following required environment variables are missing:")
    for key in missing_keys:
        print(f"  - {key}")
    print("\nSome stages may fail if these keys are not provided.")
    print("Please add them to your environment or .env file.")
    
    # Check if running in GitHub Actions
    in_github_actions = os.environ.get('GITHUB_ACTIONS') == 'true'
    
    if args.debug or in_github_actions:
        print("\nContinuing anyway in CI/debug mode...\n")
    else:
        proceed = input("\nDo you want to continue anyway? (y/n): ")
        if proceed.lower() != 'y':
            print("Aborting.")
            sys.exit(1)
        print()
else:
    print("All required API keys found in environment variables.")

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