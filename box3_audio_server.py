"""Ingress server for 16 kHz mono signed-16-bit PCM from the ESP32-S3-BOX-3.

Run on the Mac connected to the same Wi-Fi/hotspot as the device:

    python box3_audio_server.py

The BOX-3 sends one 12-byte header (`DBA1`) followed by unframed PCM. This
service forwards the live PCM to Deepgram and prints final transcripts plus
their existing math-normalized representation. It does not change the
RealtimeSTT local-microphone path in main.py or transcribe.py.
"""

import argparse
import asyncio
import audioop
from contextlib import AsyncExitStack
import json
import os
import struct

import requests
import websockets
from dotenv import load_dotenv

from agent import AgentError, respond
from speech_normalizer import normalize
from teachback import build_teachback_prompt

HEADER = struct.Struct("!4sIBB2x")
MAGIC = b"DBA1"
EXPECTED_FORMAT = (16_000, 1, 16)
REPLY_HEADER = struct.Struct("!4sIBB2xI")
REPLY_MAGIC = b"DBR1"
TTS_URL = "https://api.openai.com/v1/audio/speech"
TTS_INPUT_SAMPLE_RATE = 24_000
TTS_OUTPUT_SAMPLE_RATE = 16_000
DEEPGRAM_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2&language=en-US&encoding=linear16"
    "&sample_rate=16000&channels=1&interim_results=true"
)


def synthesize_speech(text: str) -> bytes:
    """Return OpenAI TTS output as 16 kHz mono signed-16-bit PCM."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set for TTS.")

    response = requests.post(
        TTS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-4o-mini-tts",
            "voice": "coral",
            "input": text,
            "response_format": "pcm",
        },
        timeout=60,
    )
    response.raise_for_status()
    pcm_16khz, _ = audioop.ratecv(
        response.content,
        2,
        1,
        TTS_INPUT_SAMPLE_RATE,
        TTS_OUTPUT_SAMPLE_RATE,
        None,
    )
    return pcm_16khz


async def send_audio_reply(writer: asyncio.StreamWriter, pcm: bytes) -> None:
    """Send a framed 16 kHz mono signed-16-bit PCM reply to the BOX-3."""
    writer.write(REPLY_HEADER.pack(
        REPLY_MAGIC,
        TTS_OUTPUT_SAMPLE_RATE,
        1,
        16,
        len(pcm),
    ))
    writer.write(pcm)
    await writer.drain()


async def forward_to_deepgram(reader: asyncio.StreamReader,
                               writer: asyncio.StreamWriter, peer: object) -> None:
    """Validate one device stream and relay its PCM chunks to Deepgram."""
    history: list[dict] = []
    header = await reader.readexactly(HEADER.size)
    magic, sample_rate, channels, bits_per_sample = HEADER.unpack(header)
    if magic != MAGIC or (sample_rate, channels, bits_per_sample) != EXPECTED_FORMAT:
        raise ValueError(
            "unsupported audio format: "
            f"magic={magic!r}, rate={sample_rate}, channels={channels}, bits={bits_per_sample}"
        )

    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPGRAM_API_KEY is not set in the local environment.")

    print(f"BOX-3 connected from {peer}; forwarding 16 kHz mono PCM to Deepgram.")
    headers = {"Authorization": f"Token {api_key}"}
    async with websockets.connect(DEEPGRAM_URL, additional_headers=headers) as deepgram:
        async def sender() -> None:
            while chunk := await reader.read(4096):
                await deepgram.send(chunk)

        async def receiver() -> None:
            nonlocal history
            async for message in deepgram:
                event = json.loads(message)
                if event.get("type") != "Results":
                    continue
                alternative = event.get("channel", {}).get("alternatives", [{}])[0]
                transcript = alternative.get("transcript", "").strip()
                if transcript and event.get("is_final"):
                    print(f"Student: {transcript}")
                    normalized = normalize(transcript)
                    print(f"Normalized: {normalized}")
                    try:
                        reply, history = await asyncio.to_thread(
                            respond,
                            build_teachback_prompt(normalized),
                            history,
                            mode="teach_back",
                        )
                    except (AgentError, ValueError) as error:
                        print(f"Buddy error: {error}")
                    else:
                        print(f"Buddy: {reply}")
                        try:
                            pcm = await asyncio.to_thread(synthesize_speech, reply)
                            await send_audio_reply(writer, pcm)
                            print(f"Sent {len(pcm)} bytes of 16 kHz PCM to BOX-3")
                        except (RuntimeError, requests.RequestException, audioop.error) as error:
                            print(f"TTS error: {error}")

        await asyncio.gather(sender(), receiver())


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    try:
        await forward_to_deepgram(reader, writer, peer)
    except asyncio.IncompleteReadError:
        print(f"BOX-3 disconnected: {peer}")
    except (RuntimeError, ValueError, OSError, websockets.WebSocketException) as error:
        print(f"Audio stream error from {peer}: {error}")
    finally:
        writer.close()
        await writer.wait_closed()


async def main(hosts: list[str], port: int) -> None:
    """Listen independently on IPv4 and IPv6, retaining either if one fails."""
    servers: list[asyncio.AbstractServer] = []
    for host in hosts:
        try:
            servers.append(await asyncio.start_server(handle_client, host, port))
        except OSError as error:
            print(f"Cannot listen on {host}:{port}: {error}")

    if not servers:
        raise RuntimeError(f"Could not listen on any requested address for port {port}.")

    addresses = ", ".join(
        str(sock.getsockname()) for server in servers for sock in server.sockets or []
    )
    print(f"Listening for BOX-3 PCM on {addresses}")
    async with AsyncExitStack() as stack:
        for server in servers:
            await stack.enter_async_context(server)
        await asyncio.gather(*(server.serve_forever() for server in servers))


if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        action="append",
        help="Address to listen on; repeat to specify more than one. Defaults to IPv4 and IPv6 wildcards.",
    )
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    try:
        asyncio.run(main(args.host or ["0.0.0.0", "::"], args.port))
    except KeyboardInterrupt:
        print("\nAudio server stopped.")
