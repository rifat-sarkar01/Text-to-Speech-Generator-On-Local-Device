import os
import threading
import tempfile
import customtkinter as ctk
from tkinter import filedialog, messagebox

import tts_engine
from audio_player import AudioPlayer


class TTSApp(ctk.CTk):
    def __init__(self, version="1.0.0"):
        super().__init__()

        self.title(f"LocalTTS v{version}")
        self.geometry("700x750")
        self.resizable(True, True)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.lang = "en"
        self.player = None
        self.is_generating = False
        self.generation_thread = None
        self.generated_chunks = []

        self._build_ui()
        self._load_models_async()

    def _build_ui(self):
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(main_frame, text="Facebook MMS-TTS (Offline)", font=("Arial", 18, "bold")).pack(pady=(5, 10))

        lang_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        lang_frame.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(lang_frame, text="Language:").pack(side="left", padx=5)
        self.lang_btn = ctk.CTkSegmentedButton(
            lang_frame, values=["English", "Bangla"],
            command=self._on_lang_change
        )
        self.lang_btn.set("English")
        self.lang_btn.pack(side="left", padx=5)

        voice_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        voice_frame.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            voice_frame,
            text="Voice: Single fixed voice per language (MMS-TTS limitation)",
            text_color="gray",
            font=("Arial", 11)
        ).pack(side="left")

        self.device_label = ctk.CTkLabel(main_frame, text="Device: Loading...", font=("Arial", 11))
        self.device_label.pack(pady=2)

        ctk.CTkLabel(main_frame, text="Enter text:", anchor="w").pack(fill="x", padx=10, pady=(10, 2))
        self.text_box = ctk.CTkTextbox(main_frame, height=180, wrap="word")
        self.text_box.pack(fill="both", expand=True, padx=10, pady=5)

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.speak_btn = ctk.CTkButton(btn_frame, text="Speak", command=self._on_speak, width=100, state="disabled")
        self.speak_btn.pack(side="left", padx=5)

        self.stop_btn = ctk.CTkButton(btn_frame, text="Stop", command=self._on_stop, width=80,
                                       fg_color="red", hover_color="darkred", state="disabled")
        self.stop_btn.pack(side="left", padx=5)

        self.pause_btn = ctk.CTkButton(btn_frame, text="Pause", command=self._on_pause, width=80,
                                        fg_color="orange", hover_color="darkorange", state="disabled")
        self.pause_btn.pack(side="left", padx=5)

        self.save_btn = ctk.CTkButton(btn_frame, text="Save to File", command=self._on_save, width=110, state="disabled")
        self.save_btn.pack(side="left", padx=5)

        self.progress_label = ctk.CTkLabel(main_frame, text="", font=("Arial", 11))
        self.progress_label.pack(pady=5)

        self.status_label = ctk.CTkLabel(main_frame, text="Starting...", font=("Arial", 10), text_color="gray")
        self.status_label.pack(pady=(2, 5))

    def _on_lang_change(self, value):
        self.lang = "bn" if value == "Bangla" else "en"

    def _load_models_async(self):
        def _load():
            try:
                self.after(0, lambda: self.status_label.configure(text="Downloading/loading models (first run may take a while)..."))
                tts_engine.load_models(progress_callback=lambda lang: None)
                device_text = f"Running on: {'GPU' if tts_engine.DEVICE == 'cuda' else 'CPU'}"
                self.after(0, lambda: self.device_label.configure(text=device_text))
                self.after(0, lambda: self.status_label.configure(text="Models ready!"))
                self.after(0, lambda: self._enable_buttons(True))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(text=f"Model load failed: {e}"))
                messagebox.showerror("Error", f"Failed to load models: {e}")

        self.generation_thread = threading.Thread(target=_load, daemon=True)
        self.generation_thread.start()

    def _enable_buttons(self, enabled=True):
        state = "normal" if enabled else "disabled"
        self.speak_btn.configure(state=state)

    def _on_speak(self):
        text = self.text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter some text.")
            return

        if self.is_generating:
            self._on_stop()

        self.player = AudioPlayer(
            progress_callback=self._update_play_progress,
            finished_callback=self._on_generation_finished
        )
        self.is_generating = True
        self._set_controls_active(True)

        self.generation_thread = threading.Thread(
            target=self._generation_worker, args=(text, True), daemon=True
        )
        self.generation_thread.start()

    def _on_save(self):
        text = self.text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter some text.")
            return

        if self.is_generating:
            self._on_stop()

        filetypes = [("MP3 files", "*.mp3"), ("WAV files", "*.wav")]
        ext = filedialog.asksaveasfilename(
            defaultextension=".mp3",
            filetypes=filetypes,
            title="Save Audio As"
        )
        if not ext:
            return

        self.save_path = ext
        self.is_generating = True
        self._set_controls_active(True, save_only=True)

        self.generation_thread = threading.Thread(
            target=self._generation_worker, args=(text, False), daemon=True
        )
        self.generation_thread.start()

    def _generation_worker(self, text, play_mode):
        try:
            chunks = tts_engine.chunk_text(text, self.lang)
            total = len(chunks)

            self.after(0, lambda: self.progress_label.configure(
                text=f"Generating chunk 1/{total}..."
            ))

            self.generated_chunks = []
            player = self.player if play_mode else None

            if player:
                player.start_playback(total)

            for i, chunk in enumerate(chunks):
                if play_mode and player and player.is_stopped:
                    break

                chunk_path = os.path.join(self.player._temp_dir if play_mode else tempfile.mkdtemp(),
                                          f"chunk_{i}.wav")

                tts_engine.generate_wav(chunk, self.lang, chunk_path)
                self.generated_chunks.append(chunk_path)

                idx = i + 1
                self.after(0, lambda c=idx, t=total: self.progress_label.configure(
                    text=f"Generated chunk {c}/{t}"
                ))

                if play_mode and player:
                    player.chunk_queue.put(chunk_path)

            if not play_mode and hasattr(self, 'save_path'):
                fmt = "mp3" if self.save_path.endswith(".mp3") else "wav"
                self.player = AudioPlayer()
                self.player.save_to_file(self.generated_chunks, self.save_path, fmt)
                self.after(0, lambda: self.progress_label.configure(text=f"Saved to: {self.save_path}"))
                self.after(0, lambda: messagebox.showinfo("Done", f"Audio saved to:\n{self.save_path}"))
                for f in self.generated_chunks:
                    if os.path.exists(f):
                        os.remove(f)

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Error", f"Generation failed: {e}"))
            self.after(0, lambda: self.progress_label.configure(text="Error occurred."))
        finally:
            self.after(0, lambda: self._on_generation_finished())

    def _update_play_progress(self, playing, total):
        self.after(0, lambda: self.progress_label.configure(
            text=f"Playing chunk {playing}/{total}"
        ))

    def _on_generation_finished(self):
        self.is_generating = False
        self._set_controls_active(False)
        if not self.progress_label.cget("text").startswith("Error"):
            self.after(0, lambda: self.progress_label.configure(text="Done!"))

    def _on_stop(self):
        if self.player:
            self.player.stop()
        self.is_generating = False
        self._set_controls_active(False)
        self.progress_label.configure(text="Stopped.")

    def _on_pause(self):
        if self.player:
            self.player.toggle_pause()
            if self.player.is_paused:
                self.pause_btn.configure(text="Resume")
            else:
                self.pause_btn.configure(text="Pause")

    def _set_controls_active(self, generating, save_only=False):
        if generating:
            self.stop_btn.configure(state="normal")
            self.pause_btn.configure(state="normal")
            self.speak_btn.configure(state="disabled")
            self.save_btn.configure(state="disabled")
        else:
            self.stop_btn.configure(state="disabled")
            self.pause_btn.configure(state="disabled")
            self.speak_btn.configure(state="normal")
            self.save_btn.configure(state="normal")
            self.pause_btn.configure(text="Pause")

    def on_closing(self):
        if self.player:
            self.player.cleanup()
        self.destroy()
