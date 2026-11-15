import os
import re
import httpx
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import time
import random

load_dotenv()

class GoogleLinkedInFinder:
    def __init__(self, biodata: dict):
        self.biodata = biodata
        self.first_name = str(biodata.get("first_name" or "")).strip()
        self.last_name = str(biodata.get("last_name" or "")).strip()
        self.full_name = f"{self.first_name} {self.last_name}".strip()
        self.employer = str( biodata.get("employer" or "")).strip()
        self.current_city = str(biodata.get("current_city" or "")).strip()
        self.hometown = str(biodata.get("hometown" or "")).strip()
        self.roles = biodata.get("role", [])
        self.education = biodata.get("education", [])
        self.address = biodata.get("address")
        
        # Load Serper API key
        self.api_key = os.getenv("SERPER_API_KEY")

    def generate_dork_queries(self) -> list[str]:
        """Constructs site-restricted search queries."""
        queries = []
            
                
        if self.full_name:
            if self.employer:
                queries.append(f'site:linkedin.com/in "{self.full_name}" "{self.employer}"')
                queries.append(f'site:linkedin.com/in "{self.full_name}" {self.employer}')
                
            if self.roles:
                for role in self.roles:
                    queries.append(f'site:linkedin.com/in "{self.full_name}" {role} ')
                    
            if self.education:
                for point in self.education:
                    queries.append(f'site:linkedin.com/in "{self.full_name}" {point}')
                    
            if self.address:
                queries.append(f'site:linkedin.com/in "{self.full_name}" {self.address}')
                
                
            
        return list(dict.fromkeys(queries))

    def execute_search(self, max_profiles:int) -> list[dict]:
        """Queries Google via Serper API and extracts matching LinkedIn profiles."""
        if not self.api_key:
            print("[-] Error: SERPER_API_KEY not found in .env")
            return []

        queries = self.generate_dork_queries()
        discovered_profiles = []
        seen_urls = set()
        endpoint = "https://google.serper.dev/search"
        
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }

        for query in queries:
            print(f"[*] Running Serper Search Query: {query}")
            payload = {"q": query}
            
            try:
                response = httpx.post(endpoint, headers=headers, json=payload, timeout=10.0)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get("organic", [])
                    
                    for item in items:
                        link = item.get("link", "")
                        if "linkedin.com/in/" in link:
                            clean_url = link.split("?")[0].rstrip("/")
                            if clean_url not in seen_urls:
                                seen_urls.add(clean_url)
                                title = item.get("title", "")
                                snippet = item.get("snippet", "")
                                
                                discovered_profiles.append({
                                    "url": clean_url,
                                    "title": title,
                                    "snippet": snippet,
                                    "extracted_occupation": self._extract_job_title(title)
                                })
                else:
                    print(f"[-] API Error {response.status_code}: {response.text}")
                                
                if (len(discovered_profiles) > max_profiles):
                    break

                # Stop after the first query that returns valid matches
                # if discovered_profiles:
                #     break

            except Exception as e:
                print(f"[-] Exception executing API request: {e}")

        return discovered_profiles

    def _extract_job_title(self, title: str) -> str:
        """Parses job title from LinkedIn title format: Name - Job Title - Company | LinkedIn"""
        parts = [p.strip() for p in re.split(r"[-–|]", title) if p.strip()]
        if len(parts) >= 3:
            return parts[1]
        elif len(parts) == 2 and "LinkedIn" not in parts[1]:
            return parts[1]
        return "Check Snippet"
    
    def scrape(self):
        
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

        
        scrape = input("Do you want to scrape results? (y/n): ").lower()
        if scrape == 'y':
            url = input("Enter URL to scrape: ") 
            
            with requests.session() as session:
                session.headers.update(HEADERS)
                response = session.get(url)
                print(f"Cookies gathered: {session.cookies.get_dict()}\n")
                
                time.sleep(random.uniform(1.5, 3.0))
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                return soup
            else:
                return f"Failed to retrieve the webpage. Status code: {response.status_code}"
        else:
            print("Exiting...")
            os._exit(1)


# --- Execution ---
if __name__ == "__main__":
    sample_data = {
        "first_name": "Tanmay",
        "last_name": "gadge",
        "employer": "IKSC Knowledge Bridge",
        "role": [""],
        "education": ["Bachelor of Technology", "BTech.", "MIT-World Peace University"],
        "hometown": "Pune",
        "current_city": "Pune"
    }

    finder = GoogleLinkedInFinder(sample_data)
    profiles = finder.execute_search(10)

    print("\n================ DISCOVERED LINKEDIN PROFILES ================")
    if profiles:
        for p in profiles:
            print(f"[+] Found Match: {p['url']}")
            print(f"    Extracted Role: {p['extracted_occupation']}")
            print(f"    Raw Title: {p['title']}")
            print(f"    Snippet: {p['snippet']}\n")
        print(profiles)
        scraped_page = finder.scrape()
        print(scraped_page)
    else:
        print("No profiles found.")
        
       