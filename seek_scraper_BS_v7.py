import aiohttp
import asyncio
import json
import re
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, HttpUrl
import uvicorn
import os
from datetime import datetime
import random

#Import selenium package
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc  # Consider adding this library


#Create the API APP
app = FastAPI(
    title = "Seek Job Scraper API",
    description = "A simple API to scrape job listings from Seek.com.au",
    version = "1.0.0"
)

#Define the data model for the job search
class JobSearchRequest(BaseModel):
    search_url: HttpUrl
    max_pages: Optional[int] = None
    posted_time_limit: Optional[str] = None
    num_jobs: Optional[int] = None


#Create class for all the functions regarding scraping
class SeekScraper:
    
    def __init__(self, use_selenium=True):
        """
        Initialize the scraper with base URL and headers for requests

        Args:
            use_selenium: Boolean to determine to user selenium and not aiohttp
        """
        self.base_url = "https://www.seek.com.au" #Define the main URL that will be used
        self.use_selenium = use_selenium
        self.timeout = 30  # Timeout in seconds for HTTP requests
        
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15'
        ] # set the rotation of browesers
        
        
        if use_selenium:
            self._setup_selenium()
        else:
            # Keep the aiohttp setup as backup
            self.headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            }

    def _setup_selenium(self):
        """
        Set up the Selenium web driver with Chrome
        """
        # Set up the Chrome options
        chrome_options = Options()
        
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-insecure-localhost')
        chrome_options.add_argument('--ignore-ssl-errors=yes')
        chrome_options.add_argument('--disable-web-security')

        # Add headless option for server environments
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")

        # Add additional privacy options to avoid detection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)


        # Set user agent - Picks randomly from the list
        chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")
        
        chromedriver_path = '/usr/local/bin/chromedriver'
        
        self.driver = webdriver.Chrome(
            service=Service(chromedriver_path),
            options=chrome_options
            )
            
        # Set window size
        self.driver.set_window_size(1920, 1080)
        
        # Execute JavaScript to mask WebDriver presence
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")     
        

    async def __aenter__(self): #This will open the session in the browser
                
        """Set up resources when entering context"""

        if not self.use_selenium:
            # Only set up aiohttp if not using Selenium
            self.session = aiohttp.ClientSession(headers=self.headers)
            
            # Make an initial request to get cookies
            try:
                async with self.session.get(self.base_url) as response:
                    if response.status == 200:
                        print("Successfully initialized session with cookies")
            except Exception as e:
                print(f"Error initializing session: {str(e)}")
                
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb): #this will close the session 
        """Clean up resources when exiting context"""
        if self.use_selenium:
            self.driver.quit()
        else:
            await self.session.close()

    def extract_job_id(self, url: str) -> str: #defines the function with the variable self and the needed url (this URL contains the job_id)
        """
        Extract job ID from URL.
        
        Args:
            url: The job posting URL
            
        Returns:
            The job ID extracted from the URL
        """
        try: #uses try loop
            # Find the part after 'job/' and before '?'
            start_index = url.find('/job/') + 5  # +5 to skip '/job/' this function looks for the word '/job/' and adds 5 more spaces to get to the job_id
            end_index = url.find('?', start_index) #defines the end of the job_id
            
            if end_index == -1:  # If there's no '?', take until the end
                return url[start_index:]
            return url[start_index:end_index]
        
        except Exception as e:
            return "Job ID not found"

    async def fetch_page(self, url: str, max_retries: int = 3) -> BeautifulSoup:
        """
        Fetch a webpage and return a BeautifulSoup object using either Selenium or aiohttp
        """
        if self.use_selenium:
            return await self._fetch_with_selenium(url, max_retries)
        else:
            return await self._fetch_with_aiohttp(url, max_retries)
        

    async def _fetch_with_selenium(self, url: str, max_retries: int = 3) -> BeautifulSoup:
        """
        Fetch a webpage using Selenium
        """
        for attempt in range(max_retries):
            try:
                # Execute in an asyncio executor to avoid blocking
                loop = asyncio.get_event_loop()
                
                # Load the page
                await loop.run_in_executor(None, lambda: self.driver.get(url))
                
                # Add a random delay to simulate human behavior
                await asyncio.sleep(random.uniform(2, 4))
                
                # Wait for the page content to load 
                await loop.run_in_executor(
                    None, 
                    lambda: WebDriverWait(self.driver, self.timeout).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                )
                
                # Get page source
                html = await loop.run_in_executor(None, lambda: self.driver.page_source)
                
                # Parse with BeautifulSoup
                return BeautifulSoup(html, 'html.parser')
                
            except TimeoutException:
                print(f"Timeout on attempt {attempt + 1} for {url}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except WebDriverException as e:
                print(f"WebDriver error on attempt {attempt + 1} for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    
                    # Refresh the WebDriver if we encounter issues
                    if "ERR_INTERNET_DISCONNECTED" in str(e) or "invalid session id" in str(e):
                        self.driver.quit()
                        self._setup_selenium()
                        
            except Exception as e:
                print(f"Unexpected error on attempt {attempt + 1} for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        print(f"Failed to fetch {url} after {max_retries} attempts")
        return None    

    async def _fetch_with_aiohttp(self, url: str, max_retries: int = 3) -> BeautifulSoup:
        """
        Fetch a webpage using aiohttp (kept as a fallback)
        """
        for attempt in range(max_retries):
            try:
                # Update headers with random user agent
                self.session.headers.update({'User-Agent': random.choice(self.user_agents)})
                
                async with self.session.get(url, timeout=self.timeout) as response:
                    if response.status == 200:
                        html = await response.text()
                        return BeautifulSoup(html, 'html.parser')
                    elif response.status == 403:
                        print(f"Received 403 Forbidden. Waiting before retry.")
                        wait_time = 2 ** attempt  # Exponential backoff
                        await asyncio.sleep(wait_time)
                    else:
                        print(f"Error fetching {url}: HTTP {response.status}")
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                else:
                    print(f"Failed after {max_retries} attempts")
                    raise
        return None



    #Helps sanitize the text extracted from the website, avoiding Unicode errors.
    def sanitize_text(self, text):
            if not isinstance(text, str):
                return str(text)
        
    # Replace surrogate pairs and other problematic characters
            try:
        # First attempt: encode with surrogateescape and decode back
                return text.encode('utf-8', 'surrogateescape').decode('utf-8', 'replace')
            except UnicodeError:
        # Second attempt: more aggressive replacement
                return text.encode('utf-8', 'replace').decode('utf-8')
            
            
    #Added a function to extract the location in the page
    def extract_location(self, soup):
        """
        Extract job location from HTML using the job-detail-location container
        and the anchor tag inside it.
        
        Args:
            soup: BeautifulSoup object of the job page
            
        Returns:
            str: The location text or "Location not found" if not found
        """
        # First try to find the container with data-automation="job-detail-location"
        location_container = soup.select_one('[data-automation="job-detail-location"]')
        
        if location_container:
            # Look for the anchor tag inside the container
            location_link = location_container.select_one('a[class*="gepq850"]')
            if location_link:
                return self.sanitize_text(location_link.text.strip())
            
            # If no specific anchor found, try any anchor or the container text itself
            location_link = location_container.select_one('a')
            if location_link:
                return self.sanitize_text(location_link.text.strip())
                
            return self.sanitize_text(location_container.text.strip())
        
        # Direct selector for the location anchor if container not found
        location_link = soup.select_one('a[href*="/jobs/in-"][class*="gepq850"]')
        if location_link:
            return self.sanitize_text(location_link.text.strip())
                
        return "Location not found"


    #Extraction of the job details
    async def extract_job_details(self, job_url: str) -> Dict: #once we have the job_url (defined later), the function will extract the details and added to a dictionary
        """
        Extract details from a single job posting.
        
        Args:
            job_url: URL of the job posting
            
        Returns:
            Dictionary containing job details (title, company, requirements, etc.)
        """
        #the dictionary will be called job_details
        try:
            job_details = {
                'url': job_url, 
                'job_id': self.extract_job_id(job_url)
            } #this first sentence will add the job_url to fetch de job page and the job id that is embeded in the url
            
            # Fetch and parse the job page
            soup = await self.fetch_page(job_url) #this will parse the whole page and if its not a soup object, it will return None
            if not soup:
                return None
                
            # Extract job title
            try:
                title_element = soup.select_one('[data-automation="job-detail-title"], .j1ww7nx7')
                job_details['job_title'] = self.sanitize_text(title_element.text.strip() if title_element else "Title not found")
            except Exception as e:
                job_details['job_title'] = "Title not found"

            #Extract Location
            try:
                job_details['job_location'] = self.extract_location(soup)
                print(f"Location: {job_details['job_location']}")
            except Exception as e:
                print(f"Error extracting location: {str(e)}")
                job_details['job_location'] = "Location not found"
            
                
            # Extract company name
            try:
                company_element = soup.select_one('[data-automation="advertiser-name"], .y735df0')
                job_details['company'] = self.sanitize_text(company_element.text.strip() if company_element else "Company not found")
            except Exception as e:
                job_details['company'] = "Company not found"
              
                
            # Extract job requirements/description
            try:
                description_element = soup.select_one('[data-automation="jobAdDetails"], .YCeva_0')
                job_details['job_description'] = self.sanitize_text(description_element.text.strip() if description_element else "Description not found")
            except Exception as e:
                job_details['job_description'] = "Description not found"
                
            # Extract posting time
            try:
                # Look for spans containing "Posted" text
                posting_elements = soup.select('[data-automation="jobDetailsPage"] span')
                posting_time = "Posting time not found"
                
                for element in posting_elements: #for all the elements in the posting_comments vairable defined before, it will check if it has the posted word and any of the Time letters
                    text = element.text.strip()
                    if "Posted" in text and any(unit in text for unit in ["ago", "h", "d", "m"]): #if the posted element has it, it will return the extracted text
                        posting_time = text
                        break
                         
                job_details['posting_time'] = posting_time #Now it will be added to the dictionary
            except Exception as e:
                job_details['posting_time'] = "Posting time not found"


            try: 
                job_details['job_type'] = self.categorize_job_type(job_details['job_title'])
                print(f"Job_type: {job_details['job_type']}")
            except Exception as e:
                job_details['job_type'] = "unknown"

            return job_details #returns the dictionary after finishing the extraction 

        except Exception as e:
            print(f"Error extracting job details: {str(e)}")
            return None

    
    #Build a job_type categorization for the different job_types
    def categorize_job_type(self, job_title: str) -> str:
        """
        Categorize job types based on the job title 

        """
        job_title_lower = job_title.lower()

        #check for DA
        if "data analyst" in job_title_lower:
            return "Data Analyst"
        
        if "data engineer" in job_title_lower:
            return "Data Engineer"
        
        if "engineer" in job_title_lower:
            return "Data Engineer"
        
        if "business analyst" in job_title_lower:
            return "Business Analyst"   
        
        if "analytics analyst" in job_title_lower:
            return "Analytcis Engineer" 
        
        if "data scientist" in job_title_lower:
            return "Data Scientist" 
        
        if "report developer" in job_title_lower:
            return "Report Developer" 
        
        if "solutions architect" in job_title_lower:
            return "Solutions Architect" 
        
        return "unknown"


    #This function will get the next page URL
    async def get_next_page_url(self, soup: BeautifulSoup, current_page: int) -> str:
        """
        Get the URL for the next page of search results
        
        Args:
            soup: BeautifulSoup object of the current page
            current_page: Current page number
            
        Returns:
            URL of the next page, or None if there is no next page
        """
        try:
            next_page_num = current_page + 1
            
            # Look for the next page link
            next_page_element = soup.select_one(f'[data-automation="page-{next_page_num}"]')
            
            if next_page_element and next_page_element.has_attr('href'):
                href = next_page_element['href']
                return urljoin(self.base_url, href)
                
            return None
            
        except Exception as e:
            print(f"Error getting next page URL: {str(e)}")
            return None

    def _convert_to_days(self, posting_time: str) -> float:
        """
        Convert posting time string to number of days
        
        Args:
            posting_time: String representing when the job was posted (e.g., "Posted 2d ago")
            
        Returns:
            Float representing the number of days
        """
        print(f"\nConverting posting time: {posting_time}")
        
        try:
            if not posting_time or 'not found' in posting_time:
                print("Invalid posting time, returning infinity")
                return float('inf')
            
            # Remove "Posted" prefix and clean the string
            cleaned_posted_time = posting_time.lower().replace('posted', '').strip()
            print(f"Cleaned time string: {cleaned_posted_time}")

            # Match a number followed by m (minutes), h (hours), or d (days)
            match = re.match(r'(\d+)\s*([mhd])', cleaned_posted_time)
            if not match:
                print(f"Could not parse time format: {cleaned_posted_time}")
                return float('inf')
                        
            value, unit = match.groups()
            value = float(value)
                    
            # Convert to days based on unit
            if unit == 'm':
                days = value / (24 * 60)
                print(f"Converting {value} minutes to {days:.2f} days")
            elif unit == 'h':
                days = value / 24
                print(f"Converting {value} hours to {days:.2f} days")
            else:  # unit == 'd'
                days = value
                print(f"Already in days: {days}")
                        
            return days
                    
        except Exception as e:
            print(f"Error converting time: {str(e)}")
            return float('inf')
    
    def _is_within_time_limit(self, posting_time: str, time_limit: str) -> bool:
        """
        Check if a posting time is within the specified time limit
        
        Args:
            posting_time: String representing when the job was posted
            time_limit: String representing the maximum age of posts to include
            
        Returns:
            Boolean indicating if the job posting is within the time limit
        """
        if not time_limit:
            return True
            
        job_days = self._convert_to_days(posting_time)
        limit_days = self._convert_to_days(time_limit)
        
        print(f"Comparing job time ({job_days:.2f} days) with limit ({limit_days:.2f} days)")
        return job_days < limit_days


    async def scrape_jobs(self, search_url: str, num_jobs: int = None, max_pages: int = None, posted_time_limit: str = None) -> List[Dict]:
        """
        Scrape job listings from Seek based on search criteria
        
        Args:
            search_url: Initial search URL
            num_jobs: Maximum number of jobs to scrape (optional)
            max_pages: Maximum number of pages to scrape (optional)
            posted_time_limit: Only include jobs posted within this time frame (e.g., "1d ago")
            
        Returns:
            List of dictionaries containing job details
        """
        try:
            print(f"Starting scrape with search URL: {search_url}")
            
            all_jobs_data = []
            current_page = 1
            jobs_scraped = 0
            current_url = search_url

            while True:
                print(f"\nScraping page {current_page}")
                
                # Fetch the current page with retries
                soup = await self.fetch_page(current_url, max_retries=3)
                if not soup:
                    break
                
                # Find all job cards
                job_cards = soup.select('article[data-automation="normalJob"], [data-automation="jobCard"]')
                print(f"Found {len(job_cards)} job cards on page {current_page}")

                # Process each job card
                for card in job_cards:
                    if num_jobs and jobs_scraped >= num_jobs:
                        return all_jobs_data

                    try:
                                              
                        
                        # Get the job link
                        link_element = card.select_one('a')
                        if not link_element or not link_element.has_attr('href'):
                            continue

                        href = link_element['href']
                        job_url = urljoin(self.base_url, href)
                        print(f"\nProcessing job {jobs_scraped + 1}: {job_url}")

                        # Extract job details with retries
                        job_details = None
                        for detail_attempt in range(3):
                            try:
                                job_details = await self.extract_job_details(job_url)
                                if job_details:
                                    break
                            except Exception as e:
                                print(f"Job detail attempt {detail_attempt + 1} failed: {str(e)}")
                                await asyncio.sleep(2)

                        # Check if job meets criteria and add to results
                        if job_details:
                            if posted_time_limit and not self._is_within_time_limit(job_details['posting_time'], posted_time_limit):
                                print(f"Job outside time limit, stopping scrape")
                                return all_jobs_data

                            all_jobs_data.append(job_details)
                            jobs_scraped += 1
                            print(f"Successfully scraped job {jobs_scraped}")
                        
                    except Exception as e:
                        print(f"Error processing job card: {str(e)}")
                        continue

                # Check if we've reached the maximum number of pages
                if max_pages and current_page >= max_pages:
                    break

                # Add a random delay between pages
                await asyncio.sleep(random.uniform(2, 5))

                # Get the next page URL
                next_page_url = await self.get_next_page_url(soup, current_page)
                if not next_page_url:
                    print("No next page found, ending scrape")
                    break

                current_url = next_page_url
                current_page += 1
                await asyncio.sleep(1)  # Small delay between pages to avoid rate limiting

            return all_jobs_data

        except Exception as e:
            print(f"Error in scrape_jobs: {str(e)}")
            return []

    async def save_to_json(self, jobs_data: List[Dict], filename: str = 'seek_jobs_bs4.json'):
        """
        Save scraped job data to a JSON file
        
        Args:
            jobs_data: List of job data dictionaries
            filename: Name of the output JSON file
        """
        # Ensure all job details are fully resolved
        scraped_jobs = []
        for job in jobs_data:
            # Create a new dict with resolved values
            scraped_job = {}
            for key, value in job.items():
                if key in ['job_title', 'company','job_location', 'job_description', 'posting_time', 'job_type']:
                    # Ensure these values are strings
                    scraped_job[key] = self.sanitize_text(value)
                else:
                    scraped_job[key] = value
            scraped_jobs.append(scraped_job)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(scraped_jobs, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(scraped_jobs)} jobs to {filename}")


# Creates a directory to save the results if it doesnt exists
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# Define the API endpoints

@app.get("/")
async def root():
    """Root endpoint that returns basic API information"""
    return {
        "message": "Welcome to the Seek Job Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "/scrape": "POST - Scrape jobs based on search criteria and return results",
            "/health": "GET - Check API health status"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

#Scrape endpoint
@app.post("/scrape")
async def scrape_jobs_endpoint(request: JobSearchRequest):
    """
    Endpoint to scrape jobs based on search criteria
    
    Returns the scraped jobs data directly in the response
    """
    try:
        
        start_time = time.time()    

        # Run the scraper
        async with SeekScraper(use_selenium=True) as scraper:
            jobs_data = await scraper.scrape_jobs(
                str(request.search_url),
                num_jobs=request.num_jobs,
                max_pages=request.max_pages,
                posted_time_limit=request.posted_time_limit
            
            )

        elapsed_time = time.time() - start_time
        
        
        # Ensure all values are properly serializable
        serializable_jobs = []
        for job in jobs_data:
            serializable_job = {}
            for key, value in job.items():
                # Use sanitize_text for string values
                if isinstance(value, str):
                    serializable_job[key] = scraper.sanitize_text(value)
                elif isinstance(value, (type, object)) and not isinstance(value, (int, float, bool, str, list, dict, type(None))):
                    serializable_job[key] = str(value)
                else:
                    serializable_job[key] = value

            serializable_jobs.append(serializable_job)
        
        return {
            "status": "success",
            "job_count": len(serializable_jobs),
            "execution_time": round(elapsed_time, 2),
            "data": serializable_jobs
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Scraping failed: {str(e)}"
        )



if __name__ == "__main__":
    # Determine port - use environment variable if available
    port = int(os.environ.get("PORT", 8080))
    
    # Run the API server
    uvicorn.run("seek_scraper_BS_v7:app", host="0.0.0.0", port=port, reload=False)
