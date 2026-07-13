import os
import time
import queue
import threading
import tempfile
import ctypes
import ctypes.wintypes

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False

if not HAS_PYGAME:
    from ctypes import windll, POINTER, Structure, c_uint, byref

    class WAVEFORMATEX(Structure):
        _fields_ = [
            ("wFormatTag", c_uint),
            ("nChannels", c_uint),
            ("nSamplesPerSec", c_uint),
            ("nAvgBytesPerSec", c_uint),
            ("nBlockAlign", c_uint),
            ("wBitsPerSample", c_uint),
            ("cbSize", c_uint),
        ]

    winmm = windll.winmm
    MMSYSERR_NOERROR = 0
    CALLBACK_FUNCTION = 0x30000
    WAVE_FORMAT_PCM = 1
    WHDR_DONE = 0x00000001
    WHDR_PREPARED = 0x00000002
    MCI_PLAY = 0x0806
    MCI_STOP = 0x0808
    MCI_CLOSE = 0x0804
    MCI_STATUS = 0x0814
    MCI_STATUS_LENGTH = 0x00000001
    MCI_STATUS_POSITION = 0x00000002
    MCI_STATUS_MODE = 0x00000004
    MCI_MODE_PLAY = 0x00000405
    MCI_MODE_PAUSE = 0x00000407
    MCI_MODE_STOP = 0x00000408
    MCI_SET_TIME_FORMAT = 0x0803
    MCI_FORMAT_MILLISECONDS = 0
    MCI_OPEN = 0x0800
    MCI_OPEN_TYPE = 0x00002000
    MCI_NOTIFY = 0x00000001

    class MCI_OPEN_PARMS(ctypes.Structure):
        _fields_ = [
            ("dwCallback", ctypes.c_ulong),
            ("wDeviceID", ctypes.c_uint),
            ("lpstrDeviceType", ctypes.c_char_p),
            ("lpstrElementName", ctypes.c_char_p),
            ("lpstrAlias", ctypes.c_char_p),
        ]

    class MCI_GENERIC_PARMS(ctypes.Structure):
        _fields_ = [
            ("dwCallback", ctypes.c_ulong),
        ]


