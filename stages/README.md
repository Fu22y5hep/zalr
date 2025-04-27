# ZALR Processing Pipeline

This directory contains scripts for processing judgments through the ZALR pipeline. The pipeline consists of 8 stages, from scraping judgments to classifying practice areas.

## Consolidated CLI Tool

We have consolidated all individual wrapper scripts into a single CLI tool called `zalr_cli.py`. This tool provides a simpler and more consistent interface for running the various pipeline stages.

### Installation

No special installation is required. Just make sure the `zalr` script is executable:

```bash
chmod +x zalr
```

### Usage

The `zalr` command provides several subcommands:

#### List Available Stages

```bash
./zalr list
```

#### Run a Specific Stage

```bash
./zalr run --stage 1 --year 2023 --court ZACC
```

#### Run Multiple Stages

```bash
./zalr run --stages 1,2,3 --year 2023 --court ZACC
```

#### Run All Stages

```bash
./zalr run-all --year 2023 --court ZACC
```

### Common Options

These options apply to all commands:

- `--year` - Year to process (required)
- `--court` - Court code to process (e.g., ZACC) (optional, processes all courts if not specified)
- `--batch-size` - Batch size for processing (optional)
- `--prevent-sleep` - Prevent system from sleeping during processing (optional, macOS only)

### Stage-Specific Options

These options apply to specific stages:

- `--timeout` - Timeout in seconds (Stage 1)
- `--max-retries` - Max number of retries (Stages 1 and 4)
- `--chunk-size` - Size of each chunk (Stage 3)
- `--overlap` - Overlap between chunks (Stage 3)
- `--model` - Model to use (Stages 4-8, default: gpt-4o-mini)
- `--max-tokens` - Max tokens for summary (Stage 7)
- `--min-reportability` - Minimum reportability score for Stage 7 (default: 75)

## Pipeline Stages

The pipeline consists of the following stages:

1. **Stage 1: Scrape Judgments**
   - Scrapes judgments from the source
   - Args: year, court, batch_size, timeout, max_retries

2. **Stage 2: Fix Metadata**
   - Fixes and enhances judgment metadata
   - Args: year, court, batch_size

3. **Stage 3: Chunk Judgments**
   - Splits judgments into chunks
   - Args: year, court, batch_size, chunk_size, overlap

4. **Stage 4: Generate Embeddings**
   - Generates embeddings for judgment chunks
   - Args: year, court, batch_size, model, max_retries

5. **Stage 5: Generate Short Summaries**
   - Generates short summaries for judgments
   - Args: year, court, batch_size, model

6. **Stage 6: Calculate Reportability**
   - Calculates reportability scores
   - Args: year, court, batch_size, model

7. **Stage 7: Generate Long Summaries**
   - Generates detailed summaries for judgments with reportability ≥ min_reportability
   - Args: year, court, batch_size, model, max_tokens, min_reportability

8. **Stage 8: Classify Practice Areas**
   - Classifies practice areas
   - Args: year, court, batch_size, model

## Examples

### Process All Stages for a Specific Court/Year

```bash
./zalr run-all --year 2023 --court ZACC --model gpt-4o-mini
```

### Process Only the Scraping and Metadata Stages

```bash
./zalr run --stages 1,2 --year 2023 --court ZACC
```

### Process Embedding Generation with Custom Batch Size

```bash
./zalr run --stage 4 --year 2023 --court ZACC --batch-size 5 --model gpt-4o-mini
```

### Generate Long Summaries Only for Highly Reportable Cases

```bash
./zalr run --stage 7 --year 2023 --court ZACC --min-reportability 80 --model gpt-4o-mini
```

### Process All Stages Without Letting the System Sleep

```bash
./zalr run-all --year 2023 --court ZACC --prevent-sleep
``` 