# Doc Scraper

A flexible documentation crawler that can scrape and process documentation from any website.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

Run the scraper with a URL:

```bash
python -m doc_scraper.main https://docs.example.com
```

### Optional Arguments

- `-o, --output`: Output directory (default: output_docs)
- `-m, --max-pages`: Maximum pages to scrape (default: 1000)
- `-c, --concurrent`: Number of concurrent pages to scrape (default: 1)

Example with all options:
```bash
python -m doc_scraper.main https://docs.example.com -o my_docs -m 500 -c 2
```

## Configuration

The crawler accepts the following parameters:

- `base_url`: The starting URL to crawl
- `output_dir`: Directory where scraped docs will be saved
- `max_pages`: Maximum number of pages to crawl
- `max_concurrent_pages`: Number of concurrent pages to process

## Requirements

- Python 3.8+
- Chrome/Chromium browser (for Selenium)
