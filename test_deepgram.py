import os
import requests
from dotenv import load_dotenv

load_dotenv()

AUDIO_URL = "https://dpgr.am/spacewalk.wav"

def main():
    api_key = os.getenv("DEEPGRAM_API_KEY")

    response = requests.post(
        "https://api.deepgram.com/v1/listen?model=nova-2&language=en",
        headers={
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        },
        json={"url": AUDIO_URL},
    )

    response.raise_for_status()
    transcript = response.json()["results"]["channels"][0]["alternatives"][0]["transcript"]
    print("Transcript:", transcript)

if __name__ == "__main__":
    main()
