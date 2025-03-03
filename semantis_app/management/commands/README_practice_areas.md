# Practice Area Classification

This Django management command classifies legal judgments into practice areas based on their short summaries.

## Overview

The script uses a hybrid approach for classification:

1. **Rule-based classification**: First attempts to match keywords from the summary to practice areas
2. **Zero-shot classification**: If rule-based is inconclusive, uses Hugging Face's zero-shot classification
3. **OpenAI GPT fallback**: If zero-shot fails, tries OpenAI's GPT-4o-mini model
4. **Simple keyword matching**: If OpenAI API fails, falls back to a simple keyword matching approach
5. **Default fallback**: If all methods fail, the judgment is labeled as "Not Classified"

## Requirements

- Python 3.8+
- Django
- transformers
- torch
- openai

## Usage

Run the command with:

```bash
python manage.py classify_practice_areas [options]
```

### Options

- `--batch-size`: Number of judgments to process (default: 20)
- `--force`: Process all judgments, even those that already have practice areas. By default, the script only processes judgments with no practice area or those marked as "Not Classified".

### Examples

Process 10 judgments:
```bash
python manage.py classify_practice_areas --batch-size 10
```

Process all judgments, including those already classified with valid practice areas:
```bash
python manage.py classify_practice_areas --force
```

## Practice Areas

The practice areas are defined in `semantis_app/config/practice_areas.yaml` and include:

1. ADMINISTRATIVE LAW
2. COMMERCIAL LAW
3. COMPETITION LAW
4. CONSTITUTIONAL LAW
5. CRIMINAL LAW
6. DELICTUAL LAW
7. ENVIRONMENTAL LAW
8. FAMILY LAW
9. INSURANCE LAW
10. INTELLECTUAL PROPERTY LAW
11. LABOUR LAW
12. LAND AND PROPERTY LAW
13. PRACTICE AND PROCEDURE
14. TAX LAW
15. ARBITRATION

## How It Works

1. The script loads practice areas and their keywords from the YAML file
2. It enhances the keywords map with additional common keywords
3. For each judgment with a short summary:
   - First tries rule-based classification using keywords
   - If inconclusive, uses zero-shot classification
   - If still inconclusive, uses OpenAI GPT
   - If OpenAI API fails, uses a simple keyword matching approach
   - If all methods fail, assigns "Not Classified" as the practice area
4. The classified practice area is saved to the judgment's `practice_area` field

## Troubleshooting

- Ensure your OpenAI API key is set in the environment variables
- Check that the practice areas YAML file exists and is properly formatted
- If classification seems inaccurate, you may need to adjust the keywords or thresholds 