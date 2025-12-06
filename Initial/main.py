# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import requests
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

app = FastAPI()


load_dotenv()
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# Check if keys are loaded (Optional safety check)
if not TOGETHER_API_KEY or not GOOGLE_API_KEY:
    print("⚠️ WARNING: API Keys not found in .env file!")

# Allow the frontend to talk to this backend
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
    Uses 'User-Agent' headers to look like a real Chrome browser.
    """
    print(f"Downloading content from: {url}...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }
    
    try:
        # Timeout is set to 15 seconds to avoid hanging forever
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            return response.text
        elif response.status_code == 403:
            print("❌ Blocked (403 Forbidden). The website knows you are a script.")
            return None
        else:
            print(f"❌ Error: Status Code {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Connection Error: {str(e)}")
        return None

def get_google_pagespeed(url):
    """
    Fetches the Performance Score (0-100) from Google PageSpeed API.
    """
    print("Checking Page Speed...")
    
    # If user hasn't put a key, skip this
    if "YOUR_" in GOOGLE_API_KEY:
        return "N/A (Key Missing)"

    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&key={GOOGLE_API_KEY}&strategy=mobile"
    try:
        response = requests.get(api_url)
        data = response.json()
        
        if "error" in data:
            print(f"Google API Error: {data['error']['message']}")
            return "Error"

        # Extract the score (0.9 is 90)
        score = data['lighthouseResult']['categories']['performance']['score'] * 100
        return round(score)
    except Exception as e:
        print(f"PageSpeed Error: {e}")
        return "N/A"

def generate_ai_content_together(current_title, current_desc, keyword, page_text_snippet):
    """
    Uses Together AI (Llama-3-70b) to write SEO content.
    """
    print("Generating AI Content...")
    
    # If user hasn't put a key, return dummy data
    if "YOUR_" in TOGETHER_API_KEY:
        return {"suggested_title": "Enter API Key in main.py", "suggested_description": "Enter API Key in main.py"}

    prompt = f"""
    You are an SEO expert.
    Target Keyword: "{keyword}"
    
    Current Page Context:
    Title: {current_title}
    Description: {current_desc}
    Page Text Sample: {page_text_snippet}
    
    Task:
    1. Write a new Meta Title (max 60 chars) using the keyword.
    2. Write a Meta Description (max 155 chars) using the keyword.
    
    Format your answer exactly like this:
    Title: [Your Title Here]
    Description: [Your Description Here]
    """

    endpoint = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/Llama-3-70b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 200,
        "temperature": 0.7
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response_json = response.json()
        
        if "error" in response_json:
            return {"suggested_title": "AI Error", "suggested_description": response_json['error']['message']}

        ai_text = response_json['choices'][0]['message']['content']
        
        # Parse the result
        new_title = "Could not generate"
        new_desc = "Could not generate"
        
        lines = ai_text.split('\n')
        for line in lines:
            if "Title:" in line:
                new_title = line.split("Title:")[1].strip()
            if "Description:" in line:
                new_desc = line.split("Description:")[1].strip()
                
        return {"suggested_title": new_title, "suggested_description": new_desc}
        
    except Exception as e:
        print(f"Together AI Error: {e}")
        return {"suggested_title": "Error calling AI", "suggested_description": str(e)}

@app.post("/analyze")
async def analyze_seo(request: AnalysisRequest):
    try:
        # 1. Download Page
        html_content = get_page_content(request.url)
        
        if not html_content:
            raise HTTPException(status_code=400, detail="Could not access website. It might be blocking bots.")

        soup = BeautifulSoup(html_content, 'html.parser')

        # 2. Extract Data
        current_title = soup.title.string if soup.title else "No Title"
        meta_desc_tag = soup.find("meta", attrs={"name": "description"})
        current_desc = meta_desc_tag["content"] if meta_desc_tag else "No Description"
        
        # Get snippet of text for AI context (first 500 characters)
        text_snippet = soup.get_text(" ", strip=True)[:500]

        # 3. Technical Checks
        tech_issues = []
        if not soup.find('h1'): tech_issues.append("Missing H1 Tag.")
        if len(soup.find_all('h1')) > 1: tech_issues.append("Multiple H1 Tags found (Only 1 allowed).")
        
        missing_alt = 0
        for img in soup.find_all('img'):
            if not img.get('alt'):
                missing_alt += 1
        if missing_alt > 0: tech_issues.append(f"{missing_alt} images are missing Alt text.")
        
        # 4. Check Page Speed
        speed_score = get_google_pagespeed(request.url)

        # 5. Generate AI Suggestions
        ai_result = generate_ai_content_together(current_title, current_desc, request.focus_keyword, text_snippet)

        return {
            "current_status": {
                "title": current_title,
                "title_length": len(current_title),
                "description": current_desc,
                "keyword_found_times": soup.get_text().lower().count(request.focus_keyword.lower()),
                "mobile_speed_score": speed_score
            },
            "technical_audit": tech_issues,
            "ai_suggestions": ai_result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
