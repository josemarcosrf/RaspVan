import asyncio
import json
import logging
import os
import time
import wave
from typing import Dict, Optional

import sounddevice as sd
import websockets

from asr import calc_block_size
from asr.vad import VAD
from common.utils.io import init_logger
from respeaker.pixels import Pixels

logger = logging.getLogger(__name__)
init_logger(level=os.getenv("LOG_LEVEL", logging.INFO), logger=logger)


class ASRClient:
    # TODO: Make as parameters
    MAX_SECONDS_NO_VOICE = 3
    MAX_SECONDS_VOICE = 5
    ASR_BLOCK_SIZE = 4000
    VAD_BLOCK_MS = 30
    VOICE_TH = 0.9

    def __init__(self, asr_uri: str, vad: VAD, pixels: Optional[Pixels] = None) -> None:
        self.asr_uri = asr_uri
        self.loop = asyncio.get_running_loop()
        self.audio_queue = asyncio.Queue()
        self.pixels = pixels or Pixels()
        self.vad = vad

    async def from_wave(self, wave_file: str) -> Dict[str, str]:
        async with websockets.connect(self.asr_uri) as websocket:
            wf = wave.open(wave_file, "rb")
            await websocket.send(
                '{ "config" : { "sample_rate" : %d } }' % (wf.getframerate())
            )
            buffer_size = int(wf.getframerate() * 0.2)  # 0.2 seconds of audio
            while True:
                data = wf.readframes(buffer_size)
                if len(data) == 0:
                    break

                await websocket.send(data)
                logger.debug(await websocket.recv())

            await websocket.send('{"eof" : 1}')

            return json.loads(await websocket.recv())

    async def stream_mic(self, sample_rate: float, device_id: int) -> Dict[str, str]:
        def _callback(indata, frames, time, status):
            """This is called (from a separate thread) for each audio block."""
            self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, bytes(indata))

        async def _do_asr(pcm_data):
            # ASR on the entire buffer
            await websocket.send(pcm_data)
            res = json.loads(await websocket.recv())

            return res.get("text", "")

        # Compute pcm buffer parameters
        asr_block_ms = self.ASR_BLOCK_SIZE / sample_rate * 1000  # e.g: 250ms
        vad_block_size = calc_block_size(self.VAD_BLOCK_MS, sample_rate)

        logger.debug(
            f"ASR Block ms: {asr_block_ms} | VAD block size: {vad_block_size} "
        )

        with sd.RawInputStream(
            samplerate=sample_rate,
            blocksize=self.ASR_BLOCK_SIZE,
            device=device_id,
            dtype="int16",
            channels=1,
            callback=_callback,
        ) as device:
            text = ""

            # Blocks of size 4000 @ 16kHz are 250 ms of audio
            # however for VAD we need 10, 20 or 30 ms blocks
            async with websockets.connect(self.asr_uri) as websocket:
                await websocket.send(
                    '{ "config" : { "sample_rate" : %d } }' % (device.samplerate)
                )
                self.pixels.speak()
                start = time.time()
                # t_last_voice = start
                total_seconds_no_voice = 0
                total_seconds_voice = 0
                i = 0
                while True:
                    i += 1
                    data = await self.audio_queue.get()

                    if self.vad.is_voice(data, device.samplerate, self.VAD_BLOCK_MS):
                        total_seconds_no_voice = 0
                        total_seconds_voice += asr_block_ms / 1000

                        if total_seconds_voice >= self.MAX_SECONDS_VOICE:
                            logger.info(
                                f"🛑 Stopped listening after {total_seconds_voice}s "
                                f"capturing voice (block {i})"
                            )
                            break
                    else:
                        # time from microphone perspective
                        total_seconds_no_voice += asr_block_ms / 1000

                        if total_seconds_no_voice >= self.MAX_SECONDS_NO_VOICE:
                            logger.info(
                                f"🛑 Stopped listening after {total_seconds_no_voice}s "
                                f"without detecting voice (block {i})"
                            )
                            break

                    # NOTE: While we run the ASR the microphone continues
                    # to collect audio frames and potentially we can
                    # break due to having 'silent' audio blocks before
                    # the ASR has completed!
                    # logger.debug(f"🎙️ [block {i}] Running ASR! ({len(data)})")
                    text += await _do_asr(data)

                # close up pixels and asr-server sock stream
                self.pixels.off()
                await websocket.send('{"eof" : 1}')

                # empty the queue
                for _ in range(self.audio_queue.qsize()):
                    self.audio_queue.get_nowait()

                logger.debug(f"⏳️ Total run time: {time.time() - start}")

                return text
