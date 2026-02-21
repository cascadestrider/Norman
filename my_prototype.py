import os
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv
import random

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_ai_recommendation(title, text_snippet):
    print("🧠 Consulting the AI Brain...")
    # We send a snippet of the actual text now for better accuracy
    prompt = f"Target Page: {title}\nContent Snippet: {text_snippet[:500]}\n\nTask: Based on this content, recommend 1 specific product and 1 catchy ad headline. Format: 'Product: [Name] | Headline: [Text]'"
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def stealth_scout():
    # Loop so you can test multiple sites in one go
    while True:
        url = input("\n🌐 Enter a URL to scout (or type 'exit'): ")
        if url.lower() == 'exit': break
        
        # --- STEALTH ARMOR ---
        # We rotate "User Agents" so we look like different devices
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1'
        ]
        
        headers = {'User-Agent': random.choice(user_agents),
            'Referer': 'https://www.google.com/',  # Tell the site you came from Google
            'Accept-Language': 'en-US,en;q=0.9',}
        
        try:
            print(f"📡 Launching Stealth Scout to: {url}...")
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"❌ Site blocked the scout (Error {response.status_code})")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            title = soup.title.string if soup.title else "Untitled Page"
            
            # Extract clean text from the page
            page_text = ' '.join([p.text for p in soup.find_all('p')])
            
            if len(page_text) < 50:
                print("⚠️ Not enough content found to analyze.")
                continue

            print(f"✅ Connection Established: {title}")
            
            recommendation = get_ai_recommendation(title, page_text)
            print(f"\n--- AI AD STRATEGY ---\n{recommendation}\n----------------------")

        except Exception as e:
            print(f"❌ Connection Failed: {e}")

# Run the tool
if __name__ == "__main__":
    stealth_scout()