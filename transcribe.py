import os
import sounddevice as sd

from deepgram import DeepgramClient


SAMPLE_RATE = 16000
CHANNELS = 1

deepgram = DeepgramClient(
    api_key=os.environ["DEEPGRAM_API_KEY"]
)

print("Connecting to Deepgram...")

with deepgram.listen.v1.connect(
    model="nova-3",
    language="en-US",
    encoding="linear16",
    sample_rate=SAMPLE_RATE,
    channels=CHANNELS,
    interim_results=True,
) as connection:

    print("Listening... speak into your microphone.")
    print("Press Control+C to stop.")

    def audio_callback(indata, frames, time, status):
        if status:
            print(status)

        connection.send_media(indata.tobytes())

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        callback=audio_callback,
    ):
        try:
            for message in connection:
                if message.type == "Results":
                    transcript = message.channel.alternatives[0].transcript

                if message.is_final and transcript:
                    print(transcript)

        except KeyboardInterrupt:
            print("\nStopped.")