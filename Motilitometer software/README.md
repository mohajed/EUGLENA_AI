# Motilitometer

Command-line tool for cell motility analysis in microscopy videos.
Two processing modes: **cell tracking** (individual cell detection and tracking) and **optical flow** (dense flow with drift correction).

## Architecture

```
motilitometer.py        Main CLI (Rich), argument parsing, display loop
video_processor.py      Video processing engine (file or webcam)
cell_tracking.py        Adaptive thresholding detection + Norfair tracking
dense_flow.py           Farneback optical flow (OpenCL accelerated), zone-based drift correction
webcam_controller.py    Webcam control via DirectShow (pygrabber), SeeCAM Y12/Y16 support
video_recorder.py       Video recording (VidGear WriteGear or OpenCV fallback)
light_controller.py     Serial LED driver control (RGBW+IR, JSON protocol)
sequence_processor.py   Automation via .seq files (light, recording, waits)
```

## Dependencies

- Python 3.8+
- OpenCV (`opencv-python` or `opencv-contrib-python`)
- NumPy
- Norfair (tracking)
- Rich (CLI interface)
- pygrabber (DirectShow webcam, Windows only)
- VidGear (recording, optional)
- pyserial (light control, optional)

```
pip install opencv-contrib-python numpy norfair rich
```

## Usage

### Help

```bash
python motilitometer.py --help
```

### Optical Flow Analysis

Basic processing on a video file:

```bash
python motilitometer.py --video input.mp4 --processing flow
```

With drift correction and data export:

```bash
python motilitometer.py --video input.mp4 --processing flow --correct-flow --show-correction --export-csv --export-pkl
```

Flow parameter tuning:

```bash
python motilitometer.py --video input.mp4 --processing flow \
    --flow-erosion 10 --lower-mag-thresh 1.5 \
    --lower-cap 0 --upper-cap 500 \
    --drift-zones 4 --drift-angle 10
```

### Cell Tracking

Cell tracking with motility computation:

```bash
python motilitometer.py --video input.mp4 --processing tracking --motility --show-trails
```

Tracking with all visual annotations:

```bash
python motilitometer.py --video input.mp4 --processing tracking \
    --show-trails --show-id --show-speed --show-motile --show-circle \
    --motility --motility-mode speed --motility-thresh 30
```

Angle-based motility (dominant direction = drift):

```bash
python motilitometer.py --video input.mp4 --processing tracking \
    --motility --motility-mode angle --angle-tol 10
```

### Webcam

Real-time acquisition:

```bash
python motilitometer.py --source webcam --camera-index 0 --processing flow
```

With recording:

```bash
python motilitometer.py --source webcam --camera-index 1 --processing tracking \
    --record --record-codec libx264 --record-quality 5
```

Interactive controls in webcam mode (terminal):
- `e` / `g` : select exposure / gain
- Up/Down arrows or `w`/`s` : adjust value
- Type a number + Enter : set value directly
- Escape : deselect

### Light Control

```bash
python motilitometer.py --source webcam --processing flow \
    --light-port COM3 --light-baud 115200
```

Light controls (terminal): `r`, `G` (shift), `b`, `w`, `i` to select a channel.

### Sequence Automation

`.seq` file format (one command per line):

```
R500
5s
R5
5s
B500
5s
B0
```

Available commands: `R<val>`, `G<val>`, `B<val>`, `W<val>`, `IR<val>` (light), `<N>s` or `<N>min` (wait), `V<N>` (record for N seconds).

```bash
python motilitometer.py --source webcam --processing flow \
    --light-port COM3 --sequence sequence.seq
```

### Display Modes

- `--display overlay` : original frame + visualization (default)
- `--display mask` : visualization only
- `--display frame` : original frame only
- `--display none` : no window (headless processing)

### Export

```bash
# CSV (per-frame summary: time, mean magnitude, motility)
python motilitometer.py --video input.mp4 --processing flow --export-csv --csv-out results.csv

# Pickle (raw data: magnitudes, angles per frame)
python motilitometer.py --video input.mp4 --processing flow --export-pkl --pickle-out raw.pkl
```

### Calibration

The `--calibration` factor converts pixels to micrometers. Use `--fps-ref` to override the file's framerate if incorrect.

```bash
python motilitometer.py --video input.mp4 --processing flow --calibration 0.65 --fps-ref 25
```

## Programmatic Usage

The `VideoProcessor`, `CellTracker`, and `Denseflow` classes can be used independently from the CLI.

```python
from video_processor import VideoProcessor

processor = VideoProcessor("video.mp4", mode="flow", source_type="file")
processor.configure_common(calibration=0.65, fps_ref=30)
processor.configure_flow(correct_flow=True, drift_zones=4)

processor.open()
for frame_idx, overlay, results in processor.process():
    mags = results["mags"]       # calibrated speeds (um/s)
    angles = results["angles"]   # directions (degrees)
    motility = results["motility"]
processor.close()

processor.export_csv("output.csv")
```

```python
from dense_flow import Denseflow

flow = Denseflow()
flow.calibration = 0.65
flow.correct_flow = True

overlay, mask, mags, angles, motility = flow.calc_flow(frame_bgr)
```

```python
from cell_tracking import CellTracker

tracker = CellTracker()
tracker.tracking_enabled = True
tracker.calc_motility = True

mask, motility_pct, active_tracks = tracker.detect_and_track_cells(gray, mask)
```
