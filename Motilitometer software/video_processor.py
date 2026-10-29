"""
Video Processor Module

This module provides the VideoProcessor class that handles video reading,
frame-by-frame processing with tracking or optical flow, and result export.
Separates video processing logic from CLI for better modularity.
"""

from typing import Optional, Callable, Dict, Any, List, Tuple, Generator, Union
import csv
import pickle
import cv2
import numpy as np

from cell_tracking import CellTracker
from dense_flow import Denseflow
from webcam_controller import WebcamController


class VideoProcessor:
    """
    Video processing engine for cell tracking and optical flow analysis.
    
    Handles video reading, frame processing, and result collection.
    Can be used standalone or with a CLI/GUI.
    
    Example:
        # Video file
        processor = VideoProcessor("video.mp4", mode="flow", source_type="file")
        processor.configure_flow(calibration=1.5, flow_erosion=10)
        
        # Webcam
        processor = VideoProcessor(0, mode="flow", source_type="webcam")
        
        for frame_idx, overlay, results in processor.process():
            cv2.imshow("Preview", overlay)
            if cv2.waitKey(1) == ord('q'):
                break
                
        processor.export_csv("results.csv")
    """
    
    def __init__(
        self, 
        source: Union[str, int], 
        mode: str = "flow",
        source_type: str = "file",
        camera_width: int = None,
        camera_height: int = None,
        media_index: int = None,
        exposure: int = None,
        gain: int = None
    ):
        """
        Initialize the video processor.
        
        Args:
            source: Video file path (str) or camera index (int)
            mode: Processing mode - "flow" or "tracking"
            source_type: "file" for video files, "webcam" for camera
            camera_backend: "opencv", "pygrabber", or "seecam" (for webcam only)
            camera_width: Desired camera width (None = auto)
            camera_height: Desired camera height (None = auto)
            camera_format_index: Specific format index (None = auto)
        """
        self.source = source
        self.mode = mode
        self.source_type = source_type
        self.camera_width = camera_width
        self.camera_height = camera_height
        self.media_index = media_index
        self.exposure = exposure
        self.gain = gain
        
        # Processing modules
        self.tracker = CellTracker()
        self.denseflow = Denseflow()
        
        # Video properties (set on open)
        self.fps: float = 30.0
        self.total_frames: int = 0
        self.width: int = 0
        self.height: int = 0
        
        # Results storage
        self.summaries: List[Tuple[float, float, float]] = []
        self.raw_data: List[Dict[str, Any]] = []
        
        # Processing state
        self._cap: Optional[Union[cv2.VideoCapture, WebcamSource]] = None
        self._is_open: bool = False
    
    def configure_common(
        self,
        calibration: float = 1.0,
        fps_ref: float = 30.0
    ) -> None:
        """Configure common parameters for both modes."""
        self.tracker.calibration = calibration
        self.tracker.flow_fps = fps_ref
        self.denseflow.calibration = calibration
        self.denseflow.flow_fps = fps_ref
    
    def configure_tracking(
        self,
        blur: int = 3,
        thresh_block_size: int = 25,
        thresh_bin_thresh: int = 15,
        erosion: int = 1,
        lower_surf_thresh: int = 35,
        upper_surf_thresh: int = 90,
        show_trails: bool = False,
        show_id: bool = False,
        show_age: bool = False,
        show_distance: bool = False,
        show_speed: bool = False,
        traces_len: int = 50,
        max_track_age: Optional[int] = None,
        max_tracking_reset: Optional[int] = None,
        calc_motility: bool = False,
        motility_mode: str = "speed",
        motility_thresh: float = 30.0,
        angle_tol: float = 10.0,
        min_trace_angle: int = 5,
        show_motile: bool = False,
        show_circle: bool = False,
        show_blob: bool = False,
        show_selection: bool = False,
        show_centers: bool = False,
        show_boxes: bool = False
    ) -> None:
        """Configure tracking-specific parameters."""
        tr = self.tracker
        tr.blur = blur
        tr.thresh_block_size = thresh_block_size
        tr.thresh_bin_thresh = thresh_bin_thresh
        tr.erosion = erosion
        tr.lower_surf_thresh = lower_surf_thresh
        tr.upper_surf_thresh = upper_surf_thresh
        tr.show_trails = show_trails
        tr.show_id = show_id
        tr.show_age = show_age
        tr.show_distance = show_distance
        tr.show_speed = show_speed
        tr.traces_len = traces_len
        tr.max_track_age = max_track_age
        tr.max_tracking_reset = max_tracking_reset
        tr.calc_motility = calc_motility
        tr.motility_mode = motility_mode
        tr.motility_thresh = motility_thresh
        tr.angle_tol_deg = angle_tol
        tr.min_trace_len_for_angle = min_trace_angle
        tr.show_motile = show_motile
        tr.show_circle = show_circle
        tr.show_blob = show_blob
        tr.show_selection = show_selection
        tr.show_centers = show_centers
        tr.show_boxes = show_boxes
        
        # Auto-enable tracking in tracking mode
        tr.tracking_enabled = (self.mode == "tracking")
    
    def configure_flow(
        self,
        supersat: bool = True,
        flow_erosion: int = 10,
        lower_mag_thresh: float = 1.5,
        lower_cap: float = 0.0,
        upper_cap: float = 500.0,
        show_arrows: bool = True,
        show_blobs: bool = True,
        only_cardinal: bool = False,
        drift_angle: float = 10.0,
        correct_flow: bool = False,
        show_correction: bool = False,
        hide_flow: bool = False,
        drift_zones: int = 4
    ) -> None:
        """Configure optical flow parameters."""
        df = self.denseflow
        df.supersat = supersat
        df.flow_erosion = flow_erosion
        df.flow_lower_mag_thresh = lower_mag_thresh
        df.flow_lower_cap = lower_cap
        df.flow_upper_cap = upper_cap
        df.flow_show_arrows = show_arrows
        df.flow_show_blobs = show_blobs
        df.flow_only_cardinal = only_cardinal
        df.drift_angle = drift_angle
        df.correct_flow = correct_flow
        df.show_correction = show_correction
        df.hideflow = hide_flow
        df.drift_zones = drift_zones

    def open(self) -> bool:
        """
        Open the video source (file or webcam) and read properties.
        
        Returns:
            True if source opened successfully
        """
        if self.source_type == "webcam":
            camera_index = int(self.source) if isinstance(self.source, (int, str)) else 0
            
            # Use unified WebcamController
            self._cap = WebcamController(camera_index)
            
            # Check formatting options
            fmt_idx = self.media_index
            
            if not self._cap.open(
                width=self.camera_width,
                height=self.camera_height,
                format_index=fmt_idx
            ):
                return False
            
            # Apply initial controls if requested
            if self.exposure is not None:
                self._cap.set_exposure(self.exposure)
            if self.gain is not None:
                self._cap.set_gain(self.gain)
            
            self.fps = self._cap.fps
            self.total_frames = 0  # Webcam has no fixed total
            self.width = self._cap.width
            self.height = self._cap.height
        else:
            self._cap = cv2.VideoCapture(str(self.source))
            if not self._cap.isOpened():
                return False
            
            self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self._is_open = True
        
        # Clear previous results
        self.summaries.clear()
        self.raw_data.clear()
        
        return True
    
    def close(self) -> None:
        """Release video resources."""
        if self._cap is not None:
            if hasattr(self._cap, "close"):
                self._cap.close()
            elif hasattr(self._cap, "release"):
                self._cap.release()
            self._cap = None
        self._is_open = False
    
    def __enter__(self):
        """Context manager entry."""
        self.open()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
    
    def process(
        self,
        display_mode: str = "overlay",
        callback: Optional[Callable[[int, float, Dict], None]] = None
    ) -> Generator[Tuple[int, np.ndarray, Dict[str, Any]], None, None]:
        """
        Process video frame by frame.
        
        Args:
            display_mode: "overlay", "mask", or "frame"
            callback: Optional function called per frame with (frame_idx, fps, results)
            
        Yields:
            Tuple of (frame_idx, visualization, results_dict)
            
        Results dict contains:
            - mags: List of magnitudes (flow mode)
            - angles: List of angles (flow mode)
            - motility: Motility percentage
            - motility_data: Raw motility tuple
        """
        if not self._is_open:
            if not self.open():
                raise IOError(f"Cannot open video: {self.video_path}")
        
        # Initialize timing
        import time
        last_time = time.time()
        
        # Initial delta_t estimate
        delta_t = 1.0 / self.fps if self.fps > 1e-6 else 0.033
        frame_idx = -1
        
        while True:
            # Measure time since last loop start (or last read)
            # Ideally we measure time between frame acquisitions
            
            ok, frame = self._cap.read()
            if not ok:
                break
            
            # Update real delta_t
            now = time.time()
            real_dt = now - last_time
            last_time = now
            
            # Use real_dt for processing if reasonable (avoid huge jumps on first frame or pauses)
            if frame_idx >= 0 and real_dt > 0:
                delta_t = real_dt
                
            frame_idx += 1
            
            # Process frame
            results = self._process_frame(frame, delta_t, display_mode)
            
            # Store results for flow mode
            if self.mode == "flow" and frame_idx > 0:
                mags = results.get("mags", [])
                angles = results.get("angles", [])
                motility = results.get("motility", 100.0)
                motility_data = results.get("motility_data", (0, 0))
                
                mean_mag = float(np.mean(mags)) if mags else 0.0
                if motility_data[1] > 0:
                    motility = (motility_data[1] / max(1, motility_data[0])) * 100.0
                
                if mean_mag != 0.0:
                    time_s = frame_idx / self.fps
                    self.summaries.append((time_s, mean_mag, motility))
                    self.raw_data.append({
                        "frame_idx": frame_idx,
                        "mags": mags,
                        "angles": angles,
                        "motility": motility
                    })
            
            # Store results for tracking mode
            elif self.mode == "tracking" and frame_idx > 0:
                motility = results.get("motility", 100.0)
                cell_count = results.get("cell_count", 0)
                mean_speed = results.get("mean_speed", 0.0)
                tracks = results.get("tracks", [])
                
                time_s = frame_idx / self.fps
                self.summaries.append((time_s, float(cell_count), motility, mean_speed))
                self.raw_data.append({
                    "frame_idx": frame_idx,
                    "cell_count": cell_count,
                    "motility": motility,
                    "mean_speed": mean_speed,
                    "tracks": tracks
                })
            
            # Callback for progress updates
            if callback:
                callback(frame_idx, results.get("fps", 0.0), results)
            
            yield frame_idx, results["overlay"], results
    
    def _process_frame(
        self,
        frame: np.ndarray,
        delta_t: Optional[float],
        display_mode: str
    ) -> Dict[str, Any]:
        """Process a single frame and return results."""
        import time
        t0 = time.time()
        
        original_bgr = frame.copy()
        
        results: Dict[str, Any] = {
            "mags": [],
            "angles": [],
            "motility": 100.0,
            "motility_data": (0, 0),
            "overlay": original_bgr,
            "fps": 0.0
        }
        
        # TRACKING MODE
        if self.mode == "tracking":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            track_mask = np.zeros_like(original_bgr)
            track_mask, motility, active_tracks = self.tracker.detect_and_track_cells(gray, track_mask)
            results["motility"] = motility
            results["cell_count"] = len(active_tracks)
            results["tracks"] = active_tracks
            
            # Calculate mean speed of all active cells
            all_speeds = [t["speed"] for t in active_tracks]
            results["mean_speed"] = float(np.mean(all_speeds)) if all_speeds else 0.0
            
            if display_mode == "mask":
                results["overlay"] = track_mask
            elif display_mode == "overlay":
                results["overlay"] = cv2.add(original_bgr, track_mask)
            else:
                results["overlay"] = frame
        
        # FLOW MODE
        elif self.mode == "flow":
            flow_overlay, flow_mask, mags, angles, motility_data = self.denseflow.calc_flow(
                frame, delta_t=delta_t
            )
            results["mags"] = mags
            results["angles"] = angles
            results["motility_data"] = motility_data
            
            if display_mode == "mask":
                results["overlay"] = flow_mask
            elif display_mode == "overlay":
                results["overlay"] = flow_overlay
            else:
                results["overlay"] = frame
        
        # Calculate FPS based on real Delta T (Stream FPS)
        # Avoid zero division
        if delta_t and delta_t > 0:
            results["fps"] = 1.0 / delta_t
        else:
            # Fallback to Processing Speed if delta_t unavailable
            proc_dt = time.time() - t0
            results["fps"] = (1.0 / proc_dt) if proc_dt > 0 else 0.0
        
        return results
    
    def export_csv(self, path: str) -> None:
        """
        Export summary results to CSV.
        
        Args:
            path: Output file path
        """
        self.summaries.sort(key=lambda r: r[0])
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            
            if self.mode == "tracking":
                writer.writerow(["time", "cell_count", "motility", "mean_speed"])
            else:
                writer.writerow(["time", "mean_mag", "mean_mot"])
                
            writer.writerows(self.summaries)
    
    def export_pickle(self, path: str) -> None:
        """
        Export raw data to pickle file.
        
        Args:
            path: Output file path
        """
        self.raw_data.sort(key=lambda d: d["frame_idx"])
        with open(path, "wb") as f:
            pickle.dump(self.raw_data, f, protocol=pickle.HIGHEST_PROTOCOL)
    
    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------
    
    @property
    def duration(self) -> float:
        """Video duration in seconds."""
        return self.total_frames / self.fps if self.fps > 0 else 0.0
    
    @property
    def is_open(self) -> bool:
        """Whether video is currently open."""
        return self._is_open
