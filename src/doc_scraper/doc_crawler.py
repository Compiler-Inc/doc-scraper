import os
import logging
import asyncio
from urllib.parse import urljoin, urlparse
from typing import Set, Dict
from .gpt_helper import GPTHelper
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocCrawler:
    def __init__(
        self,
        base_url: str,
        output_dir: str = "coinbase_docs",
        max_pages: int = 50,
        max_concurrent_pages: int = 3
    ):
        self.base_url = base_url
        self.base_domain = urlparse(base_url).netloc
        self.output_dir = output_dir
        self.max_pages = max_pages
        self.max_concurrent_pages = max_concurrent_pages
        self.visited_urls: Set[str] = set()
        self.processed_content: Dict[str, str] = {}
        self.gpt_helper = GPTHelper()
        self._page_semaphore = asyncio.Semaphore(max_concurrent_pages)

        # Initialize Selenium
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        os.makedirs(output_dir, exist_ok=True)

        # Add progress tracking
        self.total_processed = 0
        logger.info(f"Initializing crawler for {base_url}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Maximum pages to crawl: {max_pages}")
        logger.info(f"Maximum concurrent pages: {max_concurrent_pages}")

    def __del__(self):
        """Clean up Selenium driver"""
        if hasattr(self, 'driver'):
            self.driver.quit()

    def is_relevant_url(self, url: str) -> bool:
        """Check if URL is relevant to the HealthKit documentation."""
        parsed = urlparse(url)

        # Must be Apple developer domain
        if parsed.netloc != "developer.apple.com":
            return False

        # Must be in the HealthKit documentation section
        if '/documentation/healthkit' not in url:
            return False

        # Skip non-documentation paths
        skip_patterns = [
            '/videos', '/downloads', '/forums', '/account',
            '/search', '/feedback', '/contact',
            '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip'
        ]
        return not any(pattern in url.lower() for pattern in skip_patterns)

    def extract_content(self, url: str) -> str:
        """Extract relevant content from the Apple documentation page."""
        try:
            logger.info(f"Loading page with Selenium: {url}")
            self.driver.get(url)

            # Wait for the main content to load (Apple docs specific)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "main"))
            )

            # Give a bit more time for dynamic content
            time.sleep(2)

            # Get the title
            try:
                title = self.driver.find_element(By.CLASS_NAME, "title").text
            except:
                try:
                    title = self.driver.find_element(By.TAG_NAME, "h1").text
                except:
                    title = ""

            # Get the main content sections
            content_parts = []
            
            # Add title
            if title:
                content_parts.append(f"# {title}\n")

            try:
                # Get abstract/introduction
                abstract = self.driver.find_element(By.CLASS_NAME, "abstract")
                if abstract:
                    content_parts.append(abstract.text + "\n")

                # Get main content sections
                content_sections = self.driver.find_elements(By.CLASS_NAME, "content")
                for section in content_sections:
                    content_parts.append(section.text + "\n")

                # Get code samples
                code_blocks = self.driver.find_elements(By.CLASS_NAME, "code-listing")
                for block in code_blocks:
                    try:
                        language = block.get_attribute("data-language") or "swift"
                        code = block.text
                        content_parts.append(f"\n```{language}\n{code}\n```\n")
                    except:
                        continue

                # Get declaration sections
                declarations = self.driver.find_elements(By.CLASS_NAME, "declaration")
                for decl in declarations:
                    content_parts.append("\n### Declaration\n")
                    content_parts.append("```swift\n" + decl.text + "\n```\n")

            except Exception as e:
                logger.warning(f"Error extracting specific content: {str(e)}")

            content = "\n".join(content_parts)

            if not content:
                logger.warning("Could not find main content")
                return ""

            return content

        except Exception as e:
            logger.error(f"Error extracting content: {str(e)}")
            return ""

    def get_page_links(self) -> Set[str]:
        """Get all links from the current page."""
        links = set()
        try:
            elements = self.driver.find_elements(By.TAG_NAME, "a")
            for element in elements:
                href = element.get_attribute('href')
                if href:
                    full_url = urljoin(self.base_url, href)
                    if self.is_relevant_url(full_url) and full_url not in self.visited_urls:
                        links.add(full_url)
        except Exception as e:
            logger.error(f"Error getting links: {str(e)}")
        return links

    async def process_page(self, url: str) -> None:
        """Process a single page asynchronously."""
        async with self._page_semaphore:
            try:
                content = self.extract_content(url)

                if content:
                    logger.info("Content extracted successfully")
                    logger.info("Sending to GPT for formatting...")

                    formatted_content = await self.gpt_helper.format_documentation(content)
                    self.processed_content[url] = formatted_content
                    logger.info("Content formatted successfully")

                    # Get new URLs to process
                    new_urls = self.get_page_links()
                    new_urls = {u for u in new_urls if u not in self.visited_urls}
                    return new_urls
                else:
                    logger.warning(f"No relevant content found at: {url}")
                    return set()

            except Exception as e:
                logger.error(f"Error processing {url}")
                logger.error(f"Error details: {str(e)}")
                return set()

    def save_documentation(self):
        """Save all processed content into a single markdown file."""
        output_file = os.path.join(self.output_dir, "api_documentation.md")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("# API Documentation\n\n")
            f.write("## Table of Contents\n\n")

            # Write table of contents
            for url in self.processed_content.keys():
                section_name = url.split('/')[-1].replace('-', ' ').title()
                anchor = url.split('/')[-1].lower()
                f.write(f"- [{section_name}](#{anchor})\n")

            f.write("\n---\n\n")

            # Write content
            for url, content in self.processed_content.items():
                section_name = url.split('/')[-1].replace('-', ' ').title()
                f.write(f"## {section_name}\n\n")
                f.write(f"Source: {url}\n\n")
                f.write(content)
                f.write("\n\n---\n\n")

        logger.info(f"Documentation saved to: {output_file}")

    async def crawl(self) -> None:
        """Crawl the documentation and save as a single markdown file."""
        urls_to_visit = {self.base_url}
        tasks = []

        logger.info("Starting crawl process...")
        logger.info(f"Initial URL queue size: 1")

        while urls_to_visit and len(self.visited_urls) < self.max_pages:
            remaining_pages = self.max_pages - len(self.visited_urls)
            queue_size = len(urls_to_visit)

            logger.info(f"\nProgress Update:")
            logger.info(f"Pages processed: {len(self.visited_urls)}")
            logger.info(f"Pages remaining: {remaining_pages}")
            logger.info(f"URLs in queue: {queue_size}")
            logger.info(
                f"Completion: {(len(self.visited_urls) / self.max_pages) * 100:.1f}%")

            # Process up to max_concurrent_pages pages in parallel
            current_batch = []
            while urls_to_visit and len(current_batch) < self.max_concurrent_pages:
                url = urls_to_visit.pop()
                if url not in self.visited_urls:
                    current_batch.append(url)
                    self.visited_urls.add(url)

            if current_batch:
                # Process the batch in parallel
                batch_tasks = [self.process_page(url) for url in current_batch]
                new_urls_list = await asyncio.gather(*batch_tasks)
                
                # Add new URLs to visit
                for new_urls in new_urls_list:
                    urls_to_visit.update(new_urls)

                # Save progress after each batch
                self.save_documentation()

        # Perform final review of the entire documentation
        if self.processed_content:
            logger.info("\nPerforming final documentation review...")
            
            # Read the current documentation file
            output_file = os.path.join(self.output_dir, "api_documentation.md")
            with open(output_file, 'r', encoding='utf-8') as f:
                current_content = f.read()
            
            # Perform the final review
            reviewed_content = await self.gpt_helper.final_review(current_content)
            
            # Save the reviewed documentation
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(reviewed_content)
            
            logger.info("Final documentation review completed!")

        logger.info("Crawl completed!")
