"""
Command Line Interface for Motilitometer

This module provides the CLI argument parser and user interface.
All video processing logic is delegated to VideoProcessor.
"""

import argparse
import os
import time
import cv2
import msvcrt # For terminal input on Windows

# Rich for beautiful terminal output
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live
from rich.layout import Layout
from rich.console import Group

from video_processor import VideoProcessor
from video_recorder import VideoRecorder
try:
    from light_controller import LightController
except ImportError:
    LightController = None
try:
    from sequence_processor import SequenceProcessor
except ImportError:
    SequenceProcessor = None

# Configure OpenCV
cv2.ocl.setUseOpenCL(True)
cv2.setNumThreads(1)

console = Console()


class RichHelpFormatter(argparse.HelpFormatter):
    """Custom help formatter using Rich Panels."""
    
    def __init__(self, prog):
        super().__init__(prog, max_help_position=40, width=100)

    def _format_action_invocation(self, action):
        if not action.option_strings:
            return super()._format_action_invocation(action)
        return ", ".join([f"[bold cyan]{o}[/bold cyan]" for o in action.option_strings])

    def _format_args(self, action, default_metavar):
        return f"[dim]{super()._format_args(action, default_metavar)}[/dim]"

    def add_argument(self, action):
        if action.help:
            help_text = action.help
            if "%(default)" in help_text:
                help_text = help_text.replace("%(default)s", f"[yellow]{action.default}[/yellow]")
            elif action.default != argparse.SUPPRESS and action.default is not None:
                help_text += f" (default: [yellow]{action.default}[/yellow])"
            action.help = help_text
        super().add_argument(action)


