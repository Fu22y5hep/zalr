#!/usr/bin/env python3
"""
Simple script to run the ZALR pipeline, trying multiple approaches.
This acts as a failsafe in case the other scripts are not working.
"""

import os
import sys
import subprocess
import logging
from datetime import datetime

# Set up logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"pipeline_runner_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

def run_command(cmd):
    """Run a shell command and log output"""
    logging.info(f"Running command: {cmd}")
    try:
        process = subprocess.Popen(
            cmd, 
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Stream and log output
        for line in process.stdout:
            logging.info(line.strip())
        
        # Get return code
        process.wait()
        if process.returncode != 0:
            logging.error(f"Command failed with return code {process.returncode}")
            for line in process.stderr:
                logging.error(line.strip())
            return False
        
        return True
    except Exception as e:
        logging.error(f"Error running command: {str(e)}")
        return False

def main():
    if len(sys.argv) < 2:
        logging.error("Missing year parameter. Usage: python run_pipeline.py <year> [court]")
        sys.exit(1)
    
    year = sys.argv[1]
    court = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Approach 1: Try zalr script
    if os.path.exists("stages/zalr"):
        logging.info("Found stages/zalr script")
        os.chmod("stages/zalr", 0o755)  # Make executable
        cmd = f"./stages/zalr run-all --year {year}"
        if court:
            cmd += f" --court {court}"
        
        if run_command(cmd):
            logging.info("Pipeline completed successfully using zalr script")
            return
    
    # Approach 2: Try zalr_cli.py
    if os.path.exists("stages/zalr_cli.py"):
        logging.info("Found stages/zalr_cli.py")
        cmd = f"python stages/zalr_cli.py run-all --year {year}"
        if court:
            cmd += f" --court {court}"
        
        if run_command(cmd):
            logging.info("Pipeline completed successfully using zalr_cli.py")
            return
    
    # Approach 3: Try individual stage modules
    if os.path.exists("stages/stage1_scrape_judgments.py"):
        logging.info("Found individual stage modules, running them in sequence")
        stages = [
            "stages/stage1_scrape_judgments.py",
            "stages/stage2_fix_metadata.py",
            "stages/stage3_chunk_judgments.py",
            "stages/stage4_generate_embeddings.py",
            "stages/stage5_generate_short_summaries.py",
            "stages/stage6_calculate_reportability.py",
            "stages/stage7_generate_long_summaries.py",
        ]
        
        for stage in stages:
            if not os.path.exists(stage):
                logging.warning(f"Stage file {stage} not found, skipping")
                continue
                
            cmd = f"python {stage} --year {year}"
            if court:
                cmd += f" --court {court}"
            
            if not run_command(cmd):
                logging.error(f"Stage {stage} failed, stopping pipeline")
                break
    
    # Approach 4: Fall back to run_all_stages.py
    elif os.path.exists("run_all_stages.py"):
        logging.info("Found run_all_stages.py")
        cmd = f"python run_all_stages.py --year {year}"
        if court:
            cmd += f" --court {court}"
        
        if run_command(cmd):
            logging.info("Pipeline completed successfully using run_all_stages.py")
            return
    
    else:
        logging.error("No suitable scripts found to run the pipeline.")
        # Print directory structure for debugging
        run_command("find . -name '*.py' | grep -E 'stage|zalr'")
        sys.exit(1)

if __name__ == "__main__":
    main() 