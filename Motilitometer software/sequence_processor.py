import threading
import time
import re
import os
from typing import Callable, Optional, Dict

class SequenceProcessor(threading.Thread):
    """
    Process .seq files for automation.
    Runs in a separate thread.
    """
    def __init__(self, file_path: str, light_ctrl, record_start_cb: Callable[[float], None], record_stop_cb: Callable[[], None], log_cb: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.file_path = file_path
        self.light_ctrl = light_ctrl
        self.record_start_cb = record_start_cb
        self.record_stop_cb = record_stop_cb
        self.log_cb = log_cb
        self.running = False
        self.daemon = True
        
        # Progress Tracking
        self.total_duration = 0.0
        self.start_time = 0.0
        self.current_cmd = ""
        self.elapsed_time = 0.0 # Track actual elapsed sleep time
        
        self._calculate_total_duration()

    def _calculate_total_duration(self):
        """Pre-scan file to calculate total blocking time (Waits)."""
        try:
            self.total_duration = 0.0
            with open(self.file_path, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'): continue
                
                # Check for Wait commands
                match_wait = re.match(r'^(\d+(\.\d+)?)(s|min)$', line.lower())
                if match_wait:
                    val = float(match_wait.group(1))
                    unit = match_wait.group(3)
                    if unit == 'min': val *= 60
                    self.total_duration += val
        except:
            pass

    def get_status(self) -> Dict:
        """Return current sequence status."""
        p = 0.0
        if self.running and self.start_time > 0 and self.total_duration > 0:
            now = time.time()
            p = min(1.0, (now - self.start_time) / self.total_duration)
        
        return {
            "cmd": self.current_cmd,
            "progress": p,
            "total_duration": self.total_duration
        }

    def log(self, msg: str):
        if self.log_cb:
            self.log_cb(msg)
        else:
            print(f"[SEQ] {msg}")

    def run(self):
        self.running = True
        self.start_time = time.time()
        self.log(f"Starting sequence ({self.total_duration}s)...")
        
        try:
            with open(self.file_path, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                if not self.running: break
                line = line.strip()
                if not line or line.startswith('#'): continue
                
                self.current_cmd = line
                try:
                    self.process_command(line)
                except Exception as e:
                    self.log(f"Error: {e}")
                    
        except FileNotFoundError:
            self.log(f"File not found: {self.file_path}")
        except Exception as e:
            self.log(f"Sequence error: {e}")
        
        self.log("Sequence finished.")
        self.current_cmd = "Done"
        self.running = False

    def stop(self):
        self.running = False

    def process_command(self, cmd: str):
        # 1. Video Command
        if cmd.upper().startswith('V'):
            match = re.match(r'V(\d+(\.\d+)?)', cmd.upper())
            if match:
                 duration = float(match.group(1))
                 if 'min' in cmd.lower(): duration *= 60
                 self.handle_video(duration)
                 return

        # 2. Wait
        match_wait = re.match(r'^(\d+(\.\d+)?)(s|min)$', cmd.lower())
        if match_wait:
            val = float(match_wait.group(1))
            unit = match_wait.group(3)
            if unit == 'min': val *= 60
            time.sleep(val)
            return

        # 3. Light Commands
        found_light = False
        patterns = [
            (r'IR(\d+)', 'ir'),
            (r'R(\d+)', 'r'),
            (r'G(\d+)', 'g'),
            (r'B(\d+)', 'b'),
            (r'W(\d+)', 'w'),
        ]
        
        updates = {}
        cmd_upper = cmd.upper()
        for pat, key in patterns:
            matches = re.finditer(pat, cmd_upper)
            for m in matches:
                updates[key] = int(m.group(1))
                found_light = True
        
        if found_light and self.light_ctrl:
            for k, v in updates.items():
                self.light_ctrl.set_value(k, v)
        elif not found_light:
            self.log(f"Unknown: {cmd}")

    def handle_video(self, duration: float):
        self.log(f"Starting async recording for {duration}s")
        self.record_start_cb(duration)
        stop_timer = threading.Timer(duration, self.record_stop_cb)
        stop_timer.start()