class AudioPlayer:
    def __init__(self, progress_callback=None, finished_callback=None):
        self.chunk_queue = queue.Queue(maxsize=3)
        self.is_paused = False
        self.is_stopped = False
        self.current_chunk_index = 0
        self.total_chunks = 0
        self.progress_callback = progress_callback
        self.finished_callback = finished_callback
        self._playback_thread = None
        self._temp_dir = tempfile.mkdtemp()
        self._current_file = None
        self._mci_device_id = None
        self._paused_position = 0
        self._total_length_ms = 0
        self._use_pygame = HAS_PYGAME

        if self._use_pygame:
            pygame.mixer.init()

    @property
    def device(self):
        return self._temp_dir

    def start_playback(self, total_chunks):
        self.total_chunks = total_chunks
        self.current_chunk_index = 0
        self.is_paused = False
        self.is_stopped = False
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()

    def _playback_loop(self):
        while True:
            if self.is_stopped:
                break

            while self.is_paused and not self.is_stopped:
                time.sleep(0.05)

            if self.is_stopped:
                break

            try:
                chunk_path = self.chunk_queue.get(timeout=1.0)
            except queue.Empty:
                if self.current_chunk_index >= self.total_chunks:
                    break
                continue

            self.current_chunk_index += 1

            if self.progress_callback:
                self.progress_callback(self.current_chunk_index, self.total_chunks)

            try:
                if self._use_pygame:
                    self._play_with_pygame(chunk_path)
                else:
                    self._play_with_mci(chunk_path)
            except Exception:
                pass

        if self.finished_callback:
            self.finished_callback()

    def _play_with_pygame(self, chunk_path):
        pygame.mixer.music.load(chunk_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy() and not self.is_stopped:
            time.sleep(0.05)
            while self.is_paused and not self.is_stopped:
                time.sleep(0.05)

    def _play_with_mci(self, chunk_path):
        if self._mci_device_id is not None:
            winmm.mciSendCommand(self._mci_device_id, MCI_CLOSE, 0, 0)

        open_parms = MCI_OPEN_PARMS()
        open_parms.lpstrDeviceType = b"waveaudio"
        open_parms.lpstrElementName = chunk_path.encode("utf-8")
        open_parms.dwCallback = 0

        result = winmm.mciSendCommand(0, MCI_OPEN, MCI_OPEN_TYPE | 0x00010000, ctypes.byref(open_parms))
        if result != MMSYSERR_NOERROR:
            return

        self._mci_device_id = open_parms.wDeviceID

        time_format_parms = MCI_GENERIC_PARMS()
        winmm.mciSendCommand(self._mci_device_id, MCI_SET_TIME_FORMAT, MCI_FORMAT_MILLISECONDS, ctypes.byref(time_format_parms))

        self._paused_position = 0
        self._play_current_chunk()

        while not self.is_stopped:
            if self.is_paused:
                time.sleep(0.05)
                continue

            status_parms = MCI_GENERIC_PARMS()
            result = winmm.mciSendCommand(self._mci_device_id, MCI_STATUS, MCI_STATUS_MODE, ctypes.byref(status_parms))
            if result != MMSYSERR_NOERROR:
                break

            mode = status_parms.dwCallback
            if mode != MCI_MODE_PLAY:
                break
            time.sleep(0.05)

    def _play_current_chunk(self):
        if self._mci_device_id is None:
            return

        from_to = ctypes.c_ulong(self._paused_position)
        winmm.mciSendCommand(self._mci_device_id, MCI_PLAY, 0, ctypes.byref(from_to))

    def pause(self):
        self.is_paused = True
        if self._use_pygame and HAS_PYGAME:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
        elif self._mci_device_id is not None:
            self._get_current_position()
            winmm.mciSendCommand(self._mci_device_id, MCI_STOP, 0, 0)

    def unpause(self):
        self.is_paused = False
        if self._use_pygame and HAS_PYGAME:
            pygame.mixer.music.unpause()
        elif self._mci_device_id is not None:
            self._play_current_chunk()

    def toggle_pause(self):
        if self.is_paused:
            self.unpause()
        else:
            self.pause()

    def _get_current_position(self):
        if self._mci_device_id is None:
            return
        status_parms = MCI_GENERIC_PARMS()
        result = winmm.mciSendCommand(self._mci_device_id, MCI_STATUS, MCI_STATUS_POSITION, ctypes.byref(status_parms))
        if result == MMSYSERR_NOERROR:
            self._paused_position = status_parms.dwCallback

    def stop(self):
        self.is_stopped = True
        self.is_paused = False
        if self._use_pygame and HAS_PYGAME:
            pygame.mixer.music.stop()
        elif self._mci_device_id is not None:
            winmm.mciSendCommand(self._mci_device_id, MCI_STOP, 0, 0)
            winmm.mciSendCommand(self._mci_device_id, MCI_CLOSE, 0, 0)
            self._mci_device_id = None
        self._clear_queue()

    def _clear_queue(self):
        while not self.chunk_queue.empty():
            try:
                path = self.chunk_queue.get_nowait()
                if os.path.exists(path):
                    os.remove(path)
            except queue.Empty:
                break

    def cleanup(self):
        self.stop()
        for f in os.listdir(self._temp_dir):
            path = os.path.join(self._temp_dir, f)
            if os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        try:
            os.rmdir(self._temp_dir)
        except OSError:
            pass

    def save_to_file(self, chunk_paths, output_path, fmt="mp3"):
        from pydub import AudioSegment

        combined = AudioSegment.empty()
        for path in chunk_paths:
            audio = AudioSegment.from_wav(path)
            combined += audio

        if fmt == "mp3":
            combined.export(output_path, format="mp3")
        else:
            combined.export(output_path, format="wav")
