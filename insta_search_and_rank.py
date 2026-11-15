import os
import re
import httpx
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

class ContextAwareInstagramResolver:
    SYSTEM_ROUTES = {
        "p", "reel", "reels", "stories", "explore", "tags", "direct",
        "tv", "accounts", "popular", "directory", "developer", "about",
        "privacy", "terms", "legal", "api", "meta", "shop", "graphql"
    }

    FAN_KEYWORDS = {
        "fan", "fc", "universe", "edits", "update", "daily", 
        "club", "page", "lover", "fp", "stan"
    }

    def __init__(self, biodata: dict):
        self.biodata = biodata
        
        # 1. Primary Name Attributes
        self.first_name = biodata.get("first_name", "").strip()
        self.last_name = biodata.get("last_name", "").strip()
        self.full_name = f"{self.first_name} {self.last_name}".strip()

        # 2. Contextual Location Attributes
        self.current_city = biodata.get("current_city", "").strip()
        self.hometown = biodata.get("hometown", "").strip()

        # 3. DOB & Age Derivatives for Handle Matching
        self.dob_raw = biodata.get("date_of_birth", "")
        self.birth_year_full = ""
        self.birth_year_short = ""
        self.birth_day = ""
        self._parse_dob()

        # 4. Educational & Professional Keywords
        self.edu_keywords = self._extract_education_keywords()
        self.employer = biodata.get("employer", "").strip()

        self.api_key = os.getenv("SERPER_API_KEY")

    def _parse_dob(self):
        """Extracts day and year variations from DOB string (e.g., '27/08/1998')."""
        if self.dob_raw and "/" in self.dob_raw:
            parts = self.dob_raw.split("/")
            if len(parts) == 3:
                self.birth_day = parts[0].zfill(2)
                self.birth_year_full = parts[2]
                self.birth_year_short = parts[2][-2:]

    def _extract_education_keywords(self) -> list[str]:
        """Extracts acronyms and core degree terms from education list."""
        keywords = []
        raw_edu = self.biodata.get("education", [])
        for entry in raw_edu:
            # Extract text inside parentheses, e.g., 'BBA' from '... (BBA)'
            acronyms = re.findall(r"\((.*?)\)", entry)
            keywords.extend(acronyms)
            
            # Clean common words and collect degree tokens
            clean_entry = re.sub(r"[^\w\s]", "", entry).lower()
            for token in clean_entry.split():
                if token not in {"bachelor", "master", "of", "in", "degree", "diploma"}:
                    keywords.append(token)
        return list(set(k.lower() for k in keywords if len(k) > 1))

    def extract_handle_from_url(self, url: str) -> str | None:
        """Extracts username from Instagram URLs while rejecting system routes."""
        parsed = urlparse(url)
        if "instagram.com" not in parsed.netloc.lower():
            return None

        segments = [seg for seg in parsed.path.split("/") if seg.strip()]
        if segments:
            first_seg = segments[0].lower()
            if first_seg not in self.SYSTEM_ROUTES:
                if re.match(r"^[a-zA-Z0-9_\.]+$", first_seg):
                    return first_seg
        return None

    def calculate_match_score(self, username: str, title: str, snippet: str) -> tuple[float, list[str]]:
        """
        Evaluates candidate against biodata attributes, returning a 
        confidence score and reason breakdown.
        """
        score = 0.0
        reasons = []
        
        combined_text = f"{title} {snippet}".lower()
        fn_clean = self.first_name.lower()
        ln_clean = self.last_name.lower()

        # -------------------------------------------------------------
        # 1. HANDLE STRUCTURE EVALUATION
        # -------------------------------------------------------------
        exact_patterns = {
            f"{fn_clean}{ln_clean}", 
            f"{fn_clean}_{ln_clean}", 
            f"{fn_clean}.{ln_clean}"
        }
        
        if username in exact_patterns:
            score += 1.5
            reasons.append("Exact name-to-handle match")
        elif fn_clean in username and ln_clean in username:
            score += 1.0
            reasons.append("Contains both first and last name")
        elif fn_clean in username:
            score += 0.5
            reasons.append("Contains first name")

        # Handle matches DOB year/day (e.g., @ajaykumar98 or @ajay_27)
        if self.birth_year_short and self.birth_year_short in username:
            score += 0.5
            reasons.append(f"Handle matches birth year ('{self.birth_year_short}')")
        if self.birth_day and self.birth_day in username:
            score += 0.3
            reasons.append(f"Handle matches birth day ('{self.birth_day}')")

        # -------------------------------------------------------------
        # 2. CONTEXTUAL BIO & SNIPPET VERIFICATION
        # -------------------------------------------------------------
        if self.current_city and self.current_city.lower() in combined_text:
            score += 0.8
            reasons.append(f"Bio matches current city ('{self.current_city}')")

        if self.hometown and self.hometown.lower() in combined_text:
            score += 0.5
            reasons.append(f"Bio matches hometown ('{self.hometown}')")

        for kw in self.edu_keywords:
            if kw in combined_text:
                score += 0.6
                reasons.append(f"Bio matches education keyword ('{kw.upper()}')")
                break

        if self.employer and self.employer.lower() in combined_text:
            score += 0.4
            reasons.append(f"Bio matches employer ('{self.employer}')")

        if ln_clean in combined_text:
            score += 0.3
            reasons.append("Snippet contains surname")

        # -------------------------------------------------------------
        # 3. PENALTIES FOR FAN / COMMUNITY PAGES
        # -------------------------------------------------------------
        if any(kw in username for kw in self.FAN_KEYWORDS) or any(kw in combined_text for kw in self.FAN_KEYWORDS):
            score -= 1.5
            reasons.append("Penalty: Contains fan/community keywords")

        return round(score, 2), reasons

    def search_serper(self, query: str) -> list[dict]:
        """Queries Serper API."""
        endpoint = "https://google.serper.dev/search"
        headers = {"X-API-KEY": self.api_key, "Content-Type": "application/json"}
        try:
            res = httpx.post(endpoint, headers=headers, json={"q": query}, timeout=10.0)
            if res.status_code == 200:
                return res.json().get("organic", [])
        except Exception as e:
            print(f"[-] Search Error: {e}")
        return []

    def resolve(self) -> list[dict]:
        if not self.api_key:
            print("[-] SERPER_API_KEY missing in .env")
            return []

        # Multi-tier search queries built using Name + Context
        queries = [
            f'site:instagram.com "{self.full_name}"',
            f'site:instagram.com "{self.full_name}" "{self.current_city}"',
            f'"{self.full_name}" "{self.current_city}" "instagram"',
            f'{self.full_name} "instagram"'
        ]

        seen_handles = set()
        candidates = []

        for q in queries:
            print(f"[*] Executing SERP Query: {q}")
            results = self.search_serper(q)

            for item in results:
                link = item.get("link", "")
                text = f"{item.get('title', '')} {item.get('snippet', '')} {link}"
                
                # Extract handles from direct profile URLs
                handle = self.extract_handle_from_url(link)
                
                # Fallback: Extract @handle patterns mentioned in third-party search snippets
                snippet_handles = re.findall(r"\(@([a-zA-Z0-9_\.]+)\)", text)
                
                all_found_handles = [handle] if handle else []
                all_found_handles.extend([h.lower() for h in snippet_handles if h.lower() not in self.SYSTEM_ROUTES])

                for h in all_found_handles:
                    if h and h not in seen_handles:
                        seen_handles.add(h)
                        
                        score, reasons = self.calculate_match_score(
                            username=h, 
                            title=item.get("title", ""), 
                            snippet=item.get("snippet", "")
                        )

                        candidates.append({
                            "username": f"@{h}",
                            "profile_url": f"https://www.instagram.com/{h}/",
                            "confidence_score": score,
                            "match_reasons": reasons,
                            "title": item.get("title"),
                            "snippet": item.get("snippet")
                        })

        # Rank candidates by confidence score in descending order
        candidates.sort(key=lambda x: x["confidence_score"], reverse=True)
        return candidates


# --- Execution Example ---
if __name__ == "__main__":
    biodata_input = {
        "first_name": "Saloni",
        "last_name": "Gaur",
        "date_of_birth": "12/12/1999",
        "education": [
            "Bachelor of Mass Media (BMM)"
        ],
        "employer": "Independent",
        "hometown": "Bulandshahr",
        "current_city": "Mumbai"
    }

    resolver = ContextAwareInstagramResolver(biodata_input)
    ranked_candidates = resolver.resolve()

    print(f"\n================ RANKED INSTAGRAM PROFILES ({len(ranked_candidates)}) ================")
    for idx, c in enumerate(ranked_candidates, 1):
        print(f"\n[{idx}] Candidate: {c['username']} (Score: {c['confidence_score']})")
        print(f"    URL:      {c['profile_url']}")
        print(f"    Reasons:  {', '.join(c['match_reasons'])}")
        print(f"    Title:    {c['title']}")
        print(f"    Snippet:  {c['snippet']}")