"""
Webcam Controller Module
========================

A unified wrapper around pygrabber (DirectShow) to control both standard webcams 
and specialized high-bit-depth cameras (e.g., SeeCAM).

Features:
- Unified interface for different camera types.
- Support for Y8, Y12, Y16 raw formats with automatic conversion.
- Exposure and Gain control (Auto/Manual).
- Robust error handling.
"""

import numpy as np
import cv2
import time
from typing import Optional, Tuple, Dict, List, Union, Any
from comtypes import COMError, CoInitialize
from ctypes import c_long, byref

# Import from pygrabber as requested (doing NOT modify pygrabber)
from pygrabber.dshow_graph import FilterGraph, FilterType
from pygrabber.dshow_ids import MediaSubtypes, MediaTypes
from pygrabber.dshow_core import IAMCameraControlIID, IAMVideoProcAmpIID

# Constants for DirectShow Controls
CameraControl_Exposure = 4
CameraControl_Flags_Auto = 0x0001
CameraControl_Flags_Manual = 0x0002

VideoProcAmp_Brightness = 0
VideoProcAmp_Gain = 9
VideoProcAmp_Flags_Auto = 0x0001
VideoProcAmp_Flags_Manual = 0x0002


class WebcamController:
    """
    Unified controller for webcams using DirectShow (via pygrabber).
    Compatible with SeeCAM (Y12/Y16) and standard RGB cameras.
    """

    def __init__(self, camera_index_or_name: Union[int, str] = 0):
        """
        Initialize the controller. Does not open the camera immediately.
        
        Args:
            camera_index_or_name: ID (int) or Name (str) of the camera.
        """
        try:
            CoInitialize()
        except:
            pass

        self.camera_source = camera_index_or_name
        
        self.graph: Optional[FilterGraph] = None
        self.cam_ctrl = None
        self.proc_amp = None
        
        self.is_open = False
        self.is_open = False
        self.width = 0
        self.height = 0
        self._fps = 30.0
        self.format_str = "Unknown"
        
        self.frame_ready = False
        self.last_frame = None
        self.last_raw_frame = None  # To store original high-bit-depth frame if needed
        
        # Auto-exposure state
        self.exposure_check_count = 0
        self.max_exposure_check = 4

    def open(self, width: Optional[int] = None, height: Optional[int] = None, fps: Optional[float] = None, 
             format_index: Optional[int] = None, media_subtype: Optional[str] = None) -> bool:
        """
        Open and configure the camera.
        
        Args:
            width: Desired width.
            height: Desired height.
            fps: Desired FPS (approximate).
            fps: Desired FPS (approximate).
            format_index: Force a specific format index from list_formats().
            media_subtype: Preferred format subtype (e.g., 'Y16', 'Y8').
            
        Returns:
            True if successful.
        """
        if self.is_open:
            return True

        try:
            self.graph = FilterGraph()
            
            # Resolve camera index
            cam_idx = self._resolve_camera_index()
            if cam_idx is None:
                return False

            # Add device to graph
            self.graph.add_video_input_device(cam_idx)
            
            # Handle specific formats (Critical for SeeCAM)
            curr_format_idx = format_index
            
            # If no specific format requested, try to find the best one or use current
            if curr_format_idx is None:
                curr_format_idx = self._auto_select_format()

            if curr_format_idx is not None:
                self._set_format_by_index(curr_format_idx)

            # Add Null Render
            self.graph.add_null_render()
            
            # Add Sample Grabber
            self.graph.add_sample_grabber(self._frame_callback)
            sample_grabber = self.graph.filters[FilterType.sample_grabber]
            
            # Configure Media Type for Sample Grabber
            self._configure_media_type(sample_grabber)
            
            # Prepare and Run
            self.graph.prepare_preview_graph()
            self.graph.run()
            
            # Get properties
            current_fmt = self.graph.get_input_device().get_current_format()
            self.format_str, self.width, self.height = current_fmt
            
            if fps:
                self._fps = fps
            
            # Get Controls
            self._init_controls()
            
            self.is_open = True
            return True

        except Exception as e:
            print(f"[WebcamController] Error opening camera: {e}")
            self.close()
            return False

    def close(self):
        """Stop graph and release resources."""
        if self.graph:
            try:
                self.graph.stop()
            except:
                pass
            self.graph = None
        
        self.cam_ctrl = None
        self.proc_amp = None
        self.is_open = False

    def read(self, timeout: float = 1.0) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame.
        
        Args:
            timeout: Max wait time in seconds.
            
        Returns:
            (valid, frame_bgr)
            Frame is always 8-bit BGR for display compatibility.
            Use get_last_raw_frame() if you need the 12/16 bit data.
        """
        if not self.is_open or not self.graph:
            return False, None

        self.frame_ready = False
        try:
            if not self.graph.grab_frame():
                return False, None
            
            # Wait for callback
            start = time.time()
            while not self.frame_ready:
                if time.time() - start > timeout:
                    return False, None
                time.sleep(0.001)
                
            if self.last_frame is not None:
                # Ensure BGR for consistency
                if self.last_frame.ndim == 2:
                    return True, cv2.cvtColor(self.last_frame, cv2.COLOR_GRAY2BGR)
                return True, self.last_frame
                
            return False, None
            
        except Exception as e:
            print(f"[WebcamController] Read error: {e}")
            return False, None

    def get_last_raw_frame(self) -> Optional[np.ndarray]:
        """Returns the raw frame data (potentially 16-bit) from the last read."""
        return self.last_raw_frame

    def _resolve_camera_index(self) -> Optional[int]:
        devices = self.list_devices()
        if isinstance(self.camera_source, int):
            if 0 <= self.camera_source < len(devices):
                return self.camera_source
        elif isinstance(self.camera_source, str):
            for i, name in enumerate(devices):
                if self.camera_source == name:
                    return i
                # fuzzy match
                if self.camera_source.lower() in name.lower():
                    return i
        
        print(f"[WebcamController] Camera '{self.camera_source}' not found.")
        return None

    def _auto_select_format(self) -> Optional[int]:
        """
        Heuristic to choose the best format.
        Prioritizes SeeCAM formats (Y16, Y12, Y8) if available.
        """
        try:
            formats = self.graph.get_input_device().get_formats()
            # Priority list
            for fmt_str in ["Y16", "Y12", "Y8"]:
                for f in formats:
                    if f['media_type_str'] == fmt_str:
                        return f['index']
            # Default: no change, let graph decide or use current
            return None
        except:
            return None

    def _set_format_by_index(self, index: int):
        try:
            self.graph.get_input_device().set_format(index)
        except Exception as e:
            print(f"[WebcamController] Failed to set format index {index}: {e}")

    def _configure_media_type(self, sample_grabber):
        """Configure sample grabber media type based on current format."""
        try:
            fmt_str, _, _ = self.graph.get_input_device().get_current_format()
            if fmt_str == "Y8":
                sample_grabber.set_media_type(MediaTypes.Video, MediaSubtypes.Y8)
            elif fmt_str == "Y12":
                sample_grabber.set_media_type(MediaTypes.Video, MediaSubtypes.Y12)
            elif fmt_str == "Y16":
                sample_grabber.set_media_type(MediaTypes.Video, MediaSubtypes.Y16)
            else:
                # Default (RGB/MJPG) - usually handled automatically by pygrabber
                pass
        except Exception as e:
            print(f"[WebcamController] Media type set warning: {e}")

    def _init_controls(self):
        """Initialize DirectShow control interfaces."""
        try:
            video_input = self.graph.filters[FilterType.video_input].instance
            try:
                self.cam_ctrl = video_input.QueryInterface(IAMCameraControlIID)
            except:
                pass
            try:
                self.proc_amp = video_input.QueryInterface(IAMVideoProcAmpIID)
            except:
                pass
        except:
            pass

    def _frame_callback(self, buffer, blen):
        """
        Handle raw buffer data from DirectShow.
        Decodes Y12/Y16/Y8 and others.
        """
        try:
            # Get current format metadata
            fmt = self.format_str
            w, h = self.width, self.height
            
            if fmt == "Y12":
                buffer_np = np.ctypeslib.as_array(buffer, shape=(blen,))
                triplets = buffer_np.reshape(-1, 3)
                
                pixel1 = ((triplets[:, 0].astype(np.uint16) << 4) | (triplets[:, 2] & 0x0F))
                pixel2 = ((triplets[:, 1].astype(np.uint16) << 4) | ((triplets[:, 2] >> 4) & 0x0F))
                
                pixels = np.empty((w * h,), dtype=np.uint16)
                pixels[0::2] = pixel1
                pixels[1::2] = pixel2
                
                self.last_raw_frame = pixels.reshape(h, w)
                self.last_frame = (self.last_raw_frame >> 4).astype(np.uint8)

            elif fmt == "Y16":
                buffer_np = np.ctypeslib.as_array(buffer, shape=(blen,))
                frame_16 = buffer_np.view(dtype=np.uint16).reshape(h, w)
                self.last_raw_frame = frame_16
                self.last_frame = (frame_16 >> 2).astype(np.uint8)

            elif fmt == "Y8":
                buffer_np = np.ctypeslib.as_array(buffer, shape=(blen,))
                frame_8 = buffer_np.view(dtype=np.uint8).reshape(h, w)
                self.last_raw_frame = frame_8
                self.last_frame = frame_8

            else:
                buffer_np = np.ctypeslib.as_array(buffer, shape=(blen,))
                buffer_uint8 = buffer_np.view(dtype=np.uint8)
                
                try:
                    frame = buffer_uint8.reshape(h, w, 3)
                except ValueError:
                    try:
                        frame = buffer_uint8.reshape(h, w)
                    except:
                        frame = None
                
                self.last_raw_frame = frame
                self.last_frame = frame

            self.frame_ready = True
            
        except Exception as e:
            pass

    def set_exposure(self, value: int, manual: bool = True) -> bool:
        if not self.cam_ctrl: return False
        try:
            flags = CameraControl_Flags_Manual if manual else CameraControl_Flags_Auto
            hr = self.cam_ctrl.Set(CameraControl_Exposure, value, flags)
            return True
        except COMError:
            return False

    def get_exposure(self) -> int:
        if not self.cam_ctrl: return 0
        val = c_long()
        flags = c_long()
        try:
            self.cam_ctrl.Get(CameraControl_Exposure, byref(val), byref(flags))
            return val.value
        except COMError:
            return 0

    def set_gain(self, value: int, manual: bool = True) -> bool:
        if not self.proc_amp: return False
        
        def try_set(prop_id):
            flags = VideoProcAmp_Flags_Manual if manual else VideoProcAmp_Flags_Auto
            self.proc_amp.Set(prop_id, value, flags)

        try:
            try_set(VideoProcAmp_Brightness)
            return True
        except COMError:
            pass
            
        # Try actual Gain
        try:
            try_set(VideoProcAmp_Gain)
            return True
        except COMError:
            return False

    def get_gain(self) -> int:
        if not self.proc_amp: return 0
        val = c_long()
        flags = c_long()
        try:
            # Try Brightness first
            self.proc_amp.Get(VideoProcAmp_Brightness, byref(val), byref(flags))
            return val.value
        except COMError:
            try:
                # Try Gain
                self.proc_amp.Get(VideoProcAmp_Gain, byref(val), byref(flags))
                return val.value
            except COMError:
                return 0

    def get_parameter_range(self, param_name: str) -> Optional[Dict[str, int]]:
        """
        Get range for 'exposure' or 'gain'.
        Returns {'min':, 'max':, 'step':, 'default':}
        """
        target_ctrl = None
        prop_id = None
        
        if param_name.lower() == 'exposure':
            target_ctrl = self.cam_ctrl
            prop_id = CameraControl_Exposure
        elif param_name.lower() == 'gain':
            # Try Brightness first as per SeeCAM convention
            target_ctrl = self.proc_amp
            prop_id = VideoProcAmp_Brightness
        
        if not target_ctrl:
            return None
            
        # Define c_long variables
        min_v = c_long()
        max_v = c_long()
        step_v = c_long()
        def_v = c_long()
        flags = c_long()
            
        try:
            target_ctrl.GetRange(prop_id, byref(min_v), byref(max_v), byref(step_v), byref(def_v), byref(flags))
            return {
                "min": min_v.value, "max": max_v.value, "step": step_v.value, "default": def_v.value, "flags": flags.value
            }
        except COMError:
             # Retry gain on actual Gain param if Brightness failed
            if param_name.lower() == 'gain' and prop_id == VideoProcAmp_Brightness:
                prop_id = VideoProcAmp_Gain
                try:
                    target_ctrl.GetRange(prop_id, byref(min_v), byref(max_v), byref(step_v), byref(def_v), byref(flags))
                    return {
                        "min": min_v.value, "max": max_v.value, "step": step_v.value, "default": def_v.value, "flags": flags.value
                    }
                except:
                    pass
            return None

    @property
    def fps(self) -> float:
        return self._fps

    def get_info(self) -> Dict[str, Any]:
        """Return camera info for UI/logging"""
        return {
            "name": self.camera_source,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "format": self.format_str,
            "is_open": self.is_open,
            "exposure": self.get_exposure(),
            "gain": self.get_gain()
        }
    
    @staticmethod
    def list_devices() -> List[str]:
        try:
            CoInitialize()
            graph = FilterGraph()
            return graph.get_input_devices()
        except:
            return []

    # Context Manager
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def auto_exposure_loop(self, target_brightness=128):
        """Simple software AE iteration."""
        if not self.is_open or not self.last_frame is not None:
            return

        # Simple logic: measure mean brightness -> adjust exposure
        curr_mean = np.mean(self.last_frame)
        curr_exp = self.get_exposure()
        
        # Deadband
        if abs(curr_mean - target_brightness) < 10:
            return

        # Adjust
        if curr_mean < target_brightness:
            self.set_exposure(curr_exp + 1)
        else:
            self.set_exposure(curr_exp - 1)
