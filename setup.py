from setuptools import setup, find_packages

setup(
    name="doc_scraper",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "selenium>=4.0.0",
        "webdriver-manager>=3.8.0",
        "aiohttp>=3.8.0",
        "openai>=1.0.0",
        "beautifulsoup4>=4.9.0",
        "python-dotenv>=0.19.0"
    ],
    python_requires=">=3.8",
) 