def parse_args():
    """Parse command line arguments."""
    examples = """[bold white]Examples:[/bold white]
  [green]1. Basic Tracking:[/green]
    python motilitometer.py --video input.mp4 --processing tracking --show-trails --motility

  [green]2. Optical Flow with Correction:[/green]
    python motilitometer.py --video input.mp4 --processing flow --correct-flow --show-correction

  [green]3. Export Data:[/green]
    python motilitometer.py --video input.mp4 --processing tracking --export-csv --export-pkl

  [green]4. Webcam:[/green]
    python motilitometer.py --source webcam --processing flow
"""
    p = argparse.ArgumentParser(
        description="[bold blue]Motilitometer[/bold blue] - Cell Tracking & Optical Flow Analysis",
        epilog=examples,
        formatter_class=RichHelpFormatter
    )
    
    # Override standard print_help to use console.print for parsing rich markup
    # AND to implement the Panel logic by post-processing groups
    def rich_print_help(file=None):
        import sys
        from io import StringIO
        
        console.print(f"\n[bold blue]🔬 MOTILITOMETER[/bold blue] - {p.description}\n")
        console.print(f"[dim]Usage: {p.format_usage().split('usage: ')[-1].strip()}[/dim]\n")
        
        # Print grouped arguments in Panels
        for group in p._action_groups:
            if not group._group_actions:
                continue
                
            # Skip usage group (usually the first one) if empty or default
            if group.title == "options": 
                title = "Optional Arguments"
                style = "white"
            elif "Tracking" in group.title:
                title = group.title
                style = "green"
            elif "Flow" in group.title:
                title = group.title
                style = "magenta"
            elif "Export" in group.title:
                title = group.title
                style = "cyan"
            elif "Core" in group.title:
                title = group.title
                style = "blue"
            else:
                title = group.title
                style = "white"

            # Create a fresh formatter for this group
            formatter = RichHelpFormatter(p.prog)
            
            # Add arguments to the formatter
            formatter.start_section(title)
            formatter.add_arguments(group._group_actions)
            formatter.end_section()
            
            # Extract text
            group_help = formatter.format_help()
            
            # Cleanup only the title line from the output to avoid duplication in Panel
            lines = group_help.strip().split('\n')
            # Remove the first line if it matches the title (argparse usually uppercases titles)
            if lines and (lines[0].strip().upper() == title.upper() or lines[0].strip() == title):
                lines = lines[1:]
            
            content = "\n".join(lines).strip()
            
            if content:
                console.print(Panel(content, title=f"[bold {style}]{title}[/bold {style}]", border_style=style, expand=False))

        # Print epilog (Examples)
        console.print("\n" + p.epilog)

    p.print_help = rich_print_help
    
    # Core
    g_core = p.add_argument_group("Core Configuration")
    g_core.add_argument("--video", help="Path to input video (ignored if --source=webcam)", default="demo_vertical.mp4")
    g_core.add_argument("--source", choices=["file", "webcam"], default="file", help="Video source type")
    g_core.add_argument("--camera-index", type=int, default=0, help="Camera device index for webcam source")
    g_core.add_argument("--camera-width", type=int, help="Desired camera width")
    g_core.add_argument("--camera-height", type=int, help="Desired camera height")
    g_core.add_argument("--media-index", type=int, help="Specific camera format index")
    g_core.add_argument("--exposure", type=int, help="Initial exposure value")
    g_core.add_argument("--gain", type=int, help="Initial gain value")
    g_core.add_argument("--processing", choices=["none", "tracking", "flow"], default="none", help="Processing mode (default: none)")
    g_core.add_argument("--display", choices=["none", "frame", "mask", "overlay"], default="overlay", help="Visualization mode")
    g_core.add_argument("--quit-key", default="q", help="Key to quit the viewer")
    g_core.add_argument("--calibration", type=float, default=1.0, help="px to µm factor")
    g_core.add_argument("--fps-ref", type=float, default=30, help="Video frame rate (override)")

    # Tracking-specific
    g_track = p.add_argument_group("Tracking Mode Options")
    g_track.add_argument("--motility", action="store_true", default=False, help="Enable motility analysis")
    g_track.add_argument("--motility-mode", choices=["speed", "angle"], default="speed", help="Motility definition method")
    g_track.add_argument("--motility-thresh", type=float, default=30.0, help="Threshold for motility")
    
    g_track_vis = p.add_argument_group("Tracking Visualization")
    g_track_vis.add_argument("--show-trails", action="store_true", default=False, help="Draw movement trails")
    g_track_vis.add_argument("--show-id", action="store_true", default=False, help="Show track IDs")
    g_track_vis.add_argument("--show-age", action="store_true", default=False, help="Show track age")
    g_track_vis.add_argument("--show-distance", action="store_true", default=False, help="Show total distance")
    g_track_vis.add_argument("--show-speed", action="store_true", default=False, help="Show current speed")
    g_track_vis.add_argument("--traces-len", type=int, default=50, help="Length of trails in frames")
    g_track_vis.add_argument("--show-blob", action="store_true", default=False, help="Show detected cell blobs")
    g_track_vis.add_argument("--show-selection", action="store_true", default=False, help="Show selected regions")
    g_track_vis.add_argument("--show-centers", action="store_true", default=False, help="Show cell centers")
    g_track_vis.add_argument("--show-boxes", action="store_true", default=False, help="Show bounding boxes")
    g_track_vis.add_argument("--show-motile", action="store_true", default=False, help="Highlight motile cells")
    g_track_vis.add_argument("--show-circle", action="store_true", default=False, help="Draw circles around motile cells")

    g_track_algo = p.add_argument_group("Tracking Algorithm Tuning")
    g_track_algo.add_argument("--reset-tracking", type=int, default=None, help="Reset tracking every N frames")
    g_track_algo.add_argument("--max-age", type=int, default=None, help="Maximum frame age for tracks")
    g_track_algo.add_argument("--angle-tol", type=float, default=10.0, help="Angle tolerance (deg) for angle-motility")
    g_track_algo.add_argument("--min-trace-angle", type=int, default=5, help="Min track length for angle calc")
    g_track_algo.add_argument("--blur", type=int, default=3, help="Preprocessing blur kernel size")
    g_track_algo.add_argument("--thresh-block-size", type=int, default=25, help="Adaptive threshold block size")
    g_track_algo.add_argument("--thresh-bin-thresh", type=int, default=15, help="Adaptive threshold constant")
    g_track_algo.add_argument("--erosion", type=int, default=1, help="Morphological erosion iterations")
    g_track_algo.add_argument("--agg-correction", action="store_true", default=False, help="Aggressive correction")
    g_track_algo.add_argument("--lower-surf-thresh", type=int, default=35, help="Min cell area percentile")
    g_track_algo.add_argument("--upper-surf-thresh", type=int, default=90, help="Max cell area percentile")

    # Flow-specific
    g_flow = p.add_argument_group("Flow Mode Options")
    g_flow.add_argument("--supersat", action="store_true", default=True, help="Increase saturation for flow visualization")
    g_flow.add_argument("--flow-erosion", type=int, default=10, help="Erosion for flow mask")
    g_flow.add_argument("--lower-mag-thresh", type=float, default=1.5, help="Min flow magnitude")
    g_flow.add_argument("--lower-cap", type=float, default=0.0, help="Min speed cap (display)")
    g_flow.add_argument("--upper-cap", type=float, default=500.0, help="Max speed cap (display)")
    g_flow.add_argument("--drift-angle", type=float, default=10.0, help="Drift angle tolerance")
    g_flow.add_argument("--correct-flow", action="store_true", default=False, help="Apply drift correction")
    g_flow.add_argument("--drift-zones", type=int, default=4, choices=[1,2,4,8,16,32,64], help="Processing zones for drift")

    g_flow_vis = p.add_argument_group("Flow Visualization")
    g_flow_vis.add_argument("--no-show-arrows", action="store_true", default=False, help="Hide flow arrows")
    g_flow_vis.add_argument("--no-show-blob", action="store_true", default=False, help="Hide flow blobs")
    g_flow_vis.add_argument("--only-cardinal", action="store_true", default=False, help="Show only cardinal directions")
    g_flow_vis.add_argument("--show-correction", action="store_true", default=False, help="Visualize correction vectors")
    g_flow_vis.add_argument("--hide-flow", action="store_true", default=False, help="Hide flow overlay completely")

    # Export
    g_export = p.add_argument_group("Data Export")
    g_export.add_argument("--export-csv", action="store_true", default=False, help="Export summary to CSV")
    g_export.add_argument("--export-pkl", action="store_true", default=False, help="Export raw data to Pickle")
    g_export.add_argument("--csv-out", help="Custom CSV output path")
    g_export.add_argument("--pickle-out", help="Custom Pickle output path")
    
    # Recording
    g_record = p.add_argument_group("Video Recording (Webcam)")
    g_record.add_argument("--record", action="store_true", default=False, help="Enable video recording")
    g_record.add_argument("--output-video", help="Output video path (auto-generated if not specified)")
    g_record.add_argument("--record-codec", default="libx264", help="Video codec (libx264, libx265, mpeg4)")
    g_record.add_argument("--record-quality", type=int, default=5, help="Encoding quality 1-10 (1=best)")

    # Light Control
    g_light = p.add_argument_group("Light Control")
    g_light.add_argument("--light-port", help="Serial port for light controller (e.g. COM3)")
    g_light.add_argument("--light-baud", type=int, default=115200, help="Baudrate for light controller")

    # Sequence
    p.add_argument("--sequence", help="Path to .seq file for automation")

    return p.parse_args()


