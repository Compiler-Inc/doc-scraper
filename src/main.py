from doc_crawler import DocCrawler
import asyncio
import argparse

async def main():
    parser = argparse.ArgumentParser(description='Scrape documentation from a website')
    parser.add_argument('url', help='The base URL to scrape')
    parser.add_argument('--output', '-o', default='output_docs', help='Output directory for docs')
    parser.add_argument('--max-pages', '-m', type=int, default=1000, help='Maximum pages to scrape')
    parser.add_argument('--concurrent', '-c', type=int, default=1, help='Number of concurrent pages to scrape')
    
    args = parser.parse_args()

    crawler = DocCrawler(
        base_url=args.url,
        output_dir=args.output,
        max_pages=args.max_pages,
        max_concurrent_pages=args.concurrent
    )

    await crawler.crawl()

if __name__ == "__main__":
    asyncio.run(main()) 