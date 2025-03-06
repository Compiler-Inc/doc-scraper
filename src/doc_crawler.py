import os
import logging
import asyncio
from urllib.parse import urljoin, urlparse
from typing import Set, Dict
from gpt_helper import GPTHelper
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
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-web-security")  # Be careful with this in production
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

        # Set page load timeout
        self.driver.set_page_load_timeout(90)

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
        """Check if URL is relevant to the API documentation."""
        parsed = urlparse(url)

        # Must be same domain
        if parsed.netloc != self.base_domain:
            return False

        # Must be in the docs section
        if '/docs/' not in url:
            return False

        # Skip non-documentation paths
        skip_patterns = [
            '/login', '/signin', '/signup', '/register',
            '/contact', '/about', '/pricing', '/blog',
            '.png', '.jpg', '.jpeg', '.gif', '.pdf', '.zip'
        ]
        return not any(pattern in url.lower() for pattern in skip_patterns)

    def extract_content(self, url: str) -> str:
        """Extract relevant content from the page using Selenium."""
        try:
            logger.info(f"Loading page with Selenium: {url}")
            self.driver.get(url)

            # Wait longer for modern web apps to load (90 seconds)
            wait = WebDriverWait(self.driver, 90)

            # First wait for any of these common content containers
            content_selectors = [
                "main",  # Common main content wrapper
                ".theme-doc-markdown",  # Docusaurus
                ".api-content",  # Common API doc class
                "#content",  # Common content ID
                "article"  # Common content wrapper
            ]

            # Wait for the initial content container
            for selector in content_selectors:
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    main_content = self.driver.find_element(By.CSS_SELECTOR, selector)
                    if main_content:
                        # Wait for dynamic content to load
                        logger.info("Waiting for dynamic content to load...")
                        time.sleep(5)  # Give time for dynamic content
                        
                        # Scroll to load all content
                        logger.info("Scrolling to load all content...")
                        last_height = self.driver.execute_script("return document.body.scrollHeight")
                        while True:
                            # Scroll down
                            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(2)  # Wait for content to load
                            
                            # Calculate new scroll height
                            new_height = self.driver.execute_script("return document.body.scrollHeight")
                            if new_height == last_height:
                                break
                            last_height = new_height
                        
                        # Get the content after everything is loaded
                        main_content = self.driver.find_element(By.CSS_SELECTOR, selector)
                        content = main_content.text.strip()
                        if content:
                            logger.info(f"Found content using selector: {selector}")
                            return content
                except Exception as e:
                    logger.debug(f"Selector {selector} not found: {str(e)}")
                    continue

            # If no content found with specific selectors, try getting body content
            logger.info("No specific content container found, trying body...")
            body = self.driver.find_element(By.TAG_NAME, "body")
            if body:
                content = body.text.strip()
                if content:
                    logger.info("Retrieved content from body")
                    return content

            logger.warning("No content containers found")
            return ""

        except Exception as e:
            logger.error(f"Error extracting content: {str(e)}")
            logger.error("Attempting to get page source as fallback...")
            try:
                return self.driver.page_source
            except:
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

    def save_page_content(self, url: str, content: str, formatted_content: str):
        """Save both raw and formatted content for a single page."""
        # Create a valid filename from the URL
        filename = url.split('/')[-1].replace('-', '_')
        if not filename:
            filename = 'index'
        
        # Save raw content
        raw_dir = os.path.join(self.output_dir, 'raw')
        os.makedirs(raw_dir, exist_ok=True)
        raw_file = os.path.join(raw_dir, f"{filename}_raw.txt")
        with open(raw_file, 'w', encoding='utf-8') as f:
            f.write(f"URL: {url}\n\n")
            f.write(content)
        logger.info(f"Raw content saved to: {raw_file}")
        
        # Save formatted content
        formatted_dir = os.path.join(self.output_dir, 'formatted')
        os.makedirs(formatted_dir, exist_ok=True)
        formatted_file = os.path.join(formatted_dir, f"{filename}_formatted.md")
        with open(formatted_file, 'w', encoding='utf-8') as f:
            f.write(f"# {filename.replace('_', ' ').title()}\n\n")
            f.write(f"Source: {url}\n\n")
            f.write(formatted_content)
        logger.info(f"Formatted content saved to: {formatted_file}")

    async def process_page(self, url: str) -> None:
        """Process a single page asynchronously."""
        async with self._page_semaphore:
            try:
                logger.info(f"\n{'='*50}")
                logger.info(f"Processing page: {url}")
                logger.info(f"{'='*50}")
                
                content = self.extract_content(url)

                if not content:
                    logger.warning(f"No content extracted from: {url}")
                    return set()

                logger.info(f"Content extracted successfully ({len(content)} characters)")
                
                # Split content into chunks for better visibility
                chunks = content.split('\n\n')
                logger.info(f"Split into {len(chunks)} content blocks")
                
                # Process content
                try:
                    logger.info("Sending to GPT for formatting...")
                    formatted_content = await self.gpt_helper.format_documentation(content)
                    if formatted_content:
                        logger.info(f"Content formatting successful ({len(formatted_content)} characters)")
                        self.processed_content[url] = formatted_content
                        
                        # Save individual page content
                        self.save_page_content(url, content, formatted_content)
                        
                        # Get new URLs to process
                        logger.info("Extracting links from page...")
                        new_urls = self.get_page_links()
                        new_urls = {u for u in new_urls if u not in self.visited_urls}
                        logger.info(f"Found {len(new_urls)} new URLs to process")
                        
                        logger.info(f"{'='*50}\n")
                        return new_urls
                    else:
                        logger.error("GPT formatting returned empty content")
                        return set()
                except Exception as e:
                    logger.error(f"Error during GPT processing: {str(e)}")
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
