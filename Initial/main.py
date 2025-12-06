import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from bs4 import BeautifulSoup
import requests
from fastapi.middleware.cors import CORSMiddleware

# Load secrets
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
    Downloads website content with browser-like headers.
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
    if not GOOGLE_API_KEY or "YOUR_" in GOOGLE_API_KEY:
        return "N/A"
    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url={url}&key={GOOGLE_API_KEY}&strategy=mobile"
    try:
        response = requests.get(api_url)
        data = response.json()
        if "error" in data: return "Error"
        score = data['lighthouseResult']['categories']['performance']['score'] * 100
        return round(score)
    except:
        return "N/A"

def analyze_technical_issues(soup):
    """
     detailed audit finding exact locations of errors.
    """
    issues = []

    # 1. Check H1 Tags
    h1_tags = soup.find_all('h1')
    if not h1_tags:
        issues.append("Missing H1 Tag (Critical).")
    elif len(h1_tags) > 1:
        # List the actual text of the duplicate H1s
        h1_texts = [f"'{tag.get_text(strip=True)}'" for tag in h1_tags]
        issues.append(f"Multiple H1 Tags found: {', '.join(h1_texts)}")

    # 2. Check Images for Alt Text
    images = soup.find_all('img')
    missing_alt_images = []
    for img in images:
        if not img.get('alt'):
            # Get the image filename or src for identification
            src = img.get('src', 'unknown_image')
            filename = src.split('/')[-1].split('?')[0] # Get just the filename
            missing_alt_images.append(filename)
    
    if missing_alt_images:
        # Limit to showing first 3 to keep UI clean
        all_images_string = ', '.join(missing_alt_images)
        msg = f"{len(missing_alt_images)} images missing Alt text: {all_images_string}"
        issues.append(msg)

    return issues

def generate_ai_content_together(current_title, current_desc, keyword, page_text_snippet):
    print("Generating AI Content...")
    
    if not TOGETHER_API_KEY or "YOUR_" in TOGETHER_API_KEY:
        return {}

    # Improved Prompt with explicit "No Markdown" instruction
    prompt = f"""
    You are a Senior SEO Specialist for Gini London.
    Target Keyword: "{keyword}"
    
    INSTRUCTIONS:
    Generate optimized content. 
    Output MUST be plain text keys and values. Do not use Markdown (no ** or ##).
    
    REQUIREMENTS:
    1. Title: 50-60 chars, includes keyword.
    2. Description: 140-155 chars, includes keyword.
    3. H1: One powerful heading.
    4. Content: 40-word intro using keyword 2x.
    5. Headings: Suggest 2-3 specific sub-headings (H2/H3).
    6. Alt_Text: Descriptive text for a product image.
    7. Schema_Type: JSON-LD types (e.g. Product).

    CONTEXT:
    Title: {current_title}
    Desc: {current_desc}
    Snippet: {page_text_snippet}
    
    OUTPUT FORMAT (Exactly like this):
    Title: [Value]
    Description: [Value]
    H1: [Value]
    Content: [Value]
    Headings: [Value]
    Alt_Text: [Value]
    Schema_Type: [Value]
    """

    endpoint = "https://api.together.xyz/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {TOGETHER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/Llama-3-70b-chat-hf",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 800,
        "temperature": 0.7
    }

    # Default empty state
    result = {
        "suggested_title": "Not Generated",
        "suggested_description": "Not Generated",
        "suggested_h1": "Not Generated",
        "suggested_content": "Not Generated",
        "suggested_headings": "Not Generated",
        "suggested_alt": "Not Generated",
        "suggested_schema": "Not Generated"
    }

    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response_json = response.json()
        ai_text = response_json['choices'][0]['message']['content']
        
        # Improved Parsing Logic
        lines = ai_text.split('\n')
        for line in lines:
            line = line.strip()
            # Remove any markdown bolding if AI adds it
            clean_line = line.replace('**', '').replace('##', '')
            
            if clean_line.startswith("Title:"): result["suggested_title"] = clean_line.replace("Title:", "").strip()
            elif clean_line.startswith("Description:"): result["suggested_description"] = clean_line.replace("Description:", "").strip()
            elif clean_line.startswith("H1:"): result["suggested_h1"] = clean_line.replace("H1:", "").strip()
            elif clean_line.startswith("Content:"): result["suggested_content"] = clean_line.replace("Content:", "").strip()
            elif clean_line.startswith("Headings:"): result["suggested_headings"] = clean_line.replace("Headings:", "").strip()
            elif clean_line.startswith("Alt_Text:"): result["suggested_alt"] = clean_line.replace("Alt_Text:", "").strip()
            elif clean_line.startswith("Schema_Type:"): result["suggested_schema"] = clean_line.replace("Schema_Type:", "").strip()
            
        return result
        
    except Exception as e:
        print(f"AI Error: {e}")
        return result

@app.post("/analyze")
async def analyze_seo(request: AnalysisRequest):
    try:
        html_content = get_page_content(request.url)
        if not html_content: raise HTTPException(status_code=400, detail="Could not access website.")
        soup = BeautifulSoup(html_content, 'html.parser')

        # Basic Info
        current_title = soup.title.string if soup.title else "No Title"
        meta_desc = soup.find("meta", attrs={"name": "description"})
        current_desc = meta_desc["content"] if meta_desc else "No Description"
        text_snippet = soup.get_text(" ", strip=True)[:500]

        # Enhanced Technical Audit
        tech_issues = analyze_technical_issues(soup)

        # APIs
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
