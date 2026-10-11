"""Qt-free audio synthesis: band-limited oscillators, 8-bar pieces, ADPCM clips, tracker modules.

Everything here turns note data into PCM samples; playing them is the caller's job (emtk's
``emtk.audio.AudioOutput`` for emtk apps, QtMultimedia for the legacy Qt games).
"""
