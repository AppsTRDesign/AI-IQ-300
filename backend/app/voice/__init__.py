"""Voices for everything the app says out loud: spoken replies, text_to_speech, video voice-overs, the Video Studio.

Engines (one at a time, in the order of Settings > Voices; the next one only when the chosen one fails):
- piper      local, offline, fast on any CPU (ONNX); Turkish: dfki, fahrettin, fettah, 99eren99; 50+ languages
- kokoro     local, offline, very natural English (US/UK) + es / fr / hi / it / pt-br (Kokoro-82M, ONNX)
- chatterbox local, offline, the most natural and expressive (23+ languages incl. Turkish, emotion, a reference
             clip of the user's own voice); heavy (PyTorch), so it lives in its own environment (data/tts/chatterbox)
             and is installed from Settings when wanted; slow on a CPU
- edge       Microsoft's online neural voices (free, no key, 400+ voices): the fallback when nothing local fits

catalog.py  which voices exist, gender / country / quality, install / remove, gender from pitch
engines.py  text -> raw samples per engine
studio.py   the "studio" finish with ffmpeg: pitch, EQ, de-esser, compressor, loudness standard, room
render.py   sentences, pauses, timings (subtitles), dialogs with several speakers, the fallback order
"""
