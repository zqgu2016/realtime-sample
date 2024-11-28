import asyncio
import json
import os

import numpy as np
import soundfile as sf
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv
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
from websockets import ConnectionClosedOK
from websockets.asyncio.server import ServerConnection, serve


def resample_audio(audio_data, original_sample_rate, target_sample_rate):
    number_of_samples = round(
        len(audio_data) * float(target_sample_rate) / original_sample_rate
    )
    resampled_audio = resample(audio_data, number_of_samples)
    return resampled_audio.astype(np.int16)


async def send_audio(client: RTClient, websocket: ServerConnection):
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

    for i in range(0, len(audio_bytes), bytes_per_chunk):
        chunk = audio_bytes[i : i + bytes_per_chunk]
        await client.send_audio(chunk)


async def receive_message_item(item: RTMessageItem, out_dir: str):
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
            with open(
                os.path.join(out_dir, f"{item.id}_{contentPart.content_index}.wav"),
                "wb",
            ) as out:
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
                sf.write(out, audio_array, samplerate=24000)
            with open(
                os.path.join(
                    out_dir,
                    f"{item.id}_{contentPart.content_index}.audio_transcript.txt",
                ),
                "w",
                encoding="utf-8",
            ) as out:
                out.write(audio_transcript)
        elif contentPart.type == "text":
            text_data = ""
            async for chunk in contentPart.text_chunks():
                text_data += chunk
            print(prefix, f"Text: {text_data}")
            with open(
                os.path.join(
                    out_dir, f"{item.id}_{contentPart.content_index}.text.txt"
                ),
                "w",
                encoding="utf-8",
            ) as out:
                out.write(text_data)


async def receive_function_call_item(item: RTFunctionCallItem, out_dir: str):
    prefix = f"[function_call_item={item.id}]"
    await item
    print(prefix, f"Function call arguments: {item.arguments}")
    with open(
        os.path.join(out_dir, f"{item.id}.function_call.json"), "w", encoding="utf-8"
    ) as out:
        out.write(item.arguments)


async def receive_response(client: RTClient, response: RTResponse, out_dir: str):
    prefix = f"[response={response.id}]"
    async for item in response:
        print(prefix, f"Received item {item.id}")
        if item.type == "message":
            asyncio.create_task(receive_message_item(item, out_dir))
        elif item.type == "function_call":
            asyncio.create_task(receive_function_call_item(item, out_dir))

    print(prefix, f"Response completed ({response.status})")
    if response.status == "completed":
        await client.close()


async def receive_input_item(item: RTInputAudioItem):
    prefix = f"[input_item={item.id}]"
    await item
    print(prefix, f"Transcript: {item.transcript}")
    print(prefix, f"Audio Start [ms]: {item.audio_start_ms}")
    print(prefix, f"Audio End [ms]: {item.audio_end_ms}")


async def receive_events(client: RTClient, out_dir: str):
    async for event in client.events():
        if event.type == "input_audio":
            asyncio.create_task(receive_input_item(event))
        elif event.type == "response":
            asyncio.create_task(receive_response(client, event, out_dir))


async def receive_messages(client: RTClient, out_dir: str):
    await asyncio.gather(
        receive_events(client, out_dir),
    )


async def run(websocket: ServerConnection, client: RTClient):
    print("Configuring Session...", end="", flush=True)
    # await client.configure(
    #     turn_detection=ServerVAD(
    #         threshold=0.5, prefix_padding_ms=300, silence_duration_ms=200
    #     ),
    #     input_audio_transcription=InputAudioTranscription(model="whisper-1"),
    # )
    # print("Done")

    # await asyncio.gather(
    #     send_audio(client, websocket), receive_messages(client, websocket)
    # )

    while True:
        try:
            message = await websocket.recv()
            event = {
                "type": "play",
                "message": "row",
            }
            print(message)
            await websocket.send(json.dumps(event))
        except ConnectionClosedOK:
            break


def get_env_var(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        raise OSError(f"Environment variable '{var_name}' is not set or is empty.")
    return value


async def handle(websocket: ServerConnection):
    endpoint = get_env_var("AZURE_OPENAI_ENDPOINT")
    key = get_env_var("AZURE_OPENAI_API_KEY")
    deployment = get_env_var("AZURE_OPENAI_DEPLOYMENT")
    async with RTClient(
        url=endpoint,
        key_credential=AzureKeyCredential(key),
        azure_deployment=deployment,
    ) as client:
        await run(websocket, client)


async def main():
    async with serve(handle, "localhost", 8765) as server:
        await server.serve_forever()


if __name__ == "__main__":
    load_dotenv(override=True)
    asyncio.run(main())