def configure_processor(processor: VideoProcessor, args) -> None:
    """Configure the VideoProcessor from CLI arguments."""
    # Common settings
    processor.configure_common(
        calibration=args.calibration,
        fps_ref=args.fps_ref
    )
    
    # Tracking settings
    processor.configure_tracking(
        blur=args.blur,
        thresh_block_size=args.thresh_block_size,
        thresh_bin_thresh=args.thresh_bin_thresh,
        erosion=args.erosion,
        lower_surf_thresh=args.lower_surf_thresh,
        upper_surf_thresh=args.upper_surf_thresh,
        show_trails=args.show_trails,
        show_id=args.show_id,
        show_age=args.show_age,
        show_distance=args.show_distance,
        show_speed=args.show_speed,
        traces_len=args.traces_len,
        max_track_age=args.max_age,
        max_tracking_reset=args.reset_tracking,
        calc_motility=args.motility,
        motility_mode=args.motility_mode,
        motility_thresh=args.motility_thresh,
        angle_tol=args.angle_tol,
        min_trace_angle=args.min_trace_angle,
        show_motile=args.show_motile,
        show_circle=args.show_circle,
        show_blob=args.show_blob,
        show_selection=args.show_selection,
        show_centers=args.show_centers,
        show_boxes=args.show_boxes
    )
    
    # Flow settings
    show_arrows = not args.no_show_arrows
    show_blobs = not args.no_show_blob
    if args.display == "none":
        show_arrows = False
        show_blobs = False
    
    processor.configure_flow(
        supersat=args.supersat,
        flow_erosion=args.flow_erosion,
        lower_mag_thresh=args.lower_mag_thresh,
        lower_cap=args.lower_cap,
        upper_cap=args.upper_cap,
        show_arrows=show_arrows,
        show_blobs=show_blobs,
        only_cardinal=args.only_cardinal,
        drift_angle=args.drift_angle,
        correct_flow=args.correct_flow,
        show_correction=args.show_correction,
        hide_flow=args.hide_flow,
        drift_zones=args.drift_zones
    )


