"""
Video Recorder Module

This module provides the VideoRecorder class for recording video streams
to disk using VidGear's WriteGear for efficient encoding.
"""

from typing import Optional, Dict, Any
import os
from datetime import datetime
import numpy as np


class VideoRecorder:
    """
    Video recorder using VidGear's WriteGear for efficient encoding.
    
    This class provides a simple interface for recording video streams
    with configurable codec, quality, and output format.
    
    Example:
        # Basic usage
        recorder = VideoRecorder("output.mp4", fps=30.0)
        recorder.start(width=1280, height=720)
        
        for frame in frames:
            recorder.write_frame(frame)
        
        recorder.stop()
        
        # With context manager
        with VideoRecorder("output.mp4", fps=30.0) as recorder:
            recorder.start(width=1280, height=720)
            for frame in frames:
                recorder.write_frame(frame)
    """
    
    def __init__(
        self,
        output_path: str,
        fps: float = 30.0,
        codec: str = "libx264",
        quality: int = 5,
        output_params: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize video recorder.
        
        Args:
            output_path: Path to output video file
            fps: Frames per second for output video
            codec: Video codec to use (e.g., 'libx264', 'libx265', 'mpeg4')
            quality: Encoding quality 1-10 (1=best, 10=worst), default=5
            output_params: Additional FFmpeg parameters (optional)
        """
        self.output_path = output_path
        self.fps = fps
        self.codec = codec
        self.quality = quality
        self.custom_params = output_params or {}
        
        # State
        self._writer = None
        self._is_recording = False
        self._frame_count = 0
        self._width = 0
        self._height = 0
        
        # Check if VidGear is available
        self._vidgear_available = self._check_vidgear()
    
    def _check_vidgear(self) -> bool:
        """Check if VidGear is available."""
        try:
            from vidgear.gears import WriteGear
            return True
        except ImportError:
            import warnings
            warnings.warn(
                "VidGear not available. Install with: pip install vidgear[core]\n"
                "Falling back to OpenCV VideoWriter (limited codec support).",
                RuntimeWarning
            )
            return False
    
    def start(self, width: int, height: int) -> bool:
        """
        Start recording with specified resolution.
        
        Args:
            width: Frame width in pixels
            height: Frame height in pixels
            
        Returns:
            True if recording started successfully
        """
        if self._is_recording:
            return True
        
        self._width = width
        self._height = height
        self._frame_count = 0
        
        # Create output directory if needed
        output_dir = os.path.dirname(os.path.abspath(self.output_path))
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        try:
            if self._vidgear_available:
                self._start_writegear()
            else:
                self._start_opencv_writer()
            
            self._is_recording = True
            return True
            
        except Exception as e:
            import warnings
            warnings.warn(f"Failed to start recording: {e}", RuntimeWarning)
            return False
    
    def _start_writegear(self) -> None:
        """Start recording using VidGear WriteGear."""
        from vidgear.gears import WriteGear

        output_params = {
            "-vcodec": self.codec,
            "-crf": self.quality,
            "-preset": "medium",
            "-input_framerate": self.fps,
        }
        
        output_params.update(self.custom_params)
        
        self._writer = WriteGear(
            output=self.output_path,
            compression_mode=True,
            logging=False,
            **output_params
        )
    
    def _start_opencv_writer(self) -> None:
        """Fallback to OpenCV VideoWriter."""
        import cv2
        
        codec_map = {
            "libx264": "mp4v",
            "libx265": "mp4v",
            "mpeg4": "mp4v",
            "h264": "avc1",
        }
        
        fourcc_str = codec_map.get(self.codec.lower(), "mp4v")
        fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
        
        self._writer = cv2.VideoWriter(
            self.output_path,
            fourcc,
            self.fps,
            (self._width, self._height)
        )
        
        if not self._writer.isOpened():
            raise IOError(f"Failed to open VideoWriter for {self.output_path}")
    
    def write_frame(self, frame: np.ndarray) -> bool:
        """
        Write a single frame to the video.
        
        Args:
            frame: BGR frame as numpy array (H, W, 3)
            
        Returns:
            True if frame was written successfully
        """
        if not self._is_recording:
            return False
        
        if frame is None or frame.size == 0:
            return False
        
        # Validate frame dimensions
        h, w = frame.shape[:2]
        if w != self._width or h != self._height:
            import warnings
            warnings.warn(
                f"Frame size mismatch: expected {self._width}x{self._height}, "
                f"got {w}x{h}. Resizing frame.",
                RuntimeWarning
            )
            import cv2
            frame = cv2.resize(frame, (self._width, self._height))
        
        try:
            self._writer.write(frame)
            self._frame_count += 1
            return True
        except Exception as e:
            import warnings
            warnings.warn(f"Failed to write frame: {e}", RuntimeWarning)
            return False
    
    def stop(self) -> None:
        """Stop recording and release resources."""
        if not self._is_recording:
            return
        
        if self._writer is not None:
            if self._vidgear_available:
                self._writer.close()
            else:
                self._writer.release()
            
            self._writer = None
        
        self._is_recording = False
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.stop()
        return False
    
    @property
    def is_recording(self) -> bool:
        """Whether currently recording."""
        return self._is_recording
    
    @property
    def frame_count(self) -> int:
        """Number of frames written."""
        return self._frame_count
    
    @property
    def duration(self) -> float:
        """Recorded video duration in seconds."""
        return self._frame_count / self.fps if self.fps > 0 else 0.0
    
    def get_info(self) -> dict:
        """
        Get recorder information as a dictionary.
        
        Returns:
            Dictionary with recorder properties
        """
        return {
            "output_path": self.output_path,
            "fps": self.fps,
            "codec": self.codec,
            "quality": self.quality,
            "width": self._width,
            "height": self._height,
            "is_recording": self._is_recording,
            "frames_written": self._frame_count,
            "duration": self.duration
        }
    
    @staticmethod
    def generate_filename(
        prefix: str = "recording",
        extension: str = "mp4",
        include_timestamp: bool = True
    ) -> str:
        """
        Generate a timestamped filename for recordings.
        
        Args:
            prefix: Filename prefix
            extension: File extension (without dot)
            include_timestamp: Whether to include timestamp
            
        Returns:
            Formatted filename
            
        Example:
            >>> VideoRecorder.generate_filename("webcam", "mp4")
            'webcam_20260129_154530.mp4'
        """
        if include_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"{prefix}_{timestamp}.{extension}"
        else:
            return f"{prefix}.{extension}"
