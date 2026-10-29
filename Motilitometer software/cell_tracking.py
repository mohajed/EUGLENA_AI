"""
Cell Detection and Tracking Module

This module provides the CellTracker class for detecting and tracking cells
in microscopy videos using adaptive thresholding and the Norfair tracking library.
"""

from typing import Optional, Tuple, List, Dict, Any, Set
import math
import random
import cv2
import numpy as np
from norfair import Detection, Tracker

import importlib.metadata
import sys

try:
    importlib.metadata.version("norfair")
except importlib.metadata.PackageNotFoundError:
    sys.modules["norfair"].__version__ = "0.0.0"


class CellTracker:
    """
    Cell detection and tracking system using adaptive thresholding and Norfair.
    
    Provides cell detection via adaptive thresholding, tracking with Norfair,
    and motility analysis based on speed or directional consistency.
    """
    
    # Constants
    MAX_IMAGE_SIZE = 10000  # Maximum width or height in pixels
    
    def __init__(self):
        # Calibration / timing
        self.calibration: float = 1.0
        self.flow_fps: float = 30.0

        # Preprocessing
        self.blur: int = 3
        self.thresh_block_size: int = 25
        self.thresh_bin_thresh: int = 15
        self.erosion: int = 1
        self.show_blob: bool = False
        self.show_selection: bool = False
        self.show_centers: bool = False
        self.show_boxes: bool = False
        self.agg_correction: bool = False
        self.lower_surf_thresh: int = 35
        self.upper_surf_thresh: int = 90

        # Tracking
        self.tracking_enabled: bool = False
        self.show_trails: bool = False
        self.show_id: bool = False
        self.traces_len: int = 50
        self.show_age: bool = False
        self.show_distance: bool = False
        self.show_speed: bool = False
        self.max_track_age: int = 30
        self.max_tracking_reset: int = 30

        # Motility
        self.calc_motility: bool = False
        self.motility_thresh: float = 30.0
        self.show_motile: bool = False
        self.motility_mode: str = "speed"
        self.angle_tol_deg: float = 10.0
        self.min_trace_len_for_angle: int = 5
        self.show_circle: bool = False

        # Norfair tracker
        self.tracker: Tracker = Tracker(
            distance_function="euclidean",
            distance_threshold=30
        )
        self.tracking: Dict[int, Dict[str, Any]] = {}

        # Misc
        self.selection_mask: Optional[np.ndarray] = None
        self.kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    def _validate_frame(self, frame: np.ndarray, param_name: str = "frame") -> None:
        """
        Validate input frame.
        
        Args:
            frame: Input frame to validate
            param_name: Parameter name for error messages
            
        Raises:
            ValueError: If frame is invalid
            TypeError: If frame is not a numpy array
        """
        if frame is None:
            raise ValueError(f"{param_name} cannot be None")
        
        if not isinstance(frame, np.ndarray):
            raise TypeError(
                f"{param_name} must be a numpy array, got {type(frame).__name__}"
            )
        
        if frame.size == 0:
            raise ValueError(f"{param_name} cannot be empty")
        
        # Check image size to prevent DoS
        h, w = frame.shape[:2]
        if h > self.MAX_IMAGE_SIZE or w > self.MAX_IMAGE_SIZE:
            raise ValueError(
                f"{param_name} too large: {w}x{h}. "
                f"Maximum: {self.MAX_IMAGE_SIZE}x{self.MAX_IMAGE_SIZE}"
            )
        
        # Check data type
        if frame.dtype != np.uint8:
            raise ValueError(
                f"{param_name} must be uint8, got {frame.dtype}"
            )

    def reset(self) -> None:
        """
        Reset tracker state for reuse.
        
        Clears all tracking data and reinitializes the Norfair tracker,
        allowing the instance to be reused for a new video sequence.
        """
        self.reset_tracker()
        self.selection_mask = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.reset()
        return False

    def reset_tracker(self) -> None:
        """Hard-reset Norfair tracker and local tracking data."""
        self.tracker = Tracker(
            distance_function="euclidean",
            distance_threshold=30
        )
        self.tracking.clear()

    def _get_random_color(self) -> Tuple[int, int, int]:
        """Generate a random BGR color for track visualization."""
        return tuple(int(random.randint(50, 255)) for _ in range(3))

    def _circular_diff_deg(self, a: float, b: float) -> float:
        """
        Smallest absolute difference between two angles in degrees.
        
        Args:
            a: First angle in degrees
            b: Second angle in degrees
            
        Returns:
            Absolute angular difference in range (0, 180]
        """
        return abs((a - b + 180.0) % 360.0 - 180.0)

    def _trace_angle_deg(self, points: Optional[List[Tuple[int, int]]]) -> Optional[float]:
        """
        Calculate angle from first to last point of trace.
        
        Args:
            points: List of (x, y) coordinates
            
        Returns:
            Angle in degrees (0-360), or None if insufficient points
        """
        if points is None or len(points) < 2:
            return None
        x0, y0 = points[0]
        x1, y1 = points[-1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360.0
        return ang

    def _dominant_angle(
        self, 
        angles: List[float], 
        tol_deg: float
    ) -> Tuple[Optional[float], Set[int]]:
        """
        Find dominant angle that maximizes inliers within tolerance.
        
        Args:
            angles: List of angles in degrees
            tol_deg: Tolerance in degrees for grouping
            
        Returns:
            Tuple of (dominant_angle, inlier_indices_set)
        """
        if not angles:
            return None, set()
        best_center = None
        best_inliers: Set[int] = set()
        for i, a in enumerate(angles):
            inliers = {j for j, b in enumerate(angles) 
            if self._circular_diff_deg(a, b) <= tol_deg}
            if len(inliers) > len(best_inliers):
                best_inliers = inliers
                best_center = a
        return best_center, best_inliers

    def detect_cells(
        self, 
        gray_frame: np.ndarray, 
        mask: np.ndarray
    ) -> Tuple[List[Tuple[Tuple[int, int], Tuple[float, float], np.ndarray]], np.ndarray]:
        """
        Detect cells in a grayscale frame using adaptive thresholding.
        
        Args:
            gray_frame: Grayscale input image (H, W) uint8
            mask: BGR visualization mask (H, W, 3) uint8
            
        Returns:
            Tuple of (cells_list, updated_mask)
                - cells_list: List of (center, dimensions, polygon) tuples
                - updated_mask: Mask with detection visualization
                
        Raises:
            ValueError: If frames are invalid
            TypeError: If frames are not numpy arrays
        """
        # Validate inputs
        self._validate_frame(gray_frame, "gray_frame")
        self._validate_frame(mask, "mask")
        
        # Check grayscale
        if len(gray_frame.shape) != 2:
            raise ValueError("gray_frame must be 2D (grayscale)")
        
        # Check mask is BGR
        if len(mask.shape) != 3 or mask.shape[2] != 3:
            raise ValueError("mask must be 3D BGR (H, W, 3)")
        
        # Check compatible shapes
        if gray_frame.shape[:2] != mask.shape[:2]:
            raise ValueError(
                f"Frame dimensions mismatch: gray {gray_frame.shape[:2]} vs mask {mask.shape[:2]}"
            )
        
        # Selection preview
        if self.show_selection:
            gray_bgr = cv2.cvtColor(gray_frame, cv2.COLOR_GRAY2BGR)

        if self.selection_mask is None or self.selection_mask.shape[:2] != mask.shape[:2]:
            self.selection_mask = np.zeros(mask.shape[:2], dtype="uint8")
        else:
            self.selection_mask.fill(0)

        # Binary analysis frame
        anaframe = cv2.GaussianBlur(gray_frame, (self.blur, self.blur), 0)
        anaframe = cv2.adaptiveThreshold(
            anaframe, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            self.thresh_block_size, self.thresh_bin_thresh
        )
        anaframe = cv2.morphologyEx(anaframe, cv2.MORPH_CLOSE, self.kernel, iterations=self.erosion)

        if self.show_blob:
            mask[anaframe > 0] = (0, 0, 255)

        cnts = cv2.findContours(anaframe, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
        calib_boxes = [cv2.minAreaRect(c) for c in cnts]
        calib_areas = [(b[1][0]) * (b[1][1]) for b in calib_boxes]

        if not calib_areas:
            return [], mask

        left = np.percentile(calib_areas, self.lower_surf_thresh)
        right = np.percentile(calib_areas, self.upper_surf_thresh)
        filt_boxes = [box for box, area in zip(calib_boxes, calib_areas) if left <= area <= right]

        cells = []
        for box in filt_boxes:
            center = (int(box[0][0]), int(box[0][1]))
            dims = (box[1][0] * self.calibration, box[1][1] * self.calibration)
            poly = np.array(cv2.boxPoints(box), dtype=int)
            cells.append((center, dims, poly))

            if self.show_selection:
                cv2.fillPoly(self.selection_mask, [poly], 255)
            if self.show_centers:
                cv2.circle(mask, center, 2, (0, 0, 255), -1, cv2.LINE_AA)
            if self.show_boxes:
                cv2.drawContours(mask, [poly], -1, (0, 255, 0), 1, cv2.LINE_AA)

        if self.show_selection:
            mask[self.selection_mask == 255] = gray_bgr[self.selection_mask == 255]
        
        return cells, mask

    def _motility_by_speed(self) -> float:
        """
        Calculate motility percentage based on speed threshold.
        
        Returns:
            Percentage of motile cells (0-100)
        """
        active = [(tid, d) for tid, d in self.tracking.items() if d.get("active") and d.get("points")]
        if not active:
            return 0.0
        motile_cnt = 0
        for tid, d in active:
            is_motile = (d.get("speed", 0.0) >= self.motility_thresh)
            d["motile"] = bool(is_motile)
            if is_motile:
                motile_cnt += 1
        
        # Protection against division by zero
        return 100.0 * motile_cnt / len(active) if len(active) > 0 else 0.0

    def _motility_by_angle(self) -> float:
        """
        Calculate motility based on directional consistency.
        
        Cells moving in the dominant direction are considered non-motile (drift),
        others are considered motile.
        
        Returns:
            Percentage of motile cells (0-100)
        """
        # Take traces with enough points
        active = [(tid, d) for tid, d in self.tracking.items() if d.get("active") and len(d.get("points", [])) >= self.min_trace_len_for_angle]
        if not active:
            return 0.0

        # Compute global angle (first -> last)
        def trace_angle_deg(pts: List[Tuple[int, int]]) -> float:
            x0, y0 = pts[0]
            x1, y1 = pts[-1]
            return (math.degrees(math.atan2(y1 - y0, x1 - x0)) % 360.0)

        angles = [trace_angle_deg(d["points"]) for _, d in active]

        # Dominant angle by simple "max inliers in ±tol"
        def circ_diff(a: float, b: float) -> float:
            return abs((a - b + 180.0) % 360.0 - 180.0)

        best_inliers: Set[int] = set()
        for i, a in enumerate(angles):
            inliers = {j for j, b in enumerate(angles) if circ_diff(a, b) <= self.angle_tol_deg}
            if len(inliers) > len(best_inliers):
                best_inliers = inliers

        motile_cnt = 0
        for idx, (tid, d) in enumerate(active):
            is_non_motile = (idx in best_inliers)
            d["motile"] = (not is_non_motile)
            if d["motile"]:
                motile_cnt += 1

        # Protection against division by zero
        return 100.0 * motile_cnt / len(active) if len(active) > 0 else 0.0

    def _compute_motility(self) -> float:
        """
        Compute motility percentage using configured method.
        
        Returns:
            Percentage of motile cells (0-100)
        """
        if self.motility_mode == "angle":
            return self._motility_by_angle()
        else:
            return self._motility_by_speed()

    def _refresh_motile_flags_for_display(self) -> None:
        """
        Update per-track 'motile' flags for drawing, without computing global percentage.
        """
        if self.motility_mode == "angle":
            # Reuse angle method to set d["motile"] flags; ignore returned percentage
            _ = self._motility_by_angle()
        else:
            # Speed-based: simple threshold on current speed
            for _, d in self.tracking.items():
                if d.get("active") and d.get("age", 0) > 0:
                    d["motile"] = bool(d.get("speed", 0.0) >= self.motility_thresh)

    def detect_and_track_cells(
        self, 
        gray_frame: np.ndarray, 
        mask: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        Detect and track cells in a grayscale frame.
        
        Args:
            gray_frame: Grayscale input image (H, W) uint8
            mask: BGR visualization mask (H, W, 3) uint8
            
        Returns:
            Tuple of (updated_mask, motility_percentage, active_tracks)
                - updated_mask: Mask with tracking visualization
                - motility_percentage: Percentage of motile cells (0-100)
                - active_tracks: List of dicts with keys: id, pos, speed, motile, age
                
        Raises:
            ValueError: If frames are invalid
            TypeError: If frames are not numpy arrays
        """
        cells, mask = self.detect_cells(gray_frame, mask)

        if self.tracking_enabled:
            self._track_points([cell[0] for cell in cells])

        motility = 100.0
        if self.calc_motility:
            motility = self._compute_motility()
        elif self.show_motile:
            # We are asked to draw motile circles even if global motility is off
            self._refresh_motile_flags_for_display()

        if self.tracking_enabled:
            self._draw_tracks(mask, self.tracking)

        # Collect active tracks data
        active_tracks = []
        if self.tracking_enabled:
            for tid, tdata in self.tracking.items():
                if tdata.get("active"):
                    # Get last position from points
                    pos = tdata["points"][-1] if tdata["points"] else (0, 0)
                    active_tracks.append({
                        "id": tid,
                        "pos": pos,
                        "speed": tdata.get("speed", 0.0),
                        "motile": tdata.get("motile", False),
                        "age": tdata.get("age", 0)
                    })
        
        return mask, motility, active_tracks

    def _track_points(
        self, 
        point_list: List[Tuple[int, int]]
    ) -> Dict[int, Dict[str, Any]]:
        """
        Update tracker with new detections.
        
        Args:
            point_list: List of (x, y) detection coordinates
            
        Returns:
            Updated tracking dictionary
        """
        kill_age = self.max_track_age
        # Detection expects [[x,y]] float
        detections = [Detection(np.array([[x, y]], dtype=np.float32)) for (x, y) in point_list]
        tracked_objects = self.tracker.update(detections)
        active_ids = {obj.id for obj in tracked_objects}

        for obj in tracked_objects:
            est = obj.estimate[0]
            cx, cy = int(est[0]), int(est[1])

            if obj.id not in self.tracking:
                self.tracking[obj.id] = {
                    "color": self._get_random_color(),
                    "points": [],
                    "distance": 0.0,
                    "speed": 0.0,
                    "age": 0,
                    "fade": self.traces_len,
                    "active": True,
                    "motile": False
                }

            data = self.tracking[obj.id]
            pts = data["points"]
            pts.append((cx, cy))
            if self.traces_len > 0 and len(pts) > self.traces_len:
                # Keep last traces_len points without deque
                del pts[:-self.traces_len]

            data["age"] = obj.age
            data["distance"] += getattr(obj, "last_distance", 0.0)
            data["speed"] = (data["distance"] / data["age"]) * self.flow_fps / self.calibration if data["age"] > 0 else 0.0
            data["fade"] = self.traces_len
            data["active"] = True

            if kill_age is not None and data["age"] > kill_age:
                obj.hit_counter = -1
                data["active"] = False

            if self.max_tracking_reset is not None and data["age"] > self.max_tracking_reset:
                self.reset_tracker()
                # Return current state instead of None
                return self.tracking

        # Fade inactive
        for obj_id, data in self.tracking.items():
            if obj_id not in active_ids:
                data["active"] = False
                if data["fade"] > 0:
                    data["fade"] -= 1

        return self.tracking

    def _draw_tracks(
        self, 
        mask: np.ndarray, 
        tracking: Dict[int, Dict[str, Any]]
    ) -> np.ndarray:
        """
        Draw tracking trails and annotations on mask.
        
        Args:
            mask: BGR image to draw on
            tracking: Tracking dictionary
            
        Returns:
            Updated mask with tracks drawn
        """
        font = cv2.FONT_HERSHEY_SIMPLEX

        for obj_id, data in list(tracking.items()):
            points = data["points"]
            fade = data["fade"]
            if fade <= 0 or not points:
                continue

            trail = points[-fade:]
            cx, cy = trail[-1]

            # Choose color for trail/labels
            use_motile_coloring = self.show_motile and data.get("age", 0) > 0
            if use_motile_coloring:
                is_motile = data.get("motile", bool(data.get("speed", 0.0) >= self.motility_thresh))
                color = (0, 255, 0) if is_motile else (0, 0, 255)  # green/red
            else:
                color = data["color"]

            # Draw trail
            if self.show_trails and len(trail) >= 2:
                np_pts = np.asarray(trail, dtype=np.int32)
                cv2.polylines(mask, [np_pts], isClosed=False, color=color, thickness=2, lineType=cv2.LINE_AA)

            # Motility circle (always if show_motile)
            if self.show_motile and data.get("age", 0) > 0:
                # Same criterion used for color above
                is_motile = data.get("motile", bool(data.get("speed", 0.0) >= self.motility_thresh))
                circ_color = (0, 255, 0) if is_motile else (0, 0, 255)
                if self.show_circle:
                    cv2.circle(mask, (cx, cy), 10, circ_color, -1, cv2.LINE_AA)

            # Labels
            text_lines = []
            if self.show_id:
                text_lines.append(f"ID:{obj_id}")
            if self.show_age:
                text_lines.append(f"Age:{data['age']}")
            if self.show_distance:
                text_lines.append(f"Dist:{data['distance']:.1f}")
            if self.show_speed and data["age"] > 0:
                text_lines.append(f"Speed:{data['speed']:.2f}")

            for i, line in enumerate(text_lines):
                cv2.putText(mask, line, (cx + 4, cy + 12 + i * 12), font, 0.4, color, 1, cv2.LINE_AA)

        return mask
