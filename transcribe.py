"""
transcribe.py — Sam's module

Live microphone -> Deepgram WebSocket -> printed transcript.
Uses raw WebSocket (no SDK) so it works regardless of SDK version.
"""

import asyncio
import json
import os
import sounddevice as sd
import websockets
from dotenv import load_dotenv

load_dotenv()

SAMPLE_RATE = 16000
CHANNELS = 1
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2&language=en-US&encoding=linear16"
    f"&sample_rate={SAMPLE_RATE}&channels={CHANNELS}&interim_results=true"
)


async def transcribe():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    headers = {"Authorization": f"Token {api_key}"}

    async with websockets.connect(DEEPGRAM_URL, additional_headers=headers) as ws:
        print("Connected to Deepgram.")
        print("Listening... speak into your microphone. Press Ctrl+C to stop.\n")

        loop = asyncio.get_event_loop()
        queue = asyncio.Queue()

        def audio_callback(indata, frames, time, status):
            if status:
                print("Audio status:", status)
            loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

        async def sender():
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=audio_callback,
                blocksize=4000,
            ):
                while True:
                    chunk = await queue.get()
                    await ws.send(chunk)

        async def receiver():
            async for message in ws:
                data = json.loads(message)
                if data.get("type") == "Results":
                    transcript = (
                        data.get("channel", {})
                        .get("alternatives", [{}])[0]
                        .get("transcript", "")
                    )
                    is_final = data.get("is_final", False)
                    if transcript:
                        if is_final:
                            print(f"\r> {transcript}          ")
                        else:
                            print(f"\r  {transcript}          ", end="", flush=True)

        await asyncio.gather(sender(), receiver())


if __name__ == "__main__":
    try:
        asyncio.run(transcribe())
    except KeyboardInterrupt:
        print("\nStopped.")
