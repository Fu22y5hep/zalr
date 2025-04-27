#!/usr/bin/env python3
"""
Simple script to simulate running the pipeline stages for GitHub Actions testing.
This script doesn't actually run the real processing, but creates logs as if it did.
"""

import os
import sys
import time
import logging
import random
from datetime import datetime, timedelta

# Set up logging
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"simple_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

def simulate_stage(stage_num, stage_name, year, duration_range=(1, 5)):
    """Simulate running a stage with logging and random duration"""
    duration = random.uniform(*duration_range)
    
    logging.info(f"Stage {stage_num}: {stage_name}")
    logging.info(f"Processing year: {year}")
    
    # Simulate some progress logs
    courts = ["ZACC", "ZASCA", "ZAGPPHC", "ZAWCHC", "ZAKZDHC"]
    total_processed = 0
    
    start_time = time.time()
    
    # Log some fake progress
    for court in courts:
        count = random.randint(5, 25)
        total_processed += count
        time.sleep(duration / len(courts))  # Spread the duration across courts
        logging.info(f"Processed {count} judgments from {court} {year}")
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    logging.info(f"Stage {stage_num} completed in {elapsed:.2f} seconds")
    logging.info(f"Total processed in stage {stage_num}: {total_processed} items")
    
    return {
        "stage": stage_num,
        "name": stage_name,
        "processed": total_processed,
        "duration": elapsed
    }

def run_pipeline(year):
    """Run the simulated pipeline stages"""
    stages = [
        (1, "Scraping Judgments", (3, 8)),
        (2, "Fixing Metadata", (2, 5)),
        (3, "Chunking Judgments", (4, 10)),
        (4, "Generating Embeddings", (10, 20)),
        (5, "Generating Short Summaries", (15, 30)),
        (6, "Calculating Reportability Scores", (5, 10)),
        (7, "Generating Long Summaries", (20, 40)),
        (8, "Classifying Practice Areas", (10, 15))
    ]
    
    overall_start = time.time()
    results = []
    
    logging.info(f"Starting pipeline for year: {year}")
    logging.info("=" * 50)
    
    # Run each stage
    for stage_num, stage_name, duration_range in stages:
        result = simulate_stage(stage_num, stage_name, year, duration_range)
        results.append(result)
        logging.info("-" * 50)
    
    overall_end = time.time()
    total_duration = overall_end - overall_start
    hours, remainder = divmod(total_duration, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Final summary
    logging.info("=" * 50)
    logging.info(f"Pipeline completed successfully for year {year}")
    logging.info(f"Total duration: {int(hours)}h {int(minutes)}m {int(seconds)}s")
    logging.info(f"Total items processed: {sum(r['processed'] for r in results)}")
    
    # Generate a sample output file
    output_file = os.path.join(log_dir, f"pipeline_results_{year}_{datetime.now().strftime('%Y%m%d')}.json")
    with open(output_file, "w") as f:
        import json
        f.write(json.dumps({
            "year": year,
            "run_date": datetime.now().isoformat(),
            "duration_seconds": total_duration,
            "stages": results
        }, indent=2))
    
    logging.info(f"Results saved to {output_file}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        year = datetime.now().year
        logging.info(f"No year specified, using current year: {year}")
    else:
        year = int(sys.argv[1])
    
    run_pipeline(year) 