def print_config(args):
    """Print configuration at startup with Rich."""
    table = Table(title="", show_header=True, header_style="bold cyan")
    table.add_column("Parameter", style="dim")
    table.add_column("Value", style="green")
    
    # Source information
    if args.source == "webcam":
        table.add_row("Source", f"[bold magenta]Webcam {args.camera_index}[/bold magenta]")
    else:
        table.add_row("Video", str(args.video))
    
    table.add_row("Processing", f"[bold magenta]{args.processing}[/bold magenta]")
    table.add_row("Display", str(args.display))
    table.add_row("Calibration", f"{args.calibration} px/µm")
    table.add_row("FPS", str(args.fps_ref))
    
    if args.processing == "tracking":
        table.add_row("", "")
        table.add_row("[cyan]Blur[/cyan]", str(args.blur))
        table.add_row("[cyan]Threshold[/cyan]", f"{args.thresh_block_size} / {args.thresh_bin_thresh}")
        table.add_row("[cyan]Surface[/cyan]", f"{args.lower_surf_thresh}-{args.upper_surf_thresh}%")
        table.add_row("[cyan]Trails[/cyan]", f"{'✓' if args.show_trails else '✗'} (len={args.traces_len})")
        table.add_row("[cyan]Motility[/cyan]", f"{'✓' if args.motility else '✗'} ({args.motility_mode}, {args.motility_thresh})")
        
    elif args.processing == "flow":
        table.add_row("", "")
        table.add_row("[cyan]Erosion[/cyan]", str(args.flow_erosion))
        table.add_row("[cyan]Mag thresh[/cyan]", str(args.lower_mag_thresh))
        table.add_row("[cyan]Speed caps[/cyan]", f"{args.lower_cap} - {args.upper_cap} µm/s")
        table.add_row("[cyan]Drift corr.[/cyan]", f"{'✓' if args.correct_flow else '✗'} (zones={args.drift_zones})")
    
    table.add_row("[cyan]Export CSV[/cyan]", f"{'[green]✓[/green]' if args.export_csv else '[red]✗[/red]'}")
    table.add_row("[cyan]Export PKL[/cyan]", f"{'[green]✓[/green]' if args.export_pkl else '[red]✗[/red]'}")
    
    # Recording info
    if args.record:
        table.add_row("[cyan]Recording[/cyan]", f"[green]✓[/green] ({args.record_codec}, quality={args.record_quality})")
    
    console.print(Panel(table, title="[bold blue]MOTILITOMETER[/bold blue]", border_style="blue"))
    console.print()


