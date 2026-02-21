import os
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv
import random

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_ai_recommendation(title, content_snippet):
    print("🎯 AI is analyzing the conversation for friction points...")
    
    # Define our specific product strengths
    product_focus = "Tactical/Sport sunglasses with Zero-Glare polarization, Ballistic protection, and Anti-fog tech."
    
    prompt = f"""
    The following content is from a webpage titled: {title}
    
    Content: {content_snippet[:1500]}
    
    TASK:
    1. Identify a specific problem (friction point) mentioned regarding vision, glare, eye protection, or gear failure.
    2. Create a 'High-Conversion' ad strategy for our product: {product_focus}.
    3. The ad headline must directly address the user's struggle.
    
    Format your response as:
    PROBLEM DETECTED: [Briefly describe]
    WHY OUR PRODUCT WINS: [Specific feature match]
    AD HEADLINE: [Catchy, solution-oriented text]
    """
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def intent_scout():
    while True:
        url = input("\n🌐 Enter a Forum/Article URL to analyze (or 'exit'): ")
        if url.lower() == 'exit': break
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': 'https://www.google.com/'
        }
        
        try:
            print(f"📡 Scouting for high-intent leads at: {url}...")
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Focus specifically on paragraph and forum post text
            page_text = ' '.join([p.text for p in soup.find_all(['p', 'div', 'span']) if len(p.text) > 30])
            title = soup.title.string if soup.title else "Discussion Page"

            # Keywords that signal a problem
            friction_keywords = ["glare", "blinded", "fog", "scratch", "distortion", "green", "ballistic", "eye"]
            
            # Simple check to see if it's worth sending to AI
            found_keywords = [word for word in friction_keywords if word in page_text.lower()]
            
            if found_keywords:
                print(f"✅ Potential Lead Found! (Keywords: {found_keywords})")
                recommendation = get_ai_recommendation(title, page_text)
                print(f"\n--- CONVERSION STRATEGY ---\n{recommendation}\n--------------------------")
            else:
                print("⚖️ No significant vision friction detected on this page.")

        except Exception as e:
            print(f"❌ Scout failed: {e}")

if __name__ == "__main__":
    intent_scout()