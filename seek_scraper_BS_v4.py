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


#Create the API APP
app = FastAPI(
    title = "Seek Job Scraper API",
    description = "A simple API to scrape job listings from Seek.com.au",
    version = "1.0.0"
)

#Define the data model for the job search
##class JobSearchRequest(BaseModel):
    search_url: HttpUrl
    max_pages: Optional[int] = None
    posted_time_limit: Optional[str] = None
    num_jobs: Optional[int] = None
    job_title_filter: Optional[str] = None

#Create class for all the functions regarding scraping
##class SeekScraper:
    
    def __init__(self):
        """
        Initialize the scraper with base URL and headers for requests
        """
        self.base_url = "https://www.seek.com.au" #Define the main URL that will be used
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        } # define the headers for the API requests to the URL
        self.timeout = 30  # Timeout in seconds for HTTP requests

    async def __aenter__(self): #This will open the session in the browser
        """
        Set up the HTTP session when entering the context manager
        """
        self.session = aiohttp.ClientSession(headers=self.headers) #opens an http session using all the headers defined above. Uses aiohttp.
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb): #this will close the session 
        """
        Close the HTTP session when exiting the context manager
        """
        await self.session.close() #this will close the session once the scraping is done

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


    #This will get the page we need to scrape first to find the job cards. The function needs to return a BS object
    async def fetch_page(self, url: str, max_retries: int = 3) -> BeautifulSoup: #uses the URL and how many retries the function has to retrieve those number as arguments
        """
        Fetch a webpage and return a BeautifulSoup object
        
        Args:
            url: The URL to fetch
            max_retries: Maximum number of retry attempts
            
        Returns:
            BeautifulSoup object of the parsed HTML
        """
        for attempt in range(max_retries): #uses the for loop to iterate in each attemp of the entries. the range max_entries has N amount of attempts.
            try:
                async with self.session.get(url, timeout=self.timeout) as response: #this function needs to return the URL as response. 
                    if response.status == 200: #if the request asked for the function is OK - it will assign that value to HTML
                        html = await response.text() #The extracted URL (response) will be assigned to the variable HTML.
                        return BeautifulSoup(html, 'html.parser') #INPUT HTML to BS
                    else:
                        print(f"Error fetching {url}: HTTP {response.status}")
            except Exception as e: #if there is an error, it will retry and add a new retry entry
                print(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)  # Wait before retrying
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


    #extraction of the job details
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
                
            # Extract company name
            try:
                company_element = soup.select_one('[data-automation="advertiser-name"], .y735df0')
                job_details['company'] = self.sanitize_text(company_element.text.strip() if company_element else "Company not found")
            except Exception as e:
                job_details['company'] = "Company not found"
              
                
            # Extract job requirements/description
            try:
                description_element = soup.select_one('[data-automation="jobAdDetails"], .YCeva_0')
                job_details['job_description'] = self.sanitize_text(description_element.text.strip() if description_element else "Requirements not found")
            except Exception as e:
                job_details['job_description'] = "Requirements not found"
                
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
                
            return job_details #returns the dictionary after finishing the extraction 

        except Exception as e:
            print(f"Error extracting job details: {str(e)}")
            return None

    


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
        return job_days <= limit_days

       
    def job_title_conditional_filter(self, job_title:str, job_title_filter: Optional[str]) -> bool:
        """
        Check if the job title contains the search term

        Args:
            job_title: The job title to check
            job_title_filter: The text to search for in the title
            
        Returns:
            Boolean indicating if the search term is found in the title


        """
        if not job_title_filter:
            return True

        # Convert both to lowercase for case-insensitive comparison
        job_title = job_title.lower()
        # Split search term into individual words
        search_words = job_title_filter.lower().split()
        
        # Check if all search words appear in the job title
        return all(word in job_title for word in search_words) 


    async def scrape_jobs(self, search_url: str, num_jobs: int = None, max_pages: int = None, posted_time_limit: str = None, job_title_filter: Optional[str] = None) -> List[Dict]:
        """
        Scrape job listings from Seek based on search criteria
        
        Args:
            search_url: Initial search URL
            num_jobs: Maximum number of jobs to scrape (optional)
            max_pages: Maximum number of pages to scrape (optional)
            posted_time_limit: Only include jobs posted within this time frame (e.g., "1d ago")
            title_filter: Only include jobs with this text in the title (e.g., "Data Analyst")
            
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
                        # Get the job title from the card first
                        title_element = card.select_one('[data-automation="jobTitle"]')
                        if not title_element:
                            continue
                            
                        job_title = title_element.text.strip()
                        
                        # Skip this job if it doesn't match the title filter
                        if not self.job_title_conditional_filter(job_title, job_title_filter):
                            print(f"Skipping job - title doesn't match filter: {job_title}")
                            continue                        
                        
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
                if key in ['job_title', 'company', 'job_description', 'posting_time']:
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
        async with SeekScraper() as scraper:
            jobs_data = await scraper.scrape_jobs(
                str(request.search_url),
                num_jobs=request.num_jobs,
                max_pages=request.max_pages,
                posted_time_limit=request.posted_time_limit,
                job_title_filter=request.job_title_filter
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
    uvicorn.run("seek_scraper_BS_v4:app", host="0.0.0.0", port=port, reload=False)
