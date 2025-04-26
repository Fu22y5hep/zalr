import os
import sys
import subprocess
import argparse
import time
import logging
from datetime import datetime

# Set up logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = os.path.join(log_dir, f'run_all_stages_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler(sys.stdout)
    ]
)

def run_command(command):
    """Run a shell command and log output"""
    logging.info(f"Running command: {command}")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # Stream and log output in real-time
        while True:
            stdout_line = process.stdout.readline()
            stderr_line = process.stderr.readline()
            
            if stdout_line:
                logging.info(stdout_line.strip())
            if stderr_line:
                logging.warning(stderr_line.strip())
                
            return_code = process.poll()
            if return_code is not None:
                # Process remaining output
                for stdout_line in process.stdout:
                    logging.info(stdout_line.strip())
                for stderr_line in process.stderr:
                    logging.warning(stderr_line.strip())
                break
        
        if return_code != 0:
            logging.error(f"Command failed with return code {return_code}")
            return False
            
        return True
    except Exception as e:
        logging.error(f"Error running command: {str(e)}")
        return False

def run_stage(stage_num, year, court=None, batch_size=None, min_reportability=None, force=False):
    """Run a specific stage of the processing pipeline"""
    # Path to manage.py - in the root directory
    manage_py = "./manage.py"
    
    # Stage command mapping - use short command names without namespace
    stage_commands = {
        1: "stage1_scrape_judgments",
        2: "stage2_fix_metadata",
        3: "stage3_chunk_judgments",
        4: "stage4_generate_embeddings",
        5: "stage5_generate_short_summaries",
        6: "stage6_calculate_reportability",
        7: "stage7_generate_long_summaries"
    }
    
    command = f"python {manage_py} {stage_commands[stage_num]}"
    
    if court:
        command += f" --court {court}"
    
    command += f" --year {year}"
    
    if batch_size and stage_num >= 3:  # Only apply batch size to stages 3+
        command += f" --batch-size {batch_size}"
    
    if stage_num == 7 and min_reportability:
        command += f" --min-reportability {min_reportability}"
    
    if force and stage_num >= 3:  # Only apply force to stages 3+
        command += " --force"
    
    stage_names = {
        1: "Scraping Judgments",
        2: "Fixing Metadata",
        3: "Chunking Judgments",
        4: "Generating Embeddings",
        5: "Generating Short Summaries",
        6: "Calculating Reportability Scores",
        7: "Generating Long Summaries"
    }
    
    logging.info(f"Stage {stage_num}: {stage_names[stage_num]}")
    return run_command(command)

def run_all_stages(year, court=None, min_reportability=0.7, force=False):
    """Run all stages of the processing pipeline"""
    start_time = time.time()
    
    # Configure batch sizes for different stages
    batch_sizes = {
        1: None,  # No batch size for scraping
        2: None,  # No batch size for metadata fixing
        3: 20,    # Chunking batch size
        4: 30,    # Embeddings batch size
        5: 15,    # Short summaries batch size
        6: 15,    # Reportability batch size
        7: 5      # Long summaries batch size (smaller due to intensity)
    }
    
    logging.info(f"Starting all stages for year: {year}" + (f", court: {court}" if court else ", all courts"))
    
    # Run stages 1-7 in sequence
    for stage in range(1, 8):
        stage_start = time.time()
        success = run_stage(
            stage, 
            year, 
            court=court, 
            batch_size=batch_sizes[stage],
            min_reportability=min_reportability if stage == 7 else None,
            force=force
        )
        stage_end = time.time()
        
        if not success:
            logging.error(f"Stage {stage} failed. Stopping pipeline.")
            return False
            
        logging.info(f"Stage {stage} completed in {stage_end - stage_start:.2f} seconds")
    
    end_time = time.time()
    total_time = end_time - start_time
    hours, remainder = divmod(total_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    logging.info(f"All stages completed successfully in {int(hours)}h {int(minutes)}m {int(seconds)}s")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run all judgment processing stages in sequence")
    parser.add_argument("--year", type=int, required=True, help="Year to process")
    parser.add_argument("--court", type=str, help="Court code to process (e.g., ZACC)")
    parser.add_argument("--min-reportability", type=float, default=0.7, help="Minimum reportability score for long summaries")
    parser.add_argument("--force", action="store_true", help="Force processing even if data already exists")
    
    args = parser.parse_args()
    
    run_all_stages(args.year, args.court, args.min_reportability, args.force) 