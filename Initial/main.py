import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import requests
from fastapi.middleware.cors import CORSMiddleware

# Load secrets from .env file
load_dotenv()

app = FastAPI()

# --- CONFIGURATION ---
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# ---------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    url: str
    focus_keyword: str

def get_page_content(url):
    """
    Downloads the website content.
    """
    print(f"Downloading content from: {url}...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.text
        return None
    except Exception as e:
        print(f"Connection Error: {str(e)}")
        return None

def get_google_pagespeed(url):
    """
    Fetches the Performance Score (0-100).
    """
    if not GOOGLE_API_KEY or "YOUR_" in GOOGLE_API_KEY:
        return "N/A (Key Missing)"

    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&key={GOOGLE_API_KEY}&strategy=mobile"
    try:
        response = requests.get(api_url)
        data = response.json()
        if "error" in data: return "Error"
        score = data['lighthouseResult']['categories']['performance']['score'] * 100
        return round(score)
    except:
        return "N/A"

def generate_ai_content_together(current_title, current_desc, keyword, page_text_snippet):
    """
    Generates Advanced SEO Suggestions (Title, Desc, H1, Content, Schema).
    """
    print("Generating AI Content...")
    
    if not TOGETHER_API_KEY or "YOUR_" in TOGETHER_API_KEY:
        return {
            "suggested_title": "Error: Missing API Key",
            "suggested_description": "",
            "suggested_h1": "",
            "suggested_content": "",
            "suggested_headings": "",
            "suggested_alt": "",
            "suggested_schema": ""
        }

    prompt = f"""
    You are a Senior SEO Specialist for 'Gini London' (a UK fashion brand).
    
    OBJECTIVE: 
    Optimize the landing page for the Target Keyword: "{keyword}"
    
    STRICT REQUIREMENTS:
    1. Meta Title: Must be 50-60 characters. Include Primary Keyword.
    2. Meta Description: Must be 140-155 characters. Include Primary Keyword.
    3. H1 Tag: Create exactly ONE H1 tag containing the Primary Keyword.
    4. Content: Write a short product intro (approx 40 words) that uses the Primary Keyword exactly 2 times.
    5. Headings: Suggest 2 relevant H2 tags.
    6. Alt Text: Write 1 descriptive Alt Text for a product image.
    7. Schema: Suggest which JSON-LD Schema types are best (e.g., Product, CollectionPage).

    INPUT CONTEXT:
    Current Title: {current_title}
    Current Description: {current_desc}
    Page Text Snippet: {page_text_snippet}
    
    OUTPUT FORMAT (Strictly plain text with these exact labels):
    Title: [Your Title]
    Description: [Your Description]
    H1: [Your H1 Tag]
    Content: [Your text]
    Headings: [Your H2 tags]
    Alt_Text: [Your Alt Text]
    Schema_Type: [Your Schema]
    """

    endpoint = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/Llama-3-70b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 600,
        "temperature": 0.7
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response_json = response.json()
        ai_text = response_json['choices'][0]['message']['content']
        
        # --- PARSING LOGIC ---
        result = {
            "suggested_title": "Not Generated",
            "suggested_description": "Not Generated",
            "suggested_h1": "Not Generated",
            "suggested_content": "Not Generated",
            "suggested_headings": "Not Generated",
            "suggested_alt": "Not Generated",
            "suggested_schema": "Not Generated"
        }
        
        lines = ai_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith("Title:"): result["suggested_title"] = line.replace("Title:", "").strip()
            elif line.startswith("Description:"): result["suggested_description"] = line.replace("Description:", "").strip()
            elif line.startswith("H1:"): result["suggested_h1"] = line.replace("H1:", "").strip()
            elif line.startswith("Content:"): result["suggested_content"] = line.replace("Content:", "").strip()
            elif line.startswith("Headings:"): result["suggested_headings"] = line.replace("Headings:", "").strip()
            elif line.startswith("Alt_Text:"): result["suggested_alt"] = line.replace("Alt_Text:", "").strip()
            elif line.startswith("Schema_Type:"): result["suggested_schema"] = line.replace("Schema_Type:", "").strip()
            
        return result
        
    except Exception as e:
        print(f"AI Error: {e}")
        return result

@app.post("/analyze")
async def analyze_seo(request: AnalysisRequest):
    try:
        # 1. Download
        html_content = get_page_content(request.url)
        if not html_content: raise HTTPException(status_code=400, detail="Could not access website.")
        soup = BeautifulSoup(html_content, 'html.parser')

        # 2. Extract Basic Info
        current_title = soup.title.string if soup.title else "No Title"
        meta_desc = soup.find("meta", attrs={"name": "description"})
        current_desc = meta_desc["content"] if meta_desc else "No Description"
        text_snippet = soup.get_text(" ", strip=True)[:500]

        # 3. Tech Audit
        tech_issues = []
        if not soup.find('h1'): tech_issues.append("Missing H1 Tag.")
        if len(soup.find_all('h1')) > 1: tech_issues.append("Multiple H1 Tags found.")
        missing_alt = sum(1 for img in soup.find_all('img') if not img.get('alt'))
        if missing_alt > 0: tech_issues.append(f"{missing_alt} images missing Alt text.")

        # 4. APIs
        speed_score = get_google_pagespeed(request.url)
        ai_result = generate_ai_content_together(current_title, current_desc, request.focus_keyword, text_snippet)

        return {
            "current_status": {
                "title": current_title,
                "description": current_desc,
                "keyword_found_times": soup.get_text().lower().count(request.focus_keyword.lower()),
                "mobile_speed_score": speed_score
            },
            "technical_audit": tech_issues,
            "ai_suggestions": ai_result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
