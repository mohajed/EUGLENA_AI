"""
Dense Optical Flow Module

This module provides the Denseflow class for computing and analyzing dense optical flow
using OpenCL-accelerated Farneback method, with drift correction capabilities.
"""

from typing import Optional, Tuple, List
import warnings
import cv2
import numpy as np


class Denseflow:
    """
    Dense optical flow analyzer with drift correction capabilities.
    
    Uses OpenCL-accelerated Farneback method for efficient flow computation
    and zone-based drift vector estimation for motion correction.
    """
    
    # Constants
    ARROW_SCALE = 5
    RAD_TO_DEG = 180.0 / np.pi
    MAX_IMAGE_SIZE = 10000  # Maximum width or height in pixels
    
    def __init__(self):
        # Calibration / timing
        self.calibration: float = 1.0
        self.flow_fps: float = 30.0

        # Flow processing parameters
        self.supersat: bool = True  # Saturate color scale for better visibility
        self.flow_erosion: int = 10  # Erosion iterations (surface reduction)
        self.flow_lower_mag_thresh: float = 1.5  # Low speed filtering threshold
        self.flow_lower_cap: float = 0.0  # Remove vectors below this magnitude
        self.flow_upper_cap: float = 500.0  # Remove vectors above this magnitude
        self.flow_show_arrows: bool = True  # Show flow direction arrows
        self.flow_show_blobs: bool = True  # Show flow blobs
        self.flow_only_cardinal: bool = False  # Convert angles to up/down only

        # Drift correction parameters
        self.drift_angle: float = 10.0  # Angle tolerance for drift similarity (degrees)
        self.correct_flow: bool = False  # Enable drift correction
        self.show_correction: bool = False  # Visualize correction
        self.hideflow: bool = False  # Hide drift vectors

        # Zone configuration
        self._drift_zones: int = 4  # Number of drift correction zones
        self.zone_grids = {
            1: (1, 1), 2: (2, 1), 4: (2, 2), 8: (2, 4),
            16: (4, 4), 32: (4, 8), 64: (8, 8)
        }

        # State
        self.old_frame: Optional[np.ndarray] = None
        self.last_UMat_flow: Optional[cv2.UMat] = None
        self.erosion_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

        # Farneback parameters
        self.FB_PARAMS = {
            'pyr_scale': 0.5,
            'levels': 2,
            'winsize': 9,
            'iterations': 2,
            'poly_n': 5,
            'poly_sigma': 1.1
        }
        
        self._opencl_available = self._check_opencl_support()
        if not self._opencl_available:
            warnings.warn(
                "OpenCL not available or disabled. Falling back to CPU processing. "
                "Performance may be reduced.",
                RuntimeWarning
            )

    @property
    def drift_zones(self) -> int:
        """Number of zones for drift correction."""
        return self._drift_zones
    
    @drift_zones.setter
    def drift_zones(self, value: int):
        """Set drift zones with validation."""
        if value not in self.zone_grids:
            raise ValueError(
                f"drift_zones must be one of {list(self.zone_grids.keys())}, got {value}"
            )
        self._drift_zones = value
    
    def _check_opencl_support(self) -> bool:
        """Check if OpenCL is available and working."""
        try:
            # Try to create a small UMat to test OpenCL
            test = cv2.UMat(np.zeros((10, 10), dtype=np.uint8))
            return cv2.ocl.useOpenCL()
        except Exception:
            return False
    
    def reset(self) -> None:
        """
        Reset internal state for reuse.
        
        Clears stored frames and flow data, allowing the instance
        to be reused for a new video sequence.
        """
        self.old_frame = None
        self.last_UMat_flow = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with automatic cleanup."""
        self.reset()
        return False
    
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

    def _compute_optical_flow_farneback(
        self, 
        prev_frame: np.ndarray, 
        frame: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute optical flow using Farneback method with OpenCL acceleration.
        
        Args:
            prev_frame: Previous grayscale frame
            frame: Current grayscale frame
            
        Returns:
            Tuple of (magnitude, angle) arrays, both float32
        """
        prev_u = cv2.UMat(prev_frame)
        frame_u = cv2.UMat(frame)

        self.last_UMat_flow = cv2.calcOpticalFlowFarneback(
            prev_u, frame_u, self.last_UMat_flow,
            flags=(cv2.OPTFLOW_USE_INITIAL_FLOW if self.last_UMat_flow is not None else 0),
            **self.FB_PARAMS
        )

        fx_u, fy_u = cv2.split(self.last_UMat_flow)
        mag_u, ang_u = cv2.cartToPolar(fx_u, fy_u)

        mag_ang = cv2.merge((mag_u, ang_u)).get()
        mag = mag_ang[..., 0]
        ang = mag_ang[..., 1]

        if self.flow_only_cardinal:
            m = ang < np.pi
            ang[m] = np.float32(np.pi / 2)
            ang[~m] = np.float32(3 * np.pi / 2)

        return mag, ang

    def _filter_flow(
        self, 
        mag: np.ndarray, 
        ang: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Filter flow by magnitude threshold.
        
        Args:
            mag: Flow magnitude array
            ang: Flow angle array
            
        Returns:
            Tuple of (filtered_mag, filtered_ang, binary_mask)
        """
        mask = mag >= self.flow_lower_mag_thresh
        ang[~mask] = 0.0
        mag[~mask] = 0.0
        frame = (mask.view(np.uint8) * 255)
        return mag, ang, frame

    def _display_flow_opencl(
        self, 
        mag: np.ndarray, 
        ang: np.ndarray, 
        frame: np.ndarray
    ) -> np.ndarray:
        """
        Create flow visualization using OpenCL acceleration.
        
        Args:
            mag: Flow magnitude array (H, W) float32
            ang: Flow angle array (H, W) float32
            frame: Binary mask (H, W) uint8 with {0, 255}
            
        Returns:
            BGR visualization image (H, W, 3) uint8
        """
        H, W = mag.shape

        # Cache UMat buffers on size change
        if getattr(self, "_umat_vis_shape", None) != (H, W):
            self._sat_u = cv2.UMat(np.full((H, W), 255, np.uint8))
            self._hsv_u = cv2.UMat(np.empty((H, W, 3), np.uint8))
            self._bgr_u = cv2.UMat(np.empty((H, W, 3), np.uint8))
            self._umat_vis_shape = (H, W)

        # Upload inputs
        mag_u = cv2.UMat(mag)
        ang_u = cv2.UMat(ang)
        if frame.dtype != np.uint8:
            frm = (frame.astype(np.uint8) * 255) if frame.dtype == np.bool_ else frame.astype(np.uint8)
            frame_u = cv2.UMat(frm)
        else:
            frame_u = cv2.UMat(frame)

        # Hue = ang * (90/pi) then to uint8 (all on OpenCL)
        hue_f = cv2.multiply(ang_u, float(90.0 / np.pi))
        try:
            hue_u8 = cv2.convertScaleAbs(hue_f)
        except cv2.error:
            # Fallback if convertScaleAbs(UMat) unsupported
            hue_u8 = cv2.UMat(hue_f.get().astype(np.uint8))

        # Value channel (V)
        if self.supersat:
            val_u8 = self._sat_u  # 255
        else:
            try:
                val_f = cv2.normalize(mag_u, None, 0, 255, cv2.NORM_MINMAX)
                val_u8 = cv2.convertScaleAbs(val_f)
            except cv2.error:
                # Fallback: CPU normalize then upload
                m = mag
                mmin, mmax = float(m.min()), float(m.max())
                if mmax > mmin:
                    val_u8 = cv2.UMat(((m - mmin) * (255.0 / (mmax - mmin))).astype(np.uint8))
                else:
                    val_u8 = cv2.UMat(np.zeros_like(m, dtype=np.uint8))

        # Saturation channel (S) is 255 everywhere
        sat_u8 = self._sat_u

        # Merge HSV and convert to BGR on OpenCL
        hsv_u = cv2.merge((hue_u8, sat_u8, val_u8))
        bgr_u = cv2.cvtColor(hsv_u, cv2.COLOR_HSV2BGR)

        # Apply mask on OpenCL
        out_u = cv2.bitwise_and(bgr_u, bgr_u, mask=frame_u)

        return out_u.get()

    def _extract_contours(self, frame: np.ndarray) -> Tuple[List, np.ndarray]:
        """
        Extract contours and their areas from binary frame.
        
        Args:
            frame: Binary frame (uint8)
            
        Returns:
            Tuple of (contours_list, areas_array)
        """
        contours, _ = cv2.findContours(frame, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        # Optimized: direct array creation instead of fromiter
        areas = np.array([cv2.contourArea(c) for c in contours], dtype=np.float32)
        return contours, areas

    def _find_dominant_angle_indices(
        self, 
        angles_deg: np.ndarray, 
        tolerance: float
    ) -> np.ndarray:
        """
        Find indices of angles within tolerance of dominant direction.
        
        Args:
            angles_deg: Array of angles in degrees
            tolerance: Tolerance in degrees for grouping
            
        Returns:
            Indices of angles in dominant group
        """
        diffs = np.abs((angles_deg[:, None] - angles_deg[None, :] + 180) % 360 - 180)
        mask = diffs <= tolerance
        counts = mask.sum(axis=1)
        best_idx = counts.argmax()
        return np.flatnonzero(mask[best_idx])

    def _get_vectors(
        self, 
        cnts: List, 
        contarea: np.ndarray, 
        area_min: Optional[float], 
        area_max: Optional[float], 
        mag: np.ndarray, 
        ang: np.ndarray, 
        mask: np.ndarray
    ) -> List[List[Tuple]]:
        """
        Extract flow vectors from contours and assign to zones.
        
        Args:
            cnts: List of contours
            contarea: Array of contour areas
            area_min: Minimum area filter (or None)
            area_max: Maximum area filter (or None)
            mag: Flow magnitude array
            ang: Flow angle array
            mask: Visualization mask
            
        Returns:
            List of zone_vectors, one list per zone containing vector tuples
        """
        h, w = mag.shape
        grid_x, grid_y = self.zone_grids[self.drift_zones]
        zone_w, zone_h = w // grid_x, h // grid_y
        zone_vectors = [[] for _ in range(grid_x * grid_y)]
        only_cardinal = self.flow_only_cardinal

        for i, (c, area) in enumerate(zip(cnts, contarea)):
            if area_min is not None and area_max is not None and not (area_min <= area <= area_max):
                cv2.drawContours(mask, [c], -1, (0, 0, 0), -1)
                continue

            pts = c[:, 0, :]
            mags = mag[pts[:, 1], pts[:, 0]]
            angs = ang[pts[:, 1], pts[:, 0]]

            if only_cardinal:
                count_up = np.count_nonzero(angs == (np.pi / 2))
                count_down = np.count_nonzero(angs == (3 * np.pi / 2))
                mean_ang = np.pi / 2 if count_up >= count_down else 3 * np.pi / 2
            else:
                mean_ang = np.arctan2(np.mean(np.sin(angs)), np.mean(np.cos(angs)))
                if mean_ang < 0:
                    mean_ang += 2 * np.pi

            mean_mag = mags.mean()
            local_vx = mean_mag * np.cos(mean_ang)
            local_vy = mean_mag * np.sin(mean_ang)

            cx, cy = map(int, cv2.minEnclosingCircle(c)[0])
            idx_x = min(cx // zone_w, grid_x - 1)
            idx_y = min(cy // zone_h, grid_y - 1)
            idx_zone = idx_y * grid_x + idx_x

            zone_vectors[idx_zone].append((i, cx, cy, mean_mag, mean_ang, local_vx, local_vy, c))

        return zone_vectors

    def _compute_zone_drift_vectors(
        self, 
        zone_vectors: List[List[Tuple]]
    ) -> Tuple[List[Tuple[float, float]], int]:
        """
        Compute drift vectors for each zone.
        
        Args:
            zone_vectors: List of vectors per zone
            
        Returns:
            Tuple of (drift_vectors_list, total_vector_count)
        """
        drift_vectors = []
        vector_count = 0

        for zone_info in zone_vectors:
            if not zone_info or not self.correct_flow:
                drift_vectors.append((0.0, 0.0))
                continue

            # Optimized: pre-allocate arrays
            n = len(zone_info)
            angles_deg = np.empty(n, dtype=np.float32)
            vx_all = np.empty(n, dtype=np.float32)
            vy_all = np.empty(n, dtype=np.float32)

            for i, info in enumerate(zone_info):
                angles_deg[i] = np.degrees(info[4])
                vx_all[i] = info[5]
                vy_all[i] = info[6]

            best_indices = self._find_dominant_angle_indices(angles_deg, self.drift_angle)

            vector_count += len(best_indices)
            
            # Protection against division by zero
            if len(best_indices) > 0:
                drift_x = vx_all[best_indices].mean()
                drift_y = vy_all[best_indices].mean()
            else:
                drift_x, drift_y = 0.0, 0.0
                
            drift_vectors.append((drift_x, drift_y))

        return drift_vectors, vector_count

    def _draw_arrow(
        self, 
        mask: np.ndarray, 
        cx: int, 
        cy: int, 
        mag: float, 
        ang: float, 
        color: Tuple[int, int, int], 
        scale: float = 1.0, 
        thickness: int = 2
    ) -> None:
        """Draw flow arrow on mask."""
        if mag > 0:
            end_x = int(cx + mag * scale * np.cos(ang))
            end_y = int(cy + mag * scale * np.sin(ang))
            cv2.arrowedLine(mask, (cx, cy), (end_x, end_y), color, thickness, cv2.LINE_AA)

    def _identify_drift_vectors(
        self, 
        zone_info: List[Tuple], 
        drift_angle: float
    ) -> set:
        """
        Identify which vectors in zone are drift vectors.
        
        Args:
            zone_info: List of vector info tuples for zone
            drift_angle: Angle tolerance in degrees
            
        Returns:
            Set of indices that are drift vectors
        """
        if not zone_info:
            return set()
        
        angles_deg = np.degrees([info[4] for info in zone_info])
        best_indices = self._find_dominant_angle_indices(angles_deg, drift_angle)
        return set(best_indices.tolist())

    def _process_zone_vectors(
        self,
        zone_info: List[Tuple],
        drift_x: float,
        drift_y: float,
        drift_indices: set,
        mask: Optional[np.ndarray],
        fps: float
    ) -> Tuple[List[float], List[float]]:
        """
        Process vectors in a zone: correct, draw, and collect statistics.
        
        Args:
            zone_info: List of vector info tuples
            drift_x: Drift correction in x
            drift_y: Drift correction in y
            drift_indices: Set of indices that are drift vectors
            mask: Visualization mask (or None)
            fps: Frames per second
            
        Returns:
            Tuple of (magnitudes_list, angles_list)
        """
        mags, angles = [], []
        draw_arrows = self.flow_show_arrows and mask is not None

        for local_idx, (_, cx, cy, mean_mag, mean_ang, local_vx, local_vy, c) in enumerate(zone_info):
            if self.correct_flow:
                corr_vx = local_vx - drift_x
                corr_vy = local_vy - drift_y
                mean_mag_corr = np.hypot(corr_vx, corr_vy)
                mean_ang_corr = np.arctan2(corr_vy, corr_vx)

                if draw_arrows:
                    if self.show_correction and not (local_idx in drift_indices and self.hideflow):
                        self._draw_arrow(mask, cx, cy, mean_mag, mean_ang, (0, 0, 255), self.ARROW_SCALE)
                    if not (local_idx in drift_indices and self.hideflow):
                        self._draw_arrow(mask, cx, cy, mean_mag_corr, mean_ang_corr, (0, 255, 0), self.ARROW_SCALE)
            else:
                mean_mag_corr = mean_mag
                mean_ang_corr = mean_ang
                if draw_arrows:
                    self._draw_arrow(mask, cx, cy, mean_mag, mean_ang, (0, 0, 255), self.ARROW_SCALE)

            if self.correct_flow and local_idx in drift_indices:
                continue

            computed_speed = mean_mag_corr * self.calibration * fps
            if self.flow_lower_cap <= computed_speed <= self.flow_upper_cap:
                mags.append(computed_speed)
                angles.append((mean_ang_corr * self.RAD_TO_DEG) % 360)

        return mags, angles

    def _hide_drift_contours(
        self, 
        mask: Optional[np.ndarray], 
        contours_to_hide: List
    ) -> None:
        """Hide drift contours by drawing them black."""
        if self.hideflow and mask is not None:
            for c in contours_to_hide:
                cv2.drawContours(mask, [c], -1, (0, 0, 0), -1)

    def _correct_and_draw_vectors(
        self, 
        zone_vectors: List[List[Tuple]], 
        drift_vectors: List[Tuple[float, float]], 
        mask: Optional[np.ndarray], 
        fps: float
    ) -> Tuple[List[float], List[float]]:
        """
        Correct flow vectors and draw visualization.
        
        Args:
            zone_vectors: Vectors organized by zone
            drift_vectors: Drift correction per zone
            mask: Visualization mask (or None)
            fps: Frames per second
            
        Returns:
            Tuple of (all_magnitudes, all_angles)
        """
        mags, angles = [], []
        contours_to_hide = []

        for zone_idx, zone_info in enumerate(zone_vectors):
            drift_x, drift_y = drift_vectors[zone_idx]
            drift_indices = self._identify_drift_vectors(zone_info, self.drift_angle)

            if self.hideflow:
                contours_to_hide.extend(zone_info[i][7] for i in drift_indices)

            zone_mags, zone_angles = self._process_zone_vectors(
                zone_info, drift_x, drift_y, drift_indices, mask, fps
            )
            mags.extend(zone_mags)
            angles.extend(zone_angles)

        self._hide_drift_contours(mask, contours_to_hide)
        return mags, angles

    def _show_zones(self, mask: np.ndarray) -> np.ndarray:
        """Draw zone grid lines on mask."""
        h, w = mask.shape[:2]
        grid_x, grid_y = self.zone_grids[self.drift_zones]
        zone_w, zone_h = w // grid_x, h // grid_y
        for x in range(zone_w, w, zone_w):
            cv2.line(mask, (x, 0), (x, h), (255, 255, 255), 1, cv2.LINE_AA)
        for y in range(zone_h, h, zone_h):
            cv2.line(mask, (0, y), (w, y), (255, 255, 255), 1, cv2.LINE_AA)
        return mask

    def _compute_zone_centers(
        self, 
        grid_x: int, 
        grid_y: int, 
        zone_w: int, 
        zone_h: int
    ) -> List[Tuple[int, int]]:
        """Compute center coordinates for each zone."""
        half_w, half_h = zone_w // 2, zone_h // 2
        return [(i * zone_w + half_w, j * zone_h + half_h) for j in range(grid_y) for i in range(grid_x)]

    def _draw_drift_vectors(self, drift_vectors: List[Tuple[float, float]], mask: np.ndarray) -> None:
        """Draw drift vector arrows at zone centers."""
        h, w = mask.shape[:2]
        grid_x, grid_y = self.zone_grids[self.drift_zones]
        zone_w, zone_h = w // grid_x, h // grid_y
        zone_centers = self._compute_zone_centers(grid_x, grid_y, zone_w, zone_h)
        arrow_length = int(min(h, w) * 0.05)
        for (dx, dy), (zx, zy) in zip(drift_vectors, zone_centers):
            norm = np.hypot(dx, dy)
            if norm > 0:
                ang = np.arctan2(dy, dx)
                self._draw_arrow(mask, zx, zy, 1.0, ang, (255, 255, 255), arrow_length / norm)

    def _flow_process_frame_pair(
        self, 
        frame_pair: Tuple[np.ndarray, np.ndarray], 
        mask: Optional[np.ndarray] = None, 
        delta_t: Optional[float] = None
    ) -> Tuple[List[float], List[float], Optional[np.ndarray], Tuple[int, int]]:
        """
        Process a pair of frames to compute optical flow.
        
        Args:
            frame_pair: Tuple of (previous_frame, current_frame)
            mask: Visualization mask (or None)
            delta_t: Time between frames in seconds (or None)
            
        Returns:
            Tuple of (magnitudes, angles, mask, motility_stats)
        """
        fps = (1 / delta_t) if delta_t else self.flow_fps
        prev_frame, frame = frame_pair

        mag, ang = self._compute_optical_flow_farneback(prev_frame, frame)
        mag, ang, frame = self._filter_flow(mag, ang)
        frame = cv2.erode(frame, self.erosion_kernel, iterations=self.flow_erosion)

        if mask is not None and self.flow_show_blobs:
            mask = self._display_flow_opencl(mag, ang, frame)

        cnts, contarea = self._extract_contours(frame)
        if not cnts:
            return [], [], mask, (0, 0)

        zone_vectors = self._get_vectors(cnts, contarea, None, None, mag, ang, mask)
        drift_vectors, vector_count = self._compute_zone_drift_vectors(zone_vectors)

        mags, angles = self._correct_and_draw_vectors(zone_vectors, drift_vectors, mask, fps)

        if mask is not None and self.show_correction:
            mask = self._show_zones(mask)
        if self.correct_flow and self.show_correction and mask is not None:
            self._draw_drift_vectors(drift_vectors, mask)

        motility = (len(mags), vector_count)
        return mags, angles, mask, motility

    def calc_flow(
        self, 
        frame_bgr: np.ndarray, 
        delta_t: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray, List[float], List[float], Tuple[int, int]]:
        """
        Calculate dense optical flow on a BGR or grayscale frame.
        
        Args:
            frame_bgr: BGR image (H, W, 3) or grayscale image (H, W)
            delta_t: Time between frames in seconds (or None to use flow_fps)
            
        Returns:
            Tuple of (overlay, mask, magnitudes, angles, motility_stats)
                - overlay: Original frame with flow visualization (H, W, 3)
                - mask: Flow visualization mask (H, W, 3)
                - magnitudes: List of calibrated speeds (µm/s)
                - angles: List of angles in degrees
                - motility_stats: Tuple of (num_vectors, num_drift_vectors)
                
        Raises:
            ValueError: If frame is invalid or delta_t is negative
            TypeError: If frame is not a numpy array
        """
        # Validate inputs
        self._validate_frame(frame_bgr, "frame_bgr")
        
        if delta_t is not None and delta_t <= 0:
            raise ValueError(f"delta_t must be positive, got {delta_t}")
        
        # Detect if frame is grayscale or BGR
        is_gray = len(frame_bgr.shape) == 2 or frame_bgr.shape[2] == 1
        
        if is_gray:
            # Frame is already grayscale
            gray = frame_bgr if len(frame_bgr.shape) == 2 else frame_bgr[:, :, 0]
            # Convert to BGR for visualization
            original_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        else:
            # Frame is BGR
            original_frame = frame_bgr.copy()
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        
        mask = np.zeros_like(original_frame)

        if self.old_frame is None:
            self.old_frame = gray.copy()

        mags, angles, mask, motility = self._flow_process_frame_pair((self.old_frame, gray), mask, delta_t)
        self.old_frame = gray.copy()
        overlay = cv2.add(original_frame, mask)
        return overlay, mask, mags, angles, motility

    def calc_flow_regions(
        self, 
        frame_bgr: np.ndarray, 
        polys: List[np.ndarray], 
        delta_t: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray, List[float], List[float], Tuple[int, int]]:
        """
        Calculate optical flow within specified polygonal regions.
        
        Args:
            frame_bgr: BGR image (H, W, 3) or grayscale image (H, W)
            polys: List of polygons defining regions of interest
            delta_t: Time between frames in seconds (or None to use flow_fps)
            
        Returns:
            Tuple of (overlay, mask, magnitudes, angles, motility_stats)
            
        Raises:
            ValueError: If frame is invalid or delta_t is negative
            TypeError: If frame is not a numpy array
        """
        # Validate inputs
        self._validate_frame(frame_bgr, "frame_bgr")
        
        if delta_t is not None and delta_t <= 0:
            raise ValueError(f"delta_t must be positive, got {delta_t}")
        
        original_frame = frame_bgr.copy()
        mask = np.zeros_like(frame_bgr)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        if self.old_frame is None:
            self.old_frame = gray.copy()

        fps = (1 / delta_t) if delta_t else self.flow_fps
        mag, ang = self._compute_optical_flow_farneback(self.old_frame, gray)
        self.old_frame = gray.copy()

        mags, angles = [], []
        if polys:
            for poly in polys:
                poly = np.asarray(poly, dtype=np.int32)

                # Binary mask for this cell
                region_mask = np.zeros(mag.shape, dtype=np.uint8)
                cv2.fillPoly(region_mask, [poly], 255)

                ys, xs = np.where(region_mask != 0)
                if ys.size == 0:
                    continue

                mags_loc = mag[ys, xs]
                angs_loc = ang[ys, xs]

                # Circular mean for angle
                mean_ang = float(np.arctan2(np.mean(np.sin(angs_loc)),np.mean(np.cos(angs_loc))))
                if mean_ang < 0:
                    mean_ang += 2 * np.pi
                mean_mag = float(mags_loc.mean())

                # Convert to calibrated speed
                speed_cal = mean_mag * self.calibration * fps
                if self.flow_lower_cap <= speed_cal <= self.flow_upper_cap:
                    mags.append(speed_cal)
                    angles.append(np.degrees(mean_ang) % 360.0)

                # Draw arrow at polygon centroid
                if self.flow_show_arrows:
                    M = cv2.moments(region_mask)
                    if M["m00"] != 0:
                        cx = int(M["m10"] / M["m00"])
                        cy = int(M["m01"] / M["m00"])
                        self._draw_arrow(mask, cx, cy, mean_mag, mean_ang, (0, 255, 0), scale=5)

        overlay = cv2.add(original_frame, mask)
        motility = (len(mags), len(mags))
        return overlay, mask, mags, angles, motility