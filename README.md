# Arpeggio: Polyphonic Piano Simulator

A fork of the Python Piano project with enhanced audio engine capabilities for handling complex MIDI data without digital clipping or distortion.

---

## Overview

Arpeggio extends the original Python Piano project (created by LeMaster Tech) with significant improvements to audio processing, enabling high-fidelity playback of complex polyphonic MIDI compositions.

---

## Key Features

### Advanced Audio Engine

**Clip-Free Playback**
Resolves audio distortion and crackling during high-density playback through:

* **Dynamic Limiter:** Real-time audio limiting that intelligently reduces volume when simultaneous note counts exceed threshold values, ensuring seamless playback without clipping
* **Buffer Optimization:** Enhanced audio buffer sizing and optimized channel tracking to eliminate buffer underruns, maintaining smooth, low-latency sound reproduction during complex passages

### MIDI Support

* Load and parse standard MIDI files (.mid) via the `mido` library
* Accurate note visualization and playback with full MIDI velocity (volume) preservation
* Interactive controls supporting keyboard, mouse, and directional arrow keys for octave shifting

---

## Requirements & Installation

### Dependencies

* Python 3.13.3
* pygame
* mido

### Setup Using uv

For optimal dependency management, we recommend using `uv`:

1. **Clone the repository:**
   ```bash
   git clone [repository_url]
   cd [repository_name]
   ```

2. **Install dependencies & Run:**
   ```bash
   uv run main.py
   ```
---

## Credits

Based on the Python Piano project by **LeMaster Tech**. Visit the original channel for comprehensive tutorials and additional Python projects.

---

## License

MIT License