def run_processing(args):
    """Run video processing with Rich progress display."""
    # Determine source
    if args.source == "webcam":
        source = args.camera_index
        source_type = "webcam"
        
        # Always use unified Webcam Controller
        try:
            import webcam_controller
            console.print(f"[yellow]📷 Using unified Webcam Controller[/yellow]")
        except ImportError as e:
            console.print(f"[red]✗ WebcamController not available: {e}[/red]")
            return
    else:
        source = args.video
        source_type = "file"
    
    # Create processor
    processor = VideoProcessor(
        source, 
        mode=args.processing, 
        source_type=source_type,
        camera_width=getattr(args, 'camera_width', None),
        camera_height=getattr(args, 'camera_height', None),
        media_index=getattr(args, 'media_index', None),
        exposure=getattr(args, 'exposure', None),
        gain=getattr(args, 'gain', None)
    )
    configure_processor(processor, args)
    
    # --- LOGGING & STATE ---
    # Recorder State
    recording_target = False
    recording_active_actual = False
    
    # Message State
    last_seq_msg = "Ready"

    def app_log(msg: str):
        """Update last status message."""
        nonlocal last_seq_msg
        last_seq_msg = msg

    # Helper callbacks
    def req_start_rec(duration=0):
        nonlocal recording_target
        recording_target = True
        app_log(f"REC START ({duration}s)")
    
    def req_stop_rec():
        nonlocal recording_target
        recording_target = False
        app_log("REC STOP")

    # Initialize Light Controller
    light_ctrl = None
    if args.light_port and LightController:
        light_ctrl = LightController(log_cb=app_log)
        if light_ctrl.connect(args.light_port, args.light_baud):
            app_log(f"[green]Light Controller connected on {args.light_port}[/green]")
        else:
            app_log(f"[red]Failed Light Ctrl on {args.light_port}[/red]")
            light_ctrl = None
    elif args.light_port and not LightController:
        console.print("[red]⚠️ light_controller module could not be imported.[/red]")

    # Output paths
    if args.source == "webcam":
        video_dir = os.getcwd()
        base = f"webcam_{args.camera_index}"
    else:
        video_dir = os.path.dirname(os.path.abspath(args.video))
        base, _ = os.path.splitext(os.path.basename(args.video))
    
    csv_out = args.csv_out or os.path.join(video_dir, f"{base}_summary.csv")
    pickle_out = args.pickle_out or os.path.join(video_dir, f"{base}_raw.pkl")
    
    # Open video/webcam
    if not processor.open():
        if args.source == "webcam":
            console.print(f"[red]✗ Cannot open webcam:[/red] {args.camera_index}")
        else:
            console.print(f"[red]✗ Cannot open video:[/red] {args.video}")
        return
    
    # Print camera info
    cam_limits = {}
    if args.source == "webcam":
        cam_info = processor._cap.get_info()
        console.print(f"[yellow]📷 Camera Open: {cam_info.get('format', 'RGB')} {cam_info['width']}x{cam_info['height']}[/yellow]")
        
        # Fetch limits once
        if hasattr(processor._cap, 'get_parameter_range'):
            exp_range = processor._cap.get_parameter_range('exposure')
            if exp_range: cam_limits['exposure'] = exp_range
            
            gain_range = processor._cap.get_parameter_range('gain')
            if gain_range: cam_limits['gain'] = gain_range

    # Initialize recorder
    recorder = None
    if args.record:
        if getattr(VideoRecorder, 'generate_filename', None):
            out_path = args.output_video or VideoRecorder.generate_filename(prefix=base)
        else:
            import datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = args.output_video or f"{base}_{ts}.mp4"
        
        recorder_path = out_path
    else:
        recorder_path = None

    # Initialize Sequence Processor
    seq_proc = None
    if args.sequence:
        if not SequenceProcessor:
             console.print("[red]⚠️ sequence_processor module missing.[/red]")
        else:
            seq_proc = SequenceProcessor(
                args.sequence,
                light_ctrl,
                req_start_rec,
                req_stop_rec,
                log_cb=app_log
            )
            seq_proc.start()

    # Control state
    active_channel = None
    input_buffer = ""
    
    # Display window
    show = args.display != "none"
    if show:
        window_title = "Webcam Preview" if args.source == "webcam" else "Video Preview"
        if args.record:
            window_title += " [RECORDING]"
        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
    
    total_frames = 0
    recording_started = False
    
    # Process with Rich Live display
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%") if args.source == "file" else TextColumn(""),
        TextColumn("•"),
        TextColumn("[green]{task.fields[fps]:.1f} FPS"),
        TextColumn("•"),
        TextColumn("{task.fields[info]}"),
        TimeElapsedColumn(),
    )
    
    task_id = progress.add_task(
        "[cyan]Processing",
        total=processor.total_frames if args.source == "file" else None,
        fps=0.0,
        info=""
    )
    
    task_seq = progress.add_task(
        "[magenta]Sequence",
        total=100,
        visible=False
    )

    def generate_display():
        """Create the combined layout."""
        if args.source == "webcam":
            # Fetch latest stat
            info = processor._cap.get_info()
            
            # Build stats table
            stats_table = Table.grid(padding=(0, 2))
            stats_table.add_column(style="bold cyan")
            stats_table.add_column(style="white")
            
            stats_table.add_row("Name", str(info.get('name', 'Webcam')))
            stats_table.add_row("Res/Fmt", f"{info.get('width')}x{info.get('height')} {info.get('format')}")
            
            # Exposure
            exp_val = info.get('exposure')
            exp_lim = cam_limits.get('exposure')
            exp_range_str = f"({exp_lim['min']}..{exp_lim['max']})" if exp_lim else ""
            
            if active_channel == 'exposure':
                exp_prefix = "[black on yellow]> Exposure[/]"
                if input_buffer:
                    exp_val_str = f"[bold red]{input_buffer}[/]"
                else:
                    exp_val_str = f"[black on yellow]{exp_val}[/]"
            else:
                exp_prefix = "Exposure"
                exp_val_str = f"{exp_val} {exp_range_str}"
            stats_table.add_row(exp_prefix, exp_val_str)
            
            # Gain
            gain_val = info.get('gain')
            gain_lim = cam_limits.get('gain')
            gain_range_str = f"({gain_lim['min']}..{gain_lim['max']})" if gain_lim else ""
            
            if active_channel == 'gain':
                gain_prefix = "[black on yellow]> Gain[/]"
                if input_buffer:
                    gain_val_str = f"[bold red]{input_buffer}[/]"
                else:
                    gain_val_str = f"[black on yellow]{gain_val}[/]"
            else:
                gain_prefix = "Gain"
                gain_val_str = f"{gain_val} {gain_range_str}"
            stats_table.add_row(gain_prefix, gain_val_str)
            
            # Shortcuts Legend
            stats_table.add_row("", "")
            stats_table.add_row("[bold]Controls[/bold]", "")
            stats_table.add_row("Select", "[yellow]e, g[/yellow]")
            stats_table.add_row("Adjust", "[yellow]↑/↓ or Type[/yellow]")
            
            cam_panel = Panel(stats_table, title="[bold blue]Camera Parameters[/bold blue]", border_style="blue")
            
            # Light Panel
            if light_ctrl and light_ctrl.is_connected:
                light_state = light_ctrl.get_state()
                light_table = Table.grid(padding=(0, 2))
                light_table.add_column(style="bold magenta")
                light_table.add_column(style="white")
                
                light_table.add_row("[bold]Light[/bold]", "Val")
                
                channels = [('r', 'Red'), ('g', 'Green (G)'), ('b', 'Blue'), ('w', 'White'), ('ir', 'IR')]
                
                for ch_key, ch_name in channels:
                    # Map 'Green (G)' back to 'g' key for lookup
                    lookup_key = 'g' if ch_key == 'g' else ch_key
                    val = light_state.get(lookup_key, 0)
                    
                    # Highlight if active
                    # Note: we use 'green' as internal active key for Green light to differentiate from 'gain'
                    is_active = False
                    if ch_key == 'g' and active_channel == 'light_g': is_active = True
                    elif active_channel == lookup_key: is_active = True
                    
                    if is_active:
                        prefix = f"[black on yellow]> {ch_name}[/]"
                        value_str = f"[black on yellow]{val}[/]"
                        if input_buffer:
                            value_str = f"[bold red]{input_buffer}[/]"
                    else:
                        prefix = ch_name
                        value_str = str(val)
                        
                    light_table.add_row(prefix, value_str)
                
                footer = "[dim]Select: r,G,b,w,i[/dim]"
                
                l_panel = Panel(
                    Group(light_table, footer),
                    title="[bold magenta]💡 Light[/bold magenta]",
                    border_style="magenta"
                )

                layout = Table.grid(padding=1)
                layout.add_row(cam_panel, l_panel)
                
                if seq_proc:
                    status_content = f"[bold]Status:[/bold] {last_seq_msg}"
                    if seq_proc.is_alive():
                        status = seq_proc.get_status()
                        status_content += f"\n[bold]Seq Cmd:[/bold] {status['cmd']}"
                    layout.add_row(Panel(status_content, border_style="dim white"))
                
                return Group(layout, progress)

            return Group(cam_panel, progress)
        else:
            return progress
    
    def handle_control(key_code, processor, is_arrow=False, arrow_dir=0):
        """
        Handle unified controls.
        key_code: char or int code
        is_arrow: bool
        arrow_dir: -1 (Down/Left), 1 (Up/Right)
        """
        nonlocal active_channel, input_buffer
        
        key_char = ''
        if isinstance(key_code, str):
            key_char = key_code
        elif isinstance(key_code, int):
            try:
                key_char = chr(key_code)
            except:
                pass

        if key_char == 'e':
            active_channel = 'exposure'
            input_buffer = ""
            return
        if key_char == 'g':
            active_channel = 'gain'
            input_buffer = ""
            return
            
        # Light Keys (if connected)
        if light_ctrl and light_ctrl.is_connected:
            if key_char == 'G': # Shift+g for Green
                active_channel = 'light_g' # Special internal key
                input_buffer = ""
                return
            if key_char.lower() in ['r', 'b', 'w', 'i']:
                active_channel = key_char.lower()
                if active_channel == 'i': active_channel = 'ir'
                input_buffer = ""
                return

        if active_channel:
            if is_arrow:
                change = arrow_dir
                # Apply Change
                if active_channel == 'exposure':
                    curr = processor._cap.get_exposure()
                    processor._cap.set_exposure(curr + change)
                elif active_channel == 'gain':
                    curr = processor._cap.get_gain()
                    processor._cap.set_gain(curr + change)
                elif light_ctrl:
                    lookup = 'g' if active_channel == 'light_g' else active_channel
                    state = light_ctrl.get_state()
                    curr = state.get(lookup, 0)
                    light_ctrl.set_value(lookup, curr + change)
                return

            # Numeric Entry
            if key_char.isdigit() or key_char == '-':
                if len(input_buffer) < 6: # Safety limit (increased for sign)
                    input_buffer += key_char
                return
                
            if key_char == '\b' or (isinstance(key_code, int) and (key_code == 8 or key_code == 127)):
                input_buffer = input_buffer[:-1]
                return
                
            # Enter -> Commit
            if key_char == '\r' or key_char == '\n':
                if input_buffer:
                    val = int(input_buffer)
                    if active_channel == 'exposure':
                        processor._cap.set_exposure(val)
                    elif active_channel == 'gain':
                        processor._cap.set_gain(val)
                    elif light_ctrl:
                        lookup = 'g' if active_channel == 'light_g' else active_channel
                        light_ctrl.set_value(lookup, val)
                input_buffer = ""
                return
            
            # Esc -> Deselect
            if key_char == '\x1b' or (isinstance(key_code, int) and key_code == 27):
                active_channel = None
                input_buffer = ""
                return

    proc_start_time = time.time()
    with Live(generate_display(), refresh_per_second=10) as live:
        try:
            for frame_idx, overlay, results in processor.process(display_mode=args.display):
                
                # Update progress
                motility = results.get("motility", 100.0)
                rec_status = f"[REC {recorder.frame_count}] " if recording_started else ""
                info_text = f"{rec_status}Motility: {motility:.1f}%" if args.motility else f"{rec_status}Frame {frame_idx}"
                
                if args.source == "file":
                    progress.update(task_id, advance=1, fps=results.get("fps", 0.0), info=info_text)
                else:
                    # For webcam, manually update completed count
                    progress.update(task_id, completed=frame_idx, fps=results.get("fps", 0.0), info=info_text)
                
                # Update Live display content (essential for showing changing params)
                live.update(generate_display())

                # Display
                if show:
                    if args.record:
                        window_title_updated = f"Webcam Preview [RECORDING - {recorder.frame_count} frames]" if args.source == "webcam" else f"Video Preview [RECORDING - {recorder.frame_count} frames]"
                        cv2.setWindowTitle(window_title, window_title_updated)
                    cv2.imshow(window_title, overlay)
                    
                total_frames += 1
                # Update Sequence Progress
                if seq_proc and seq_proc.is_alive():
                    s = seq_proc.get_status()
                    # s['progress'] is 0.0 to 1.0
                    progress.update(task_seq, completed=s['progress']*100, visible=True, description=f"[magenta]Seq: {s['cmd']}")
                elif seq_proc and not seq_proc.is_alive() and not getattr(seq_proc, 'has_finished_msg', False):
                     progress.update(task_seq, visible=False)
                     seq_proc.has_finished_msg = True
                
                should_update_ui = (total_frames % 5 == 0)
                
                # --- Recording Logic ---
                if recording_target and not recording_active_actual:
                    # Start recording
                    if recorder is None:
                        if not recorder_path:
                             import datetime
                             ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                             recorder_path = args.output_video or f"{base}_{ts}.mp4"
                             if args.source != "webcam": recorder_path = os.path.join(video_dir, recorder_path)
                        
                        recorder = VideoRecorder(
                            output_path=recorder_path, 
                            fps=args.fps_ref,
                            codec=args.record_codec,
                            quality=args.record_quality
                        )
                        console.print(f"[yellow]Rec Init:[/yellow] [cyan]{recorder_path}[/cyan]")
                        
                    if recorder.start(width=processor._cap.width, height=processor._cap.height):
                         recording_active_actual = True
                         console.print("[red]REC START[/red]")
                    else:
                         console.print("[red] Failed to start recording [/red]")  
                         recording_target = False

                elif not recording_target and recording_active_actual:
                    if recorder:
                        recorder.stop()
                        console.print(f"[green]✓[/green] Saved: [cyan]{recorder.output_path}[/cyan]")
                        # Wipe recorder to force new file next time?
                        # If we keep it, next start() appends or overwrites?
                        # VideoRecorder logic: start() -> _start_writegear -> WriteGear(output) -> overwrites usually!
                        # So we MUST wipe it to force new filename if we want preservation.
                        recorder = None
                        recorder_path = None 
                    recording_active_actual = False
                    console.print("[red]REC STOP[/red]")

                if recording_active_actual:
                    recorder.write_frame(frame)
                
                cv2.waitKey(1)

                # Handle terminal key presses
                if msvcrt.kbhit():
                    try:
                        t_key = msvcrt.getwch()
                        should_update_ui = True
                        
                        is_arrow = False
                        arrow_dir = 0
                        
                        if t_key == '\x00' or t_key == '\xe0':
                            code = msvcrt.getwch()
                            if code == 'H': # Up 72
                                is_arrow = True
                                arrow_dir = 1
                            elif code == 'P': # Down 80
                                is_arrow = True
                                arrow_dir = -1
                        elif t_key == 'w':
                            is_arrow = True
                            arrow_dir = 1
                        elif t_key == 's':
                            is_arrow = True
                            arrow_dir = -1
                        
                        if t_key == args.quit_key:
                            break
                        
                        if args.source == "webcam":
                            handle_control(t_key, processor, is_arrow, arrow_dir)
                    except:
                        pass
                
                if should_update_ui:
                    live.update(generate_display())
        
        finally:
            if show:
                cv2.destroyAllWindows()
            processor.close()
            if light_ctrl:
                light_ctrl.close()
            
            if recorder and recording_started:
                recorder.stop()
                console.print(f"[green]✓[/green] Recording saved: [cyan]{recorder.get_info()['output_path']}[/cyan]")
                console.print(f"   Recorded {recorder.frame_count} frames ({recorder.duration:.2f}s)")
    
    proc_duration = time.time() - proc_start_time
    video_duration = total_frames / processor.fps if processor.fps > 0 else 0
    avg_proc_fps = total_frames / proc_duration if proc_duration > 0 else 0
    
    console.print()
    console.print(Panel(
        f"[green]✓[/green] Processed [bold]{total_frames}[/bold] frames in [bold]{proc_duration:.2f}s[/bold] (Video duration: {video_duration:.2f}s)\n"
        f"[cyan]Processing Speed:[/cyan] [bold]{avg_proc_fps:.2f} FPS[/bold]",
        title="[bold green]Processing Complete[/bold green]",
        border_style="green"
    ))
    
    if args.export_csv:
        processor.export_csv(csv_out)
        console.print(f"[green]✓[/green] CSV saved to [cyan]{csv_out}[/cyan]")
    
    if args.export_pkl:
        processor.export_pickle(pickle_out)
        console.print(f"[green]✓[/green] Pickle saved to [cyan]{pickle_out}[/cyan]")


def main():
    """Main entry point."""
    args = parse_args()
    print_config(args)
    run_processing(args)


if __name__ == "__main__":
    main()
