# Doc Scraper

A flexible documentation crawler that can scrape and process documentation from any website.

## Installation

First install dependencies:
```bash
pip install -r requirements.txt
```

Then install the package in editable mode:
```bash
pip install -e .
```

The `-e` flag installs the package in "editable" mode, which means:
- The package is installed in your Python environment
- Python looks for the package in your current directory instead of copying files
- Changes to the source code take effect immediately without reinstalling
- Required for running the package as a module with `python -m`

### Environment Setup

Create a `.env` file in the project root:
```bash
OPENAI_API_KEY=your_api_key_here
```

⚠️ The OpenAI API key is required for the crawler to process documentation.

## Usage

Run the scraper with a URL from the `src` directory:

```bash
cd src
python main.py https://docs.example.com
```

### Optional Arguments

- `-o, --output`: Output directory (default: output_docs)
- `-m, --max-pages`: Maximum pages to scrape (default: 1000)
- `-c, --concurrent`: Number of concurrent pages to scrape (default: 1)

Example with all options:
```bash
python main.py https://docs.example.com -o my_docs -m 500 -c 2
```

### Troubleshooting

If you get a "ModuleNotFoundError", make sure you:
1. Have run `pip install -e .` from the project root
2. Are running the command from the `src` directory

## Configuration

The crawler accepts the following parameters:

- `base_url`: The starting URL to crawl
- `output_dir`: Directory where scraped docs will be saved
- `max_pages`: Maximum number of pages to crawl
- `max_concurrent_pages`: Number of concurrent pages to process

## Requirements

- Python 3.8+
- Chrome/Chromium browser (for Selenium)
