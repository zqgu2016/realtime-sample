import asyncio
import base64
import json

import numpy as np
import soundfile as sf
from azure.core.credentials import AzureKeyCredential
from fastapi import WebSocket, WebSocketDisconnect
from rtclient import (
    InputAudioTranscription,
    RTAudioContent,
    RTClient,
    RTFunctionCallItem,
    RTInputAudioItem,
    RTMessageItem,
    RTResponse,
    ServerVAD,
)
from scipy.signal import resample


def resample_audio(audio_data, original_sample_rate, target_sample_rate):
    number_of_samples = round(
        len(audio_data) * float(target_sample_rate) / original_sample_rate
    )
    resampled_audio = resample(audio_data, number_of_samples)
    return resampled_audio.astype(np.int16)


async def send_audio(client: RTClient, websocket: WebSocket):
    audio_file_path = "test.wav"
    sample_rate = 24000
    duration_ms = 100
    samples_per_chunk = sample_rate * (duration_ms / 1000)
    bytes_per_sample = 2
    bytes_per_chunk = int(samples_per_chunk * bytes_per_sample)

    extra_params = (
        {
            "samplerate": sample_rate,
            "channels": 1,
            "subtype": "PCM_16",
        }
        if audio_file_path.endswith(".raw")
        else {}
    )

    audio_data, original_sample_rate = sf.read(
        audio_file_path, dtype="int16", **extra_params
    )

    if original_sample_rate != sample_rate:
        audio_data = resample_audio(audio_data, original_sample_rate, sample_rate)

    audio_bytes = audio_data.tobytes()
    return audio_bytes

    for i in range(0, len(audio_bytes), bytes_per_chunk):
        chunk = audio_bytes[i : i + bytes_per_chunk]
        await client.send_item.send_audio(chunk)


async def receive_message_item(item: RTMessageItem):
    prefix = f"[response={item.response_id}][item={item.id}]"
    async for contentPart in item:
        if contentPart.type == "audio":

            async def collect_audio(audioContentPart: RTAudioContent):
                audio_data = bytearray()
                async for chunk in audioContentPart.audio_chunks():
                    audio_data.extend(chunk)
                return audio_data

            async def collect_transcript(audioContentPart: RTAudioContent):
                audio_transcript: str = ""
                async for chunk in audioContentPart.transcript_chunks():
                    audio_transcript += chunk
                return audio_transcript

            audio_task = asyncio.create_task(collect_audio(contentPart))
            transcript_task = asyncio.create_task(collect_transcript(contentPart))
            audio_data, audio_transcript = await asyncio.gather(
                audio_task, transcript_task
            )
            print(prefix, f"Audio received with length: {len(audio_data)}")
            print(prefix, f"Audio Transcript: {audio_transcript}")
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
        elif contentPart.type == "text":
            text_data = ""
            async for chunk in contentPart.text_chunks():
                text_data += chunk
            print(prefix, f"Text: {text_data}")


async def receive_function_call_item(item: RTFunctionCallItem):
    prefix = f"[function_call_item={item.id}]"
    await item
    print(prefix, f"Function call arguments: {item.arguments}")
    print(f"{item.id}.function_call.json")


async def receive_response(client: RTClient, response: RTResponse):
    prefix = f"[response={response.id}]"
    async for item in response:
        print(prefix, f"Received item {item.id}")
        if item.type == "message":
            asyncio.create_task(receive_message_item(item))
        elif item.type == "function_call":
            asyncio.create_task(receive_function_call_item(item))

    print(prefix, f"Response completed ({response.status})")
    if response.status == "completed":
        await client.close()


async def receive_input_item(item: RTInputAudioItem):
    prefix = f"[input_item={item.id}]"
    await item
    print(prefix, f"Transcript: {item.transcript}")
    print(prefix, f"Audio Start [ms]: {item.audio_start_ms}")
    print(prefix, f"Audio End [ms]: {item.audio_end_ms}")


async def receive_events(client: RTClient):
    async for event in client.events():
        if event.type == "input_audio":
            asyncio.create_task(receive_input_item(event))
        elif event.type == "response":
            asyncio.create_task(receive_response(client, event))


async def receive_messages(client: RTClient, websocket: WebSocket):
    await asyncio.gather(
        receive_events(client),
    )


async def run(client: RTClient, websocket: WebSocket):
    print("Configuring Session...", end="", flush=True)
    await client.configure(
        turn_detection=ServerVAD(
            threshold=0.5, prefix_padding_ms=300, silence_duration_ms=200
        ),
        input_audio_transcription=InputAudioTranscription(model="whisper-1"),
    )
    print("Done")

    await asyncio.gather(
        send_audio(client, websocket), receive_messages(client, websocket)
    )

    while True:
        try:
            message = await websocket.receive_text()
            event = {
                "type": "play",
                "message": "football",
            }
            print(message)
            await websocket.send_text(json.dumps(event))
        except WebSocketDisconnect:
            break


async def handle(websocket: WebSocket):
    while True:
        try:
            message = await websocket.receive_text()

            if message == "1":
                sample_rate = 24000
                duration_ms = 100
                samples_per_chunk = sample_rate * (duration_ms / 1000)
                bytes_per_sample = 2
                bytes_per_chunk = int(samples_per_chunk * bytes_per_sample)

                audio_bytes = await send_audio(None, websocket)
                for i in range(0, len(audio_bytes), bytes_per_chunk):
                    chunk = audio_bytes[i : i + bytes_per_chunk]
                    base64_chunk = base64.b64encode(chunk).decode("utf-8")
                    await websocket.send_json(
                        {"type": "response.audio.delta", "delta": base64_chunk}
                    )
            else:
                await websocket.send_json(
                    {"type": "response.audio_transcript.delta", "delta": "hello"}
                )

            # await websocket.send_bytes(message)
            # await websocket.send_text(json.dumps(event))
        except WebSocketDisconnect:
            break
    # endpoint = get_env_var("AZURE_OPENAI_ENDPOINT")
    # key = get_env_var("AZURE_OPENAI_API_KEY")
    # deployment = get_env_var("AZURE_OPENAI_DEPLOYMENT")

    # async with RTClient(
    #     url=endpoint,
    #     key_credential=AzureKeyCredential(key),
    #     azure_deployment=deployment,
    # ) as client:
    #     await run(client, websocket)
