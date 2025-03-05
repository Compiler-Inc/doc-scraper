import openai
import os
import time
import logging
import asyncio
from dotenv import load_dotenv
from typing import Optional, List
from time import perf_counter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()


class GPTHelper:
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment variables")
        self.client = openai.AsyncOpenAI(api_key=self.api_key)
        self.max_retries = 3
        self.chunk_size = 2000
        self.timeout = 90  # Increased to 90 seconds
        self.total_api_time = 0
        self.total_api_calls = 0
        self.max_concurrent_calls = 2  # Reduced to 2 concurrent calls for better stability
        self._semaphore = asyncio.Semaphore(self.max_concurrent_calls)
        logger.info(f"GPTHelper initialized (max {self.max_concurrent_calls} concurrent calls)")
        
    async def _call_gpt(self, content: str, retries: int = 0, system_message: str = None) -> Optional[str]:
        """Make a single GPT API call with retry logic."""
        async with self._semaphore:
            try:
                logger.info(f"Making GPT API call (attempt {retries + 1})")
                start_time = perf_counter()

                # Use default system message if none provided
                if system_message is None:
                    system_message = """You are an expert Apple framework documentation engineer. Format this documentation chunk into clean markdown.
Focus on:
• Framework overview and concepts
• Types, protocols, and class hierarchies
• Method and property declarations
• Code examples and usage patterns
• Best practices and implementation guidelines

Use these formatting rules:
• Use Apple-style hierarchical headings
• Format Swift code blocks with proper syntax highlighting
• Use tables for parameter and return value descriptions
• Use blockquotes for important notes and warnings
• Preserve all declaration syntax and type information
• Keep working code examples
• Maintain Apple's technical accuracy and terminology
• Include relevant privacy and entitlement requirements
• Preserve framework version and availability information
• Format symbol references with proper linking syntax

Structure sections as:
1. Overview/Introduction
2. Topics
3. Declarations
4. Discussion
5. Parameters/Return Value
6. See Also/Related"""

                try:
                    response = await self.client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": system_message
                            },
                            {
                                "role": "user",
                                "content": content
                            }
                        ],
                        temperature=0.1,
                        timeout=self.timeout
                    )
                    
                    end_time = perf_counter()
                    duration = end_time - start_time
                    self.total_api_time += duration
                    self.total_api_calls += 1
                    avg_time = self.total_api_time / self.total_api_calls
                    
                    logger.info(f"GPT API call successful - Took {duration:.2f}s (Avg: {avg_time:.2f}s)")
                    return response.choices[0].message.content
                    
                except openai.APIError as e:
                    logger.error(f"OpenAI API Error: {str(e)}")
                    if "model not found" in str(e).lower():
                        logger.error("Invalid model name. Please check your OpenAI API access and model name.")
                    raise
                
            except openai.APITimeoutError:
                logger.warning(f"Timeout error (attempt {retries + 1})")
                if retries < self.max_retries:
                    await asyncio.sleep(2 ** retries)
                    return await self._call_gpt(content, retries + 1, system_message)
                raise
                
            except openai.RateLimitError:
                logger.warning(f"Rate limit error (attempt {retries + 1})")
                await asyncio.sleep(20)
                if retries < self.max_retries:
                    return await self._call_gpt(content, retries + 1, system_message)
                raise
                
            except Exception as e:
                logger.error(f"Error in GPT call: {str(e)}")
                if retries < self.max_retries:
                    await asyncio.sleep(2 ** retries)
                    return await self._call_gpt(content, retries + 1, system_message)
                return f"Error processing chunk: {str(e)}"

    def _split_into_chunks(self, text: str) -> list[str]:
        """Split text into processable chunks while preserving markdown structure."""
        chunks = []
        current_chunk = []
        current_size = 0
        
        blocks = text.split('\n\n')
        logger.info(f"Splitting content into chunks (total blocks: {len(blocks)})")
        
        for block in blocks:
            block_size = len(block)
            
            if current_size + block_size > self.chunk_size:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                current_chunk = [block]
                current_size = block_size
            else:
                current_chunk.append(block)
                current_size += block_size
        
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))
        
        logger.info(f"Created {len(chunks)} chunks")
        return chunks

    async def format_documentation(self, content: str) -> str:
        """Process documentation chunks in parallel and combine results."""
        try:
            start_time = perf_counter()
            logger.info("Starting documentation formatting")
            chunks = self._split_into_chunks(content)
            
            # Process all chunks in parallel
            tasks = [self._call_gpt(chunk) for chunk in chunks]
            formatted_chunks = await asyncio.gather(*tasks)
            formatted_chunks = [chunk for chunk in formatted_chunks if chunk]
            
            logger.info("Combining chunks")
            combined = '\n\n---\n\n'.join(formatted_chunks)
            
            end_time = perf_counter()
            total_duration = end_time - start_time
            logger.info(f"Documentation formatting completed - Total time: {total_duration:.2f}s, API calls: {self.total_api_calls}, Avg API time: {self.total_api_time/self.total_api_calls:.2f}s")
            return combined
            
        except Exception as e:
            logger.error(f"Error in format_documentation: {str(e)}")
            return f"Error formatting documentation: {str(e)}"

    async def final_review(self, content: str) -> str:
        """Perform a final review of the entire documentation."""
        try:
            logger.info("Starting final documentation review")
            start_time = perf_counter()

            # Split into larger chunks for final review since we're just cleaning up
            original_chunk_size = self.chunk_size
            self.chunk_size = 4000  # Temporarily increase chunk size
            chunks = self._split_into_chunks(content)
            self.chunk_size = original_chunk_size

            review_tasks = []
            for chunk in chunks:
                task = self._call_gpt(
                    chunk,
                    system_message="""You are an expert technical documentation reviewer. Review and improve this API documentation chunk.
Focus on:
1. Removing any duplicate content
2. Ensuring consistent formatting and style
3. Making the documentation clear and readable
4. Proper markdown formatting
5. Consistent heading hierarchy
6. Proper section breaks
7. Complete and accurate endpoint documentation
8. Consistent use of code blocks and tables
9. Clear parameter descriptions
10. Proper grouping of related endpoints

Keep all valid API endpoint information but make it more concise and well-organized."""
                )
                review_tasks.append(task)

            # Process review chunks in parallel
            reviewed_chunks = await asyncio.gather(*review_tasks)
            reviewed_chunks = [chunk for chunk in reviewed_chunks if chunk]
            
            # Combine reviewed chunks
            logger.info("Combining reviewed chunks")
            combined = '\n\n'.join(reviewed_chunks)

            # Final pass to ensure consistency across the entire document
            logger.info("Making final consistency pass")
            final_content = await self._call_gpt(
                combined,
                system_message="""You are an expert technical documentation editor. This is the final pass of the API documentation.
Your task is to ensure the entire document is consistent and well-organized.

Focus on:
1. Consistent structure throughout the document
2. Clear and logical organization of endpoints
3. Proper table of contents
4. Consistent heading levels
5. Remove any remaining duplicates
6. Ensure all cross-references are valid
7. Consistent formatting of endpoints, parameters, and examples
8. Group related endpoints together
9. Add clear section dividers
10. Ensure all API information is accurate and complete

Maintain all API endpoint information but make it as clear and well-organized as possible."""
            )

            end_time = perf_counter()
            total_duration = end_time - start_time
            logger.info(f"Final review completed - Total time: {total_duration:.2f}s")
            
            return final_content or combined

        except Exception as e:
            logger.error(f"Error in final review: {str(e)}")
            return content  # Return original content if review fails
