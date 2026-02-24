#!/usr/bin/env python3
"""
NetPulse — Modern Network Diagnostic Visualizer
A beautiful CLI tool for real-time ping monitoring and traceroute visualization.
Zero external dependencies — pure Python 3.10+ with ANSI/Unicode graphics.
"""

import argparse
import asyncio
import math
import os
import platform
import re
import shutil
import signal
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

# ─── ANSI Color & Style Engine ───────────────────────────────────────────────

class Color:
    """ANSI 256-color and truecolor support."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    ULINE   = "\033[4m"
    BLINK   = "\033[5m"
    REVERSE = "\033[7m"
    HIDDEN  = "\033[8m"
    STRIKE  = "\033[9m"

    # Foreground
    BLACK   = "\033[30m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    WHITE   = "\033[37m"

    # Bright foreground
    BRIGHT_BLACK   = "\033[90m"
    BRIGHT_RED     = "\033[91m"
    BRIGHT_GREEN   = "\033[92m"
    BRIGHT_YELLOW  = "\033[93m"
    BRIGHT_BLUE    = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN    = "\033[96m"
    BRIGHT_WHITE   = "\033[97m"

    # Background
    BG_BLACK   = "\033[40m"
    BG_RED     = "\033[41m"
    BG_GREEN   = "\033[42m"
    BG_YELLOW  = "\033[43m"
    BG_BLUE    = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN    = "\033[46m"
    BG_WHITE   = "\033[47m"

    @staticmethod
    def rgb(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    @staticmethod
    def bg_rgb(r: int, g: int, b: int) -> str:
        return f"\033[48;2;{r};{g};{b}m"

    @staticmethod
    def c256(n: int) -> str:
        return f"\033[38;5;{n}m"

    @staticmethod
    def bg_c256(n: int) -> str:
        return f"\033[48;5;{n}m"


# ─── Theme ───────────────────────────────────────────────────────────────────

class Theme:
    """Color theme for the application."""
    BRAND       = Color.rgb(0, 200, 255)      # Cyan-ish brand color
    BRAND_DIM   = Color.rgb(0, 120, 160)
    SUCCESS     = Color.rgb(80, 250, 123)      # Green
    WARNING     = Color.rgb(255, 183, 77)      # Amber
    DANGER      = Color.rgb(255, 85, 85)       # Red
    INFO        = Color.rgb(139, 180, 255)     # Soft blue
    MUTED       = Color.rgb(108, 117, 125)     # Gray
    TEXT        = Color.rgb(224, 224, 224)      # Light gray
    TEXT_BRIGHT = Color.rgb(255, 255, 255)
    ACCENT1     = Color.rgb(189, 147, 249)     # Purple
    ACCENT2     = Color.rgb(255, 121, 198)     # Pink
    ACCENT3     = Color.rgb(241, 250, 140)     # Yellow-green
    BG_PANEL    = Color.bg_rgb(30, 30, 46)     # Dark panel
    BG_HEADER   = Color.bg_rgb(20, 20, 35)     # Darker header
    BG_GRAPH    = Color.bg_rgb(25, 25, 40)

    # Gradient for latency coloring (green -> yellow -> red)
    @staticmethod
    def latency_color(ms: float, threshold: float = 100.0) -> str:
        ratio = min(ms / threshold, 1.0)
        if ratio < 0.5:
            # Green -> Yellow
            t = ratio * 2
            r = int(80 + 175 * t)
            g = int(250 - 67 * t)
            b = int(123 - 123 * t)
        else:
            # Yellow -> Red
            t = (ratio - 0.5) * 2
            r = 255
            g = int(183 - 98 * t)
            b = int(0 + 85 * t)
        return Color.rgb(r, g, b)

    @staticmethod
    def latency_bg(ms: float, threshold: float = 100.0) -> str:
        ratio = min(ms / threshold, 1.0)
        if ratio < 0.5:
            t = ratio * 2
            r = int(20 + 30 * t)
            g = int(40 - 10 * t)
            b = int(20 - 10 * t)
        else:
            t = (ratio - 0.5) * 2
            r = int(50 + 30 * t)
            g = int(30 - 20 * t)
            b = int(10)
        return Color.bg_rgb(r, g, b)


# ─── Unicode Box Drawing ────────────────────────────────────────────────────

class Box:
    """Unicode box-drawing characters."""
    # Rounded corners
    TL = "╭"
    TR = "╮"
    BL = "╰"
    BR = "╯"
    H  = "─"
    V  = "│"
    # T-junctions
    TJ = "┬"
    BJ = "┴"
    LJ = "├"
    RJ = "┤"
    X  = "┼"
    # Double
    DH = "═"
    DV = "║"
    DTL = "╔"
    DTR = "╗"
    DBL = "╚"
    DBR = "╝"
    # Block elements
    FULL    = "█"
    DARK    = "▓"
    MEDIUM  = "▒"
    LIGHT   = "░"
    # Braille (for high-res graphs)
    BRAILLE_BASE = 0x2800
    # Sparkline blocks
    SPARK = " ▁▂▃▄▅▆▇█"
    # Dots
    DOT = "●"
    CIRCLE = "○"
    DIAMOND = "◆"
    TRIANGLE = "▲"
    ARROW_R = "▶"
    ARROW_L = "◀"
    ARROW_U = "▲"
    ARROW_D = "▼"
    CHECK = "✓"
    CROSS = "✗"
    STAR = "★"
    PULSE = "⚡"
    GLOBE = "🌐"
    SIGNAL = "📶"


# ─── Braille Graph Renderer ─────────────────────────────────────────────────

class BrailleGraph:
    """
    Renders data as a high-resolution braille-dot graph.
    Each character cell = 2x4 dot matrix (2 wide, 4 tall).
    """
    # Braille dot positions: each bit maps to a position
    # ⠁ ⠈    bit 0,3
    # ⠂ ⠐    bit 1,4
    # ⠄ ⠠    bit 2,5
    # ⡀ ⢀    bit 6,7
    DOT_MAP = [
        (0, 0, 0x01), (1, 0, 0x08),
        (0, 1, 0x02), (1, 1, 0x10),
        (0, 2, 0x04), (1, 2, 0x20),
        (0, 3, 0x40), (1, 3, 0x80),
    ]

    @staticmethod
    def render(data: list[float], width: int, height: int,
               min_val: Optional[float] = None, max_val: Optional[float] = None,
               color: str = Theme.BRAND) -> list[str]:
        if not data:
            return [" " * width] * height

        dot_w = width * 2
        dot_h = height * 4

        # Auto-range
        valid = [v for v in data if v is not None and v >= 0]
        if not valid:
            return [" " * width] * height

        if min_val is None:
            min_val = 0
        if max_val is None:
            max_val = max(valid) * 1.1 if valid else 1.0
        if max_val == min_val:
            max_val = min_val + 1

        # Create dot grid
        grid = [[False] * dot_h for _ in range(dot_w)]

        # Map data points to dot positions
        n = len(data)
        for i, val in enumerate(data):
            if val is None or val < 0:
                continue
            x = int(i * (dot_w - 1) / max(n - 1, 1))
            y = int((1.0 - (val - min_val) / (max_val - min_val)) * (dot_h - 1))
            y = max(0, min(dot_h - 1, y))
            x = max(0, min(dot_w - 1, x))
            grid[x][y] = True

            # Connect to previous point for line effect
            if i > 0 and data[i - 1] is not None and data[i - 1] >= 0:
                prev_x = int((i - 1) * (dot_w - 1) / max(n - 1, 1))
                prev_y = int((1.0 - (data[i - 1] - min_val) / (max_val - min_val)) * (dot_h - 1))
                prev_y = max(0, min(dot_h - 1, prev_y))
                # Bresenham-like line
                dx = abs(x - prev_x)
                dy = abs(y - prev_y)
                sx = 1 if x > prev_x else -1
                sy = 1 if y > prev_y else -1
                cx, cy = prev_x, prev_y
                err = dx - dy
                steps = 0
                while steps < 500:
                    steps += 1
                    gx = max(0, min(dot_w - 1, cx))
                    gy = max(0, min(dot_h - 1, cy))
                    grid[gx][gy] = True
                    if cx == x and cy == y:
                        break
                    e2 = 2 * err
                    if e2 > -dy:
                        err -= dy
                        cx += sx
                    if e2 < dx:
                        err += dx
                        cy += sy

        # Convert grid to braille characters
        lines = []
        for row in range(height):
            line = ""
            for col in range(width):
                code = 0x2800
                for dx, dy, bit in BrailleGraph.DOT_MAP:
                    gx = col * 2 + dx
                    gy = row * 4 + dy
                    if 0 <= gx < dot_w and 0 <= gy < dot_h and grid[gx][gy]:
                        code |= bit
                line += chr(code)
            lines.append(f"{color}{line}{Color.RESET}")

        return lines


# ─── Sparkline Renderer ─────────────────────────────────────────────────────

class Sparkline:
    """Compact inline sparkline using block characters."""
    CHARS = " ▁▂▃▄▅▆▇█"

    @staticmethod
    def render(data: list[float], width: Optional[int] = None,
               color_func=None) -> str:
        if not data:
            return ""
        valid = [v for v in data if v is not None and v >= 0]
        if not valid:
            return " " * (width or len(data))

        mn, mx = min(valid), max(valid)
        if mn == mx:
            mx = mn + 1

        if width and len(data) > width:
            # Downsample
            chunk = len(data) / width
            sampled = []
            for i in range(width):
                start = int(i * chunk)
                end = int((i + 1) * chunk)
                vals = [v for v in data[start:end] if v is not None and v >= 0]
                sampled.append(statistics.mean(vals) if vals else -1)
            data = sampled

        result = ""
        for v in data:
            if v is None or v < 0:
                result += " "
                continue
            idx = int((v - mn) / (mx - mn) * 8)
            idx = max(0, min(8, idx))
            char = Sparkline.CHARS[idx]
            if color_func:
                result += f"{color_func(v)}{char}{Color.RESET}"
            else:
                result += char
        return result


# ─── Bar Chart Renderer ─────────────────────────────────────────────────────

class HBar:
    """Horizontal bar chart for traceroute hops."""
    @staticmethod
    def render(value: float, max_value: float, width: int,
               color: str = Theme.BRAND, bg: str = Theme.MUTED) -> str:
        if max_value <= 0:
            return " " * width
        ratio = min(value / max_value, 1.0)
        filled = int(ratio * width)
        empty = width - filled
        bar = f"{color}{'█' * filled}{bg}{'░' * empty}{Color.RESET}"
        return bar


# ─── Terminal Utilities ──────────────────────────────────────────────────────

class Term:
    """Terminal control utilities."""
    @staticmethod
    def size() -> tuple[int, int]:
        s = shutil.get_terminal_size((80, 24))
        return s.columns, s.lines

    @staticmethod
    def clear():
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    @staticmethod
    def move(x: int, y: int):
        sys.stdout.write(f"\033[{y};{x}H")

    @staticmethod
    def hide_cursor():
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    @staticmethod
    def show_cursor():
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    @staticmethod
    def write(text: str):
        sys.stdout.write(text)

    @staticmethod
    def flush():
        sys.stdout.flush()

    @staticmethod
    def strip_ansi(text: str) -> str:
        return re.sub(r'\033\[[0-9;]*m', '', text)

    @staticmethod
    def visible_len(text: str) -> int:
        return len(Term.strip_ansi(text))


# ─── Panel / Frame Renderer ─────────────────────────────────────────────────

class Panel:
    """Renders bordered panels with titles."""
    @staticmethod
    def render(content: list[str], width: int, title: str = "",
               title_color: str = Theme.BRAND,
               border_color: str = Theme.MUTED,
               padding: int = 1) -> list[str]:
        inner_w = width - 2  # borders
        lines = []

        # Top border
        if title:
            title_display = f" {title_color}{Color.BOLD}{title}{Color.RESET}{border_color} "
            title_vis_len = len(title) + 2
            remaining = inner_w - title_vis_len
            left_pad = 2
            right_pad = max(0, remaining - left_pad)
            top = f"{border_color}{Box.TL}{Box.H * left_pad}{title_display}{Box.H * right_pad}{border_color}{Box.TR}{Color.RESET}"
        else:
            top = f"{border_color}{Box.TL}{Box.H * inner_w}{Box.TR}{Color.RESET}"
        lines.append(top)

        # Content lines
        for line in content:
            vis_len = Term.visible_len(line)
            pad = max(0, inner_w - vis_len)
            lines.append(f"{border_color}{Box.V}{Color.RESET}{line}{' ' * pad}{border_color}{Box.V}{Color.RESET}")

        # Bottom border
        bottom = f"{border_color}{Box.BL}{Box.H * inner_w}{Box.BR}{Color.RESET}"
        lines.append(bottom)

        return lines


# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class PingResult:
    seq: int
    host: str
    ip: str
    ttl: int
    time_ms: float
    timestamp: float
    timeout: bool = False
    error: Optional[str] = None


@dataclass
class TracerouteHop:
    hop_num: int
    ip: str
    hostname: str
    rtt_ms: list[float]
    timeout: bool = False


@dataclass
class PingStats:
    sent: int = 0
    received: int = 0
    lost: int = 0
    times: list[float] = field(default_factory=list)
    history: deque = field(default_factory=lambda: deque(maxlen=2000))

    @property
    def loss_pct(self) -> float:
        return (self.lost / self.sent * 100) if self.sent > 0 else 0.0

    @property
    def avg(self) -> float:
        return statistics.mean(self.times) if self.times else 0.0

    @property
    def min(self) -> float:
        return min(self.times) if self.times else 0.0

    @property
    def max(self) -> float:
        return max(self.times) if self.times else 0.0

    @property
    def stddev(self) -> float:
        return statistics.stdev(self.times) if len(self.times) > 1 else 0.0

    @property
    def median(self) -> float:
        return statistics.median(self.times) if self.times else 0.0

    @property
    def jitter(self) -> float:
        if len(self.times) < 2:
            return 0.0
        diffs = [abs(self.times[i] - self.times[i-1]) for i in range(1, len(self.times))]
        return statistics.mean(diffs)

    @property
    def p95(self) -> float:
        if not self.times:
            return 0.0
        sorted_t = sorted(self.times)
        idx = int(len(sorted_t) * 0.95)
        return sorted_t[min(idx, len(sorted_t) - 1)]


# ─── Platform-Aware Ping Parser ─────────────────────────────────────────────

class PingParser:
    """Cross-platform ping output parser."""
    IS_WINDOWS = platform.system() == "Windows"
    IS_MACOS = platform.system() == "Darwin"

    @staticmethod
    def build_command(host: str, count: int = 1, timeout: int = 2,
                      interval: float = 0.2, ipv6: bool = False) -> list[str]:
        ping_cmd = "ping6" if ipv6 and not PingParser.IS_WINDOWS else "ping"
        if ipv6 and not PingParser.IS_MACOS:
            ping_cmd = "ping"

        if PingParser.IS_WINDOWS:
            cmd = [ping_cmd, "-n", str(count), "-w", str(timeout * 1000)]
            if ipv6:
                cmd.append("-6")
        else:
            cmd = [ping_cmd, "-c", str(count)]
            if PingParser.IS_MACOS:
                cmd += ["-W", str(timeout * 1000)]
            else:
                cmd += ["-W", str(timeout)]
                cmd += ["-i", str(interval)]
            if ipv6 and not PingParser.IS_MACOS:
                cmd.append("-6")
        cmd.append(host)
        return cmd

    @staticmethod
    def parse_line(line: str, seq: int, host: str) -> Optional[PingResult]:
        """Parse a single ping response line."""
        line = line.strip()
        if not line:
            return None

        # Check for timeout
        timeout_patterns = [
            "request timed out", "request timeout", "100% packet loss",
            "unreachable", "time out", "timed out"
        ]
        if any(p in line.lower() for p in timeout_patterns):
            return PingResult(
                seq=seq, host=host, ip="", ttl=0,
                time_ms=-1, timestamp=time.time(), timeout=True
            )

        # Try to extract time
        time_match = re.search(r'time[=<]\s*([\d.]+)\s*ms', line, re.IGNORECASE)
        ttl_match = re.search(r'ttl[=:]\s*(\d+)', line, re.IGNORECASE)
        ip_match = re.search(r'from\s+([\d.]+|[a-fA-F0-9:]+)', line)

        if time_match:
            return PingResult(
                seq=seq,
                host=host,
                ip=ip_match.group(1) if ip_match else host,
                ttl=int(ttl_match.group(1)) if ttl_match else 0,
                time_ms=float(time_match.group(1)),
                timestamp=time.time(),
            )
        return None


# ─── Traceroute Parser ───────────────────────────────────────────────────────

class TracerouteRunner:
    """Cross-platform traceroute execution and parsing."""
    IS_WINDOWS = platform.system() == "Windows"

    @staticmethod
    def build_command(host: str, max_hops: int = 30) -> list[str]:
        if TracerouteRunner.IS_WINDOWS:
            return ["tracert", "-d", "-h", str(max_hops), host]
        else:
            return ["traceroute", "-n", "-m", str(max_hops), "-q", "3", host]

    @staticmethod
    def parse_line(line: str) -> Optional[TracerouteHop]:
        line = line.strip()
        if not line or line.startswith("traceroute") or line.startswith("Tracing"):
            return None

        # Match hop number at start
        hop_match = re.match(r'^\s*(\d+)\s+', line)
        if not hop_match:
            return None

        hop_num = int(hop_match.group(1))
        rest = line[hop_match.end():]

        # Check for all timeouts
        if rest.strip() == "* * *":
            return TracerouteHop(hop_num=hop_num, ip="*", hostname="*",
                               rtt_ms=[], timeout=True)

        # Extract IP and RTTs
        ip_match = re.search(r'([\d.]+|[a-fA-F0-9:]+(?:%\S+)?)', rest)
        ip = ip_match.group(1) if ip_match else "*"

        rtts = [float(m) for m in re.findall(r'([\d.]+)\s*ms', rest)]

        # Try hostname resolution
        hostname = ip
        if ip != "*":
            try:
                hostname = socket.gethostbyaddr(ip)[0]
            except (socket.herror, socket.gaierror, OSError):
                hostname = ip

        return TracerouteHop(
            hop_num=hop_num, ip=ip, hostname=hostname,
            rtt_ms=rtts, timeout=len(rtts) == 0
        )


# ─── ASCII Art Banner ────────────────────────────────────────────────────────

BANNER = f"""
{Theme.BRAND}{Color.BOLD}
    ╔╗╔┌─┐┌┬┐╔═╗┬ ┬┬  ┌─┐┌─┐
    ║║║├┤  │ ╠═╝│ ││  └─┐├┤
    ╝╚╝└─┘ ┴ ╩  └─┘┴─┘└─┘└─┘{Color.RESET}
{Theme.MUTED}    ─── Network Diagnostic Visualizer ───{Color.RESET}
"""

BANNER_SMALL = (
    f"{Theme.BRAND}{Color.BOLD} {Box.PULSE} NetPulse{Color.RESET}"
    f" {Theme.MUTED}│ Network Diagnostic Visualizer{Color.RESET}"
)


# ─── Vibe Engine — Background Beat Generator ────────────────────────────────

class VibeEngine:
    """
    Generates a trap-inspired instrumental beat as a WAV file using pure
    stdlib (struct + wave). Plays it in the background via platform audio.
    Inspired by that 0-to-100 rising energy — 808 bass, hi-hats, snare.
    """

    SAMPLE_RATE = 44100

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._tmpfile: Optional[str] = None
        self._playing = False

    # ── Synthesis primitives ────────────────────────────────────────

    @staticmethod
    def _sine(freq: float, duration: float, volume: float = 0.5,
              sr: int = 44100) -> list[float]:
        """Pure sine wave."""
        n = int(sr * duration)
        return [volume * math.sin(2 * math.pi * freq * i / sr) for i in range(n)]

    @staticmethod
    def _square(freq: float, duration: float, volume: float = 0.3,
                sr: int = 44100) -> list[float]:
        """Square wave for gritty synth."""
        n = int(sr * duration)
        samples = []
        for i in range(n):
            t = (freq * i / sr) % 1.0
            samples.append(volume if t < 0.5 else -volume)
        return samples

    @staticmethod
    def _noise(duration: float, volume: float = 0.15,
               sr: int = 44100) -> list[float]:
        """Pseudo-random noise for hi-hats/snare using deterministic LCG."""
        n = int(sr * duration)
        samples = []
        seed = 12345
        for _ in range(n):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            val = (seed / 0x7FFFFFFF) * 2 - 1
            samples.append(val * volume)
        return samples

    @staticmethod
    def _envelope(samples: list[float], attack: float = 0.005,
                  decay: float = 0.0, sustain: float = 1.0,
                  release: float = 0.05, sr: int = 44100) -> list[float]:
        """ADSR envelope."""
        n = len(samples)
        a_n = int(attack * sr)
        d_n = int(decay * sr)
        r_n = int(release * sr)
        s_n = max(0, n - a_n - d_n - r_n)

        env = []
        for i in range(min(a_n, n)):
            env.append(i / max(a_n, 1))
        for i in range(min(d_n, max(0, n - a_n))):
            env.append(1.0 - (1.0 - sustain) * i / max(d_n, 1))
        for _ in range(min(s_n, max(0, n - a_n - d_n))):
            env.append(sustain)
        for i in range(min(r_n, max(0, n - a_n - d_n - s_n))):
            env.append(sustain * (1.0 - i / max(r_n, 1)))

        # Pad if needed
        while len(env) < n:
            env.append(0.0)

        return [s * e for s, e in zip(samples, env[:n])]

    @staticmethod
    def _mix(base: list[float], overlay: list[float],
             offset: int = 0) -> list[float]:
        """Mix overlay into base at sample offset."""
        needed = offset + len(overlay)
        if needed > len(base):
            base.extend([0.0] * (needed - len(base)))
        for i, s in enumerate(overlay):
            base[offset + i] = base[offset + i] + s
        return base

    # ── Instrument builders ─────────────────────────────────────────

    def _kick(self, duration: float = 0.25) -> list[float]:
        """808-style kick — pitch-swept sine."""
        sr = self.SAMPLE_RATE
        n = int(sr * duration)
        samples = []
        for i in range(n):
            t = i / sr
            # Pitch sweeps from 150Hz down to 45Hz
            freq = 45 + 105 * math.exp(-t * 20)
            val = 0.7 * math.sin(2 * math.pi * freq * t)
            samples.append(val)
        return self._envelope(samples, attack=0.002, release=0.1, sr=sr)

    def _snare(self, duration: float = 0.15) -> list[float]:
        """Snare — sine body + noise."""
        sr = self.SAMPLE_RATE
        body = self._sine(200, duration, 0.3, sr)
        body = self._envelope(body, attack=0.001, release=0.08, sr=sr)
        nz = self._noise(duration, 0.35, sr)
        nz = self._envelope(nz, attack=0.001, release=0.06, sr=sr)
        return [a + b for a, b in zip(body, nz)]

    def _hihat(self, duration: float = 0.04) -> list[float]:
        """Closed hi-hat — short noise burst."""
        sr = self.SAMPLE_RATE
        nz = self._noise(duration, 0.2, sr)
        return self._envelope(nz, attack=0.001, release=0.02, sr=sr)

    def _hihat_open(self, duration: float = 0.12) -> list[float]:
        """Open hi-hat — longer noise."""
        sr = self.SAMPLE_RATE
        nz = self._noise(duration, 0.15, sr)
        return self._envelope(nz, attack=0.001, release=0.08, sr=sr)

    def _bass_808(self, freq: float, duration: float = 0.3) -> list[float]:
        """808 bass note — low sine with bite."""
        sr = self.SAMPLE_RATE
        s = self._sine(freq, duration, 0.5, sr)
        # Add sub-harmonic
        sub = self._sine(freq / 2, duration, 0.2, sr)
        mixed = [a + b for a, b in zip(s, sub)]
        return self._envelope(mixed, attack=0.005, release=0.1, sr=sr)

    def _synth_stab(self, freq: float, duration: float = 0.15) -> list[float]:
        """Short synth stab for melody."""
        sr = self.SAMPLE_RATE
        s1 = self._square(freq, duration, 0.12, sr)
        s2 = self._sine(freq * 2, duration, 0.06, sr)
        mixed = [a + b for a, b in zip(s1, s2)]
        return self._envelope(mixed, attack=0.005, decay=0.02,
                             sustain=0.6, release=0.05, sr=sr)

    # ── Beat composition ────────────────────────────────────────────

    def generate_beat(self, bars: int = 4, bpm: int = 140) -> list[float]:
        """
        Generate a trap-inspired beat.
        4 bars of 4/4 at 140 BPM with rising energy (0-to-100 vibe).
        """
        sr = self.SAMPLE_RATE
        beat_dur = 60.0 / bpm             # duration of 1 beat
        step = beat_dur / 4               # 16th note
        bar_dur = beat_dur * 4            # 1 bar
        total_dur = bar_dur * bars
        total_samples = int(total_dur * sr)

        track = [0.0] * total_samples

        def at(bar: int, beat: float) -> int:
            """Convert bar + beat position to sample offset."""
            t = bar * bar_dur + beat * beat_dur
            return int(t * sr)

        # ── Bar 1: Sparse — kick + light hats ──────────────────
        # Kick on 1 and 3
        self._mix(track, self._kick(), at(0, 0))
        self._mix(track, self._kick(), at(0, 2))
        # Hi-hats on every 8th
        for i in range(8):
            self._mix(track, self._hihat(), at(0, i * 0.5))

        # ── Bar 2: Add snare + bass ────────────────────────────
        self._mix(track, self._kick(), at(1, 0))
        self._mix(track, self._kick(), at(1, 2))
        self._mix(track, self._snare(), at(1, 1))
        self._mix(track, self._snare(), at(1, 3))
        # Bass notes (E1, G1)
        self._mix(track, self._bass_808(41.2, 0.4), at(1, 0))
        self._mix(track, self._bass_808(49.0, 0.3), at(1, 2))
        # Hats — 16ths
        for i in range(16):
            vol_hat = self._hihat() if i % 2 == 0 else self._hihat(0.03)
            self._mix(track, vol_hat, at(1, i * 0.25))

        # ── Bar 3: Rising — add synth stabs ───────────────────
        self._mix(track, self._kick(), at(2, 0))
        self._mix(track, self._kick(0.2), at(2, 1.75))
        self._mix(track, self._kick(), at(2, 2))
        self._mix(track, self._kick(0.2), at(2, 3.5))
        self._mix(track, self._snare(), at(2, 1))
        self._mix(track, self._snare(), at(2, 3))
        # Bass line ascending (E1 -> G1 -> A1 -> B1)
        self._mix(track, self._bass_808(41.2, 0.35), at(2, 0))
        self._mix(track, self._bass_808(49.0, 0.35), at(2, 1))
        self._mix(track, self._bass_808(55.0, 0.35), at(2, 2))
        self._mix(track, self._bass_808(61.7, 0.35), at(2, 3))
        # Synth stabs — minor scale riff
        self._mix(track, self._synth_stab(329.6, 0.12), at(2, 0))     # E4
        self._mix(track, self._synth_stab(392.0, 0.12), at(2, 0.5))   # G4
        self._mix(track, self._synth_stab(440.0, 0.12), at(2, 1))     # A4
        self._mix(track, self._synth_stab(493.9, 0.12), at(2, 2))     # B4
        self._mix(track, self._synth_stab(523.3, 0.12), at(2, 2.5))   # C5
        self._mix(track, self._synth_stab(587.3, 0.12), at(2, 3))     # D5
        # Rapid hats
        for i in range(16):
            h = self._hihat(0.03) if i % 4 != 3 else self._hihat_open()
            self._mix(track, h, at(2, i * 0.25))

        # ── Bar 4: Full energy — double-time hats, heavy kicks ─
        self._mix(track, self._kick(), at(3, 0))
        self._mix(track, self._kick(0.15), at(3, 0.75))
        self._mix(track, self._kick(), at(3, 1.5))
        self._mix(track, self._kick(), at(3, 2))
        self._mix(track, self._kick(0.15), at(3, 2.75))
        self._mix(track, self._kick(), at(3, 3.5))
        self._mix(track, self._snare(), at(3, 1))
        self._mix(track, self._snare(), at(3, 3))
        # Heavy bass
        self._mix(track, self._bass_808(41.2, 0.5), at(3, 0))
        self._mix(track, self._bass_808(55.0, 0.4), at(3, 1.5))
        self._mix(track, self._bass_808(61.7, 0.5), at(3, 2))
        self._mix(track, self._bass_808(73.4, 0.4), at(3, 3))
        # Synth melody — peak energy
        self._mix(track, self._synth_stab(659.3, 0.15), at(3, 0))     # E5
        self._mix(track, self._synth_stab(587.3, 0.12), at(3, 0.5))   # D5
        self._mix(track, self._synth_stab(523.3, 0.15), at(3, 1))     # C5
        self._mix(track, self._synth_stab(587.3, 0.12), at(3, 1.5))   # D5
        self._mix(track, self._synth_stab(659.3, 0.15), at(3, 2))     # E5
        self._mix(track, self._synth_stab(784.0, 0.2), at(3, 2.5))    # G5
        self._mix(track, self._synth_stab(880.0, 0.3), at(3, 3))      # A5 (peak!)
        # 32nd note hi-hat rolls
        for i in range(32):
            h = self._hihat(0.02)
            self._mix(track, h, at(3, i * 0.125))

        # Clip / normalize
        peak = max(abs(s) for s in track) or 1.0
        if peak > 0.95:
            track = [s * 0.95 / peak for s in track]

        return track

    def _write_wav(self, samples: list[float], filepath: str):
        """Write samples to a 16-bit mono WAV file (bulk write)."""
        sr = self.SAMPLE_RATE
        # Convert all samples to 16-bit ints in one shot
        int_samples = [int(max(-1.0, min(1.0, s)) * 32767) for s in samples]
        raw = struct.pack(f'<{len(int_samples)}h', *int_samples)
        with wave.open(filepath, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(raw)

    def _get_play_command(self, filepath: str) -> list[str]:
        """Get platform-specific audio play command."""
        system = platform.system()
        if system == "Darwin":
            return ["afplay", filepath]
        elif system == "Linux":
            # Try common Linux players in order of likelihood
            for player in ["paplay", "aplay", "ffplay"]:
                if shutil.which(player):
                    if player == "ffplay":
                        return [player, "-nodisp", "-autoexit", "-loglevel", "quiet", filepath]
                    return [player, filepath]
            # Fallback — aplay is on most distros
            return ["aplay", "-q", filepath]
        elif system == "Windows":
            # PowerShell can play WAV natively
            ps_cmd = (
                f"(New-Object Media.SoundPlayer '{filepath}').PlaySync()"
            )
            return ["powershell", "-c", ps_cmd]
        return []

    def start(self, loop: bool = True):
        """Generate beat and start playback in background."""
        try:
            # Generate the beat
            beat = self.generate_beat(bars=4, bpm=140)

            if loop:
                # Repeat the beat for a ~1.5 minute loop
                beat = beat * 12

            # Write to temp file
            fd, path = tempfile.mkstemp(suffix=".wav", prefix="netpulse_vibe_")
            os.close(fd)
            self._tmpfile = path
            self._write_wav(beat, path)

            # Get play command
            cmd = self._get_play_command(path)
            if not cmd:
                return

            # Launch in background
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._playing = True

        except Exception:
            # If audio fails, just continue silently — don't break the ping
            self._playing = False

    def stop(self):
        """Stop playback and clean up."""
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

        if self._tmpfile and os.path.exists(self._tmpfile):
            try:
                os.unlink(self._tmpfile)
            except Exception:
                pass
            self._tmpfile = None

        self._playing = False

    @property
    def is_playing(self) -> bool:
        if self._proc and self._proc.poll() is not None:
            self._playing = False
        return self._playing


# ─── Main Ping Monitor Screen ───────────────────────────────────────────────

class PingMonitor:
    """Real-time ping monitoring — stable screen, only values update."""

    SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, host: str, interval: float = 0.5,
                 threshold: float = 100.0, ipv6: bool = False,
                 vibe: bool = False, **kwargs):
        self.host = host
        self.interval = interval
        self.threshold = threshold
        self.ipv6 = ipv6
        self.vibe = vibe
        self.stats = PingStats()
        self.running = False
        self.start_time = 0.0
        self.resolved_ip = ""
        self.frame_count = 0
        self._rows: dict[str, int] = {}
        self._width = 80
        self._vibe_engine: Optional[VibeEngine] = None

    def resolve_host(self) -> str:
        try:
            family = socket.AF_INET6 if self.ipv6 else socket.AF_INET
            infos = socket.getaddrinfo(self.host, None, family)
            if infos:
                self.resolved_ip = infos[0][4][0]
                return self.resolved_ip
        except socket.gaierror:
            pass
        self.resolved_ip = self.host
        return self.host

    def _paint_static(self):
        """Paint the full static layout once. Record row positions."""
        w, _ = Term.size()
        self._width = max(w, 60)
        width = self._width

        Term.clear()
        row = 1

        # Row 1: prompt line (will be updated)
        self._rows["prompt"] = row
        print()
        row += 1

        # Blank line
        print()
        row += 1

        # Banner (3 lines + subtitle + blank)
        print(f"{Theme.BRAND}{Color.BOLD}"
              "    ╔╗╔┌─┐┌┬┐╔═╗┬ ┬┬  ┌─┐┌─┐"
              f"{Color.RESET}")
        row += 1
        print(f"{Theme.BRAND}{Color.BOLD}"
              "    ║║║├┤  │ ╠═╝│ ││  └─┐├┤ "
              f"{Color.RESET}")
        row += 1
        print(f"{Theme.BRAND}{Color.BOLD}"
              "    ╝╚╝└─┘ ┴ ╩  └─┘┴─┘└─┘└─┘"
              f"{Color.RESET}")
        row += 1
        print(f"{Theme.MUTED}    ─── Network Diagnostic Visualizer ───{Color.RESET}")
        row += 1
        print()
        row += 1

        # Session heading (updatable for status)
        self._rows["heading"] = row
        print()
        row += 1

        # Separator
        print(f"  {Theme.MUTED}{'─' * (width - 4)}{Color.RESET}")
        row += 1

        print()
        row += 1

        # Target
        target_line = f"  Target:   {Theme.BRAND}{self.host}{Color.RESET}"
        if self.resolved_ip and self.resolved_ip != self.host:
            target_line += f" ({self.resolved_ip})"
        print(target_line)
        row += 1

        # Duration (updatable)
        self._rows["duration"] = row
        print()
        row += 1

        print()
        row += 1

        # Packets header
        print(f"  {Theme.TEXT_BRIGHT}Packets:{Color.RESET}")
        row += 1

        # Sent (updatable)
        self._rows["sent"] = row
        print()
        row += 1

        # Received (updatable)
        self._rows["received"] = row
        print()
        row += 1

        # Lost (updatable)
        self._rows["lost"] = row
        print()
        row += 1

        print()
        row += 1

        # Latency header
        print(f"  {Theme.TEXT_BRIGHT}Latency:{Color.RESET}")
        row += 1

        # Min (updatable)
        self._rows["min"] = row
        print()
        row += 1

        # Avg (updatable)
        self._rows["avg"] = row
        print()
        row += 1

        # Max (updatable)
        self._rows["max"] = row
        print()
        row += 1

        # P95 (updatable)
        self._rows["p95"] = row
        print()
        row += 1

        # StdDev (updatable)
        self._rows["stddev"] = row
        print()
        row += 1

        # Jitter (updatable)
        self._rows["jitter"] = row
        print()
        row += 1

        print()
        row += 1

        # Latency History label
        print(f"  {Theme.TEXT_BRIGHT}Latency History:{Color.RESET}")
        row += 1

        # Sparkline (updatable)
        self._rows["sparkline"] = row
        print()
        row += 1

        sys.stdout.flush()

    def _write_at(self, row: int, text: str):
        """Write text at a specific row, clearing the line first."""
        sys.stdout.write(f"\033[{row};1H\033[2K{text}")

    def _update_values(self):
        """Update only the changing values in-place."""
        s = self.stats
        width = self._width
        elapsed = time.time() - self.start_time
        elapsed_str = f"{int(elapsed // 3600):02d}:{int((elapsed % 3600) // 60):02d}:{int(elapsed % 60):02d}"
        spin = self.SPINNER[self.frame_count % len(self.SPINNER)]
        loss_c = Theme.SUCCESS if s.loss_pct < 5 else (Theme.WARNING if s.loss_pct < 20 else Theme.DANGER)

        # Prompt
        vibe_indicator = ""
        if self._vibe_engine and self._vibe_engine.is_playing:
            vibe_indicator = f"  {Theme.ACCENT2}♪ VIBE{Color.RESET}"
        self._write_at(self._rows["prompt"],
            f"  {Theme.BRAND}{spin}{Color.RESET} "
            f"{Theme.MUTED}Pinging{Color.RESET} {Theme.TEXT_BRIGHT}{Color.BOLD}{self.host}{Color.RESET}"
            f" {Theme.MUTED}— press{Color.RESET} "
            f"{Theme.TEXT_BRIGHT}{Color.BOLD}q{Color.RESET}"
            f"{Theme.MUTED} to quit{Color.RESET}"
            f"{vibe_indicator}"
        )

        # Heading with status
        if s.loss_pct > 50:
            status = f"{Theme.DANGER}{Box.DOT} HIGH LOSS{Color.RESET}"
        elif s.loss_pct > 10:
            status = f"{Theme.WARNING}{Box.DOT} DEGRADED{Color.RESET}"
        elif s.sent > 0:
            status = f"{Theme.SUCCESS}{Box.DOT} HEALTHY{Color.RESET}"
        else:
            status = f"{Theme.WARNING}{Box.DOT} CONNECTING{Color.RESET}"
        self._write_at(self._rows["heading"],
            f"  {Theme.TEXT_BRIGHT}{Color.BOLD}Live Session{Color.RESET}  {status}")

        # Duration
        self._write_at(self._rows["duration"],
            f"  Duration: {Theme.TEXT}{elapsed_str}{Color.RESET}")

        # Packets
        self._write_at(self._rows["sent"],
            f"    Sent:     {s.sent}")
        self._write_at(self._rows["received"],
            f"    Received: {Theme.SUCCESS}{s.received}{Color.RESET}")
        self._write_at(self._rows["lost"],
            f"    Lost:     {loss_c}{s.lost} ({s.loss_pct:.1f}%){Color.RESET}")

        # Latency
        if s.times:
            self._write_at(self._rows["min"],
                f"    Min:    {Theme.SUCCESS}{s.min:.2f}ms{Color.RESET}")
            self._write_at(self._rows["avg"],
                f"    Avg:    {Theme.latency_color(s.avg, self.threshold)}{s.avg:.2f}ms{Color.RESET}")
            self._write_at(self._rows["max"],
                f"    Max:    {Theme.latency_color(s.max, self.threshold)}{s.max:.2f}ms{Color.RESET}")
            self._write_at(self._rows["p95"],
                f"    P95:    {Theme.INFO}{s.p95:.2f}ms{Color.RESET}")
            self._write_at(self._rows["stddev"],
                f"    StdDev: {s.stddev:.2f}ms")
            self._write_at(self._rows["jitter"],
                f"    Jitter: {s.jitter:.2f}ms")
        else:
            self._write_at(self._rows["min"],
                f"    {Theme.MUTED}Waiting for data...{Color.RESET}")

        # Sparkline
        history_list = list(s.history)
        if history_list:
            spark = Sparkline.render(
                history_list, width - 6,
                color_func=lambda v: Theme.latency_color(v, self.threshold)
            )
            self._write_at(self._rows["sparkline"], f"  {spark}")

        sys.stdout.flush()

    async def ping_loop(self):
        """Continuously ping the host."""
        seq = 0
        while self.running:
            seq += 1
            self.stats.sent += 1

            cmd = PingParser.build_command(
                self.host, count=1, timeout=2,
                interval=self.interval, ipv6=self.ipv6
            )

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    stdout, _ = await asyncio.wait_for(
                        proc.communicate(), timeout=5
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    self.stats.lost += 1
                    self.stats.history.append(-1)
                    await asyncio.sleep(self.interval)
                    continue

                output = stdout.decode("utf-8", errors="replace")
                parsed = None
                for line in output.splitlines():
                    result = PingParser.parse_line(line, seq, self.host)
                    if result:
                        parsed = result
                        break

                if parsed and not parsed.timeout:
                    self.stats.received += 1
                    self.stats.times.append(parsed.time_ms)
                    self.stats.history.append(parsed.time_ms)
                else:
                    self.stats.lost += 1
                    self.stats.history.append(-1)

            except FileNotFoundError:
                self.stats.lost += 1
                self.stats.history.append(-1)
            except Exception:
                self.stats.lost += 1
                self.stats.history.append(-1)

            await asyncio.sleep(self.interval)

    async def render_loop(self):
        """Update only the changing values at ~4fps."""
        while self.running:
            self._update_values()
            self.frame_count += 1
            await asyncio.sleep(0.25)

    async def input_loop(self):
        """Handle keyboard input."""
        import tty
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            while self.running:
                import select
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch in ('q', 'Q', '\x03'):
                        self.running = False
                else:
                    await asyncio.sleep(0.05)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    async def run(self):
        """Main entry point."""
        self.running = True
        self.start_time = time.time()

        # Resolve
        Term.clear()
        print(BANNER)
        print(f"  {Theme.MUTED}Resolving {self.host}...{Color.RESET}")
        ip = self.resolve_host()
        print(f"  {Theme.SUCCESS}{Box.CHECK} Resolved to {ip}{Color.RESET}")

        # Start vibe if requested
        if self.vibe:
            print(f"  {Theme.ACCENT2}♪ Starting vibe...{Color.RESET}")
            self._vibe_engine = VibeEngine()
            self._vibe_engine.start(loop=True)
            if self._vibe_engine.is_playing:
                print(f"  {Theme.ACCENT2}♪ 0 to 100 real quick{Color.RESET}")
            else:
                print(f"  {Theme.MUTED}(audio playback not available){Color.RESET}")

        await asyncio.sleep(0.5)

        # Paint the static layout once
        self._paint_static()

        Term.hide_cursor()
        try:
            await asyncio.gather(
                self.ping_loop(),
                self.render_loop(),
                self.input_loop(),
            )
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            self.running = False
            # Stop music
            if self._vibe_engine:
                self._vibe_engine.stop()
            Term.show_cursor()
            Term.clear()
            self._print_summary()

    def _print_summary(self):
        """Print final static summary on exit."""
        s = self.stats
        width = min(Term.size()[0], 80)
        duration = time.time() - self.start_time
        hours = int(duration // 3600)
        mins = int((duration % 3600) // 60)
        secs = int(duration % 60)
        loss_c = Theme.SUCCESS if s.loss_pct < 5 else Theme.DANGER

        print(BANNER)
        print(f"  {Theme.TEXT_BRIGHT}{Color.BOLD}Session Complete{Color.RESET}")
        print(f"  {Theme.MUTED}{'─' * (width - 4)}{Color.RESET}")
        print()
        print(f"  Target:   {Theme.BRAND}{self.host}{Color.RESET} ({self.resolved_ip})")
        print(f"  Duration: {Theme.TEXT}{hours:02d}:{mins:02d}:{secs:02d}{Color.RESET}")
        print()

        print(f"  {Theme.TEXT_BRIGHT}Packets:{Color.RESET}")
        print(f"    Sent:     {s.sent}")
        print(f"    Received: {Theme.SUCCESS}{s.received}{Color.RESET}")
        print(f"    Lost:     {loss_c}{s.lost} ({s.loss_pct:.1f}%){Color.RESET}")
        print()

        if s.times:
            print(f"  {Theme.TEXT_BRIGHT}Latency:{Color.RESET}")
            print(f"    Min:    {Theme.SUCCESS}{s.min:.2f}ms{Color.RESET}")
            print(f"    Avg:    {Theme.latency_color(s.avg, self.threshold)}{s.avg:.2f}ms{Color.RESET}")
            print(f"    Max:    {Theme.latency_color(s.max, self.threshold)}{s.max:.2f}ms{Color.RESET}")
            print(f"    P95:    {Theme.INFO}{s.p95:.2f}ms{Color.RESET}")
            print(f"    StdDev: {s.stddev:.2f}ms")
            print(f"    Jitter: {s.jitter:.2f}ms")
            print()

            print(f"  {Theme.TEXT_BRIGHT}Latency History:{Color.RESET}")
            spark = Sparkline.render(
                list(s.history), width - 6,
                color_func=lambda v: Theme.latency_color(v, self.threshold)
            )
            print(f"  {spark}")

        print()


# ─── Traceroute Visualizer ───────────────────────────────────────────────────

class TracerouteVisualizer:
    """Beautiful traceroute visualization."""

    def __init__(self, host: str, max_hops: int = 30):
        self.host = host
        self.max_hops = max_hops
        self.hops: list[TracerouteHop] = []

    def _render_hop(self, hop: TracerouteHop, max_rtt: float, width: int) -> list[str]:
        lines = []
        bar_w = max(10, width - 55)

        # Hop number
        hop_str = f"{Theme.BRAND}{Color.BOLD}{hop.hop_num:>3}{Color.RESET}"

        if hop.timeout:
            # Timeout hop
            lines.append(
                f"  {hop_str} {Theme.MUTED}{Box.V}{Color.RESET}  "
                f"{Theme.DANGER}{'*':>15}  {'*':>8}  "
                f"{'░' * bar_w}{Color.RESET}"
            )
        else:
            # Resolve display
            if hop.hostname != hop.ip:
                addr_display = f"{Theme.TEXT_BRIGHT}{hop.hostname}{Color.RESET} {Theme.MUTED}({hop.ip}){Color.RESET}"
            else:
                addr_display = f"{Theme.TEXT}{hop.ip}{Color.RESET}"

            avg_rtt = statistics.mean(hop.rtt_ms) if hop.rtt_ms else 0

            # Latency bar
            color = Theme.latency_color(avg_rtt, 100)
            bar = HBar.render(avg_rtt, max(max_rtt, 1), bar_w, color=color)

            rtt_strs = "/".join(f"{r:.1f}" for r in hop.rtt_ms[:3])

            lines.append(
                f"  {hop_str} {Theme.MUTED}{Box.V}{Color.RESET}  "
                f"{addr_display}"
            )
            lines.append(
                f"      {Theme.MUTED}{Box.V}{Color.RESET}  "
                f"{color}{avg_rtt:>8.1f}ms{Color.RESET}  "
                f"{bar}  "
                f"{Theme.MUTED}({rtt_strs}ms){Color.RESET}"
            )

        # Connector
        lines.append(f"      {Theme.MUTED}{Box.V}{Color.RESET}")

        return lines

    async def run(self):
        """Run traceroute and display results."""
        width = min(Term.size()[0], 120)

        print(BANNER)
        print(f"  {Theme.TEXT}Traceroute to {Theme.BRAND}{Color.BOLD}{self.host}{Color.RESET}")

        # Resolve
        try:
            ip = socket.gethostbyname(self.host)
            print(f"  {Theme.MUTED}Resolved: {ip}{Color.RESET}")
        except socket.gaierror:
            ip = self.host
        print(f"  {Theme.MUTED}Max hops: {self.max_hops}{Color.RESET}")
        print()

        # Start with animated header
        print(f"  {Theme.BRAND}{Color.BOLD}{Box.GLOBE} Route Discovery{Color.RESET}")
        print(f"  {Theme.MUTED}{'─' * (width - 4)}{Color.RESET}")
        print(f"      {Theme.MUTED}{Box.V}{Color.RESET}")

        cmd = TracerouteRunner.build_command(self.host, self.max_hops)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            all_rtts = []

            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode("utf-8", errors="replace").strip()
                hop = TracerouteRunner.parse_line(line_str)
                if hop:
                    self.hops.append(hop)
                    if hop.rtt_ms:
                        all_rtts.extend(hop.rtt_ms)

                    max_rtt = max(all_rtts) if all_rtts else 100
                    for rendered_line in self._render_hop(hop, max_rtt, width):
                        print(rendered_line)
                    sys.stdout.flush()

            await proc.wait()

        except FileNotFoundError:
            print(f"\n  {Theme.DANGER}{Box.CROSS} traceroute command not found.{Color.RESET}")
            print(f"  {Theme.MUTED}Install: sudo apt install traceroute (Linux) or use tracert (Windows){Color.RESET}")
            return

        # Summary
        print(f"      {Theme.MUTED}{Box.V}{Color.RESET}")
        print(f"  {Theme.SUCCESS}{Color.BOLD}{Box.DOT} Destination Reached{Color.RESET}")
        print(f"  {Theme.MUTED}{'─' * (width - 4)}{Color.RESET}")
        print()

        # Stats summary
        completed = [h for h in self.hops if not h.timeout]
        timeouts = [h for h in self.hops if h.timeout]
        all_rtts = []
        for h in completed:
            all_rtts.extend(h.rtt_ms)

        print(f"  {Theme.TEXT_BRIGHT}{Color.BOLD}Route Summary{Color.RESET}")
        print(f"  Total Hops:    {Theme.BRAND}{len(self.hops)}{Color.RESET}")
        print(f"  Responding:    {Theme.SUCCESS}{len(completed)}{Color.RESET}")
        print(f"  Timeouts:      {Theme.DANGER}{len(timeouts)}{Color.RESET}")
        if all_rtts:
            print(f"  Avg Latency:   {Theme.latency_color(statistics.mean(all_rtts))}{statistics.mean(all_rtts):.1f}ms{Color.RESET}")
            print(f"  Max Latency:   {Theme.latency_color(max(all_rtts))}{max(all_rtts):.1f}ms{Color.RESET}")

        # ASCII route map
        if completed:
            print()
            print(f"  {Theme.TEXT_BRIGHT}Route Sparkline (latency per hop):{Color.RESET}")
            hop_avgs = []
            for h in self.hops:
                if h.rtt_ms:
                    hop_avgs.append(statistics.mean(h.rtt_ms))
                else:
                    hop_avgs.append(-1)

            spark = Sparkline.render(
                [v for v in hop_avgs if v >= 0], width - 6,
                color_func=lambda v: Theme.latency_color(v, 100)
            )
            print(f"  {spark}")

        print()


# ─── Multi-Host Comparison ───────────────────────────────────────────────────

class MultiPingCompare:
    """Side-by-side ping comparison of multiple hosts."""

    COLORS = [Theme.BRAND, Theme.SUCCESS, Theme.ACCENT1, Theme.ACCENT2, Theme.WARNING]

    def __init__(self, hosts: list[str], count: int = 20, interval: float = 0.5):
        self.hosts = hosts
        self.count = count
        self.interval = interval
        self.results: dict[str, PingStats] = {h: PingStats() for h in hosts}

    async def ping_host(self, host: str):
        """Ping a single host N times."""
        stats = self.results[host]
        for seq in range(self.count):
            stats.sent += 1
            cmd = PingParser.build_command(host, count=1, timeout=2)
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                output = stdout.decode("utf-8", errors="replace")

                parsed = None
                for line in output.splitlines():
                    result = PingParser.parse_line(line, seq, host)
                    if result:
                        parsed = result
                        break

                if parsed and not parsed.timeout:
                    stats.received += 1
                    stats.times.append(parsed.time_ms)
                    stats.history.append(parsed.time_ms)
                else:
                    stats.lost += 1
                    stats.history.append(-1)
            except Exception:
                stats.lost += 1
                stats.history.append(-1)

            # Progress dot
            if parsed and not parsed.timeout:
                sys.stdout.write(f"{Theme.SUCCESS}.{Color.RESET}")
            else:
                sys.stdout.write(f"{Theme.DANGER}x{Color.RESET}")
            sys.stdout.flush()

            await asyncio.sleep(self.interval)

    async def run(self):
        width = min(Term.size()[0], 120)

        print(BANNER)
        print(f"  {Theme.TEXT_BRIGHT}{Color.BOLD}Multi-Host Comparison{Color.RESET}")
        print(f"  {Theme.MUTED}Pinging {len(self.hosts)} hosts × {self.count} packets{Color.RESET}")
        print()

        # Ping all hosts
        for i, host in enumerate(self.hosts):
            color = self.COLORS[i % len(self.COLORS)]
            print(f"  {color}{Box.DOT} {host}{Color.RESET} ", end="")
            await self.ping_host(host)
            print()

        print()
        print(f"  {Theme.MUTED}{'─' * (width - 4)}{Color.RESET}")
        print()

        # Results table
        # Header
        print(f"  {Theme.TEXT_BRIGHT}{Color.BOLD}{'Host':<30} {'Avg':>8} {'Min':>8} {'Max':>8} {'P95':>8} {'Loss':>8} {'Jitter':>8}{Color.RESET}")
        print(f"  {Theme.MUTED}{'─' * 88}{Color.RESET}")

        bar_w = max(10, width - 100)
        max_avg = max((s.avg for s in self.results.values() if s.times), default=1)

        for i, (host, stats) in enumerate(self.results.items()):
            color = self.COLORS[i % len(self.COLORS)]
            if stats.times:
                avg_c = Theme.latency_color(stats.avg)
                bar = HBar.render(stats.avg, max_avg, bar_w, color=color)
                loss_c = Theme.SUCCESS if stats.loss_pct < 5 else Theme.DANGER

                print(
                    f"  {color}{host:<30}{Color.RESET} "
                    f"{avg_c}{stats.avg:>7.1f}ms{Color.RESET} "
                    f"{Theme.SUCCESS}{stats.min:>7.1f}ms{Color.RESET} "
                    f"{Theme.latency_color(stats.max)}{stats.max:>7.1f}ms{Color.RESET} "
                    f"{Theme.INFO}{stats.p95:>7.1f}ms{Color.RESET} "
                    f"{loss_c}{stats.loss_pct:>6.1f}%{Color.RESET} "
                    f"{stats.jitter:>7.1f}ms"
                )
                print(f"  {'':>30} {bar}")
            else:
                print(f"  {Theme.DANGER}{host:<30} {'UNREACHABLE':>8}{Color.RESET}")
            print()

        # Sparklines
        print(f"  {Theme.TEXT_BRIGHT}{Color.BOLD}Latency Timelines:{Color.RESET}")
        for i, (host, stats) in enumerate(self.results.items()):
            color = self.COLORS[i % len(self.COLORS)]
            data = list(stats.history)
            spark = Sparkline.render(data, min(60, width - 25),
                                    color_func=lambda v: color)
            label = f"{host[:20]:<20}"
            print(f"  {color}{label}{Color.RESET} {spark}")
        print()


# ─── Quick Ping (Non-Interactive) ────────────────────────────────────────────

class QuickPing:
    """Fast non-interactive ping with inline results."""

    def __init__(self, host: str, count: int = 10, interval: float = 0.5):
        self.host = host
        self.count = count
        self.interval = interval

    async def run(self):
        width = min(Term.size()[0], 100)
        stats = PingStats()

        print()
        print(f"  {Theme.BRAND}{Color.BOLD}{Box.PULSE} NetPulse Quick Ping{Color.RESET}")
        print(f"  {Theme.MUTED}Target: {self.host} | Packets: {self.count}{Color.RESET}")
        print()

        # Live dots
        sys.stdout.write(f"  {Theme.MUTED}Progress:{Color.RESET} ")
        sys.stdout.flush()

        for seq in range(self.count):
            stats.sent += 1
            cmd = PingParser.build_command(self.host, count=1, timeout=2)

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                output = stdout.decode("utf-8", errors="replace")

                parsed = None
                for line in output.splitlines():
                    result = PingParser.parse_line(line, seq, self.host)
                    if result:
                        parsed = result
                        break

                if parsed and not parsed.timeout:
                    stats.received += 1
                    stats.times.append(parsed.time_ms)
                    stats.history.append(parsed.time_ms)
                    dot_color = Theme.latency_color(parsed.time_ms)
                    sys.stdout.write(f"{dot_color}{Box.DOT}{Color.RESET}")
                else:
                    stats.lost += 1
                    stats.history.append(-1)
                    sys.stdout.write(f"{Theme.DANGER}{Box.CROSS}{Color.RESET}")
            except Exception:
                stats.lost += 1
                stats.history.append(-1)
                sys.stdout.write(f"{Theme.DANGER}{Box.CROSS}{Color.RESET}")

            sys.stdout.flush()
            if seq < self.count - 1:
                await asyncio.sleep(self.interval)

        print()
        print()

        # Sparkline
        spark = Sparkline.render(
            list(stats.history), width - 6,
            color_func=lambda v: Theme.latency_color(v)
        )
        print(f"  {spark}")
        print()

        # Stats
        if stats.times:
            loss_c = Theme.SUCCESS if stats.loss_pct < 5 else Theme.DANGER
            print(
                f"  {Theme.SUCCESS}AVG {stats.avg:.1f}ms{Color.RESET} │ "
                f"{Theme.SUCCESS}MIN {stats.min:.1f}ms{Color.RESET} │ "
                f"{Theme.latency_color(stats.max)}MAX {stats.max:.1f}ms{Color.RESET} │ "
                f"{Theme.INFO}P95 {stats.p95:.1f}ms{Color.RESET} │ "
                f"{loss_c}LOSS {stats.loss_pct:.1f}%{Color.RESET} │ "
                f"JITTER {stats.jitter:.1f}ms"
            )
        else:
            print(f"  {Theme.DANGER}All packets lost — host unreachable{Color.RESET}")

        print()


# ─── CLI Argument Parsing ────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netpulse",
        description=(
            f"{Color.BOLD}NetPulse{Color.RESET} — Modern Network Diagnostic Visualizer\n"
            "Real-time ping monitoring and traceroute with beautiful ASCII/ANSI graphics."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            f"\n{Color.BOLD}Examples:{Color.RESET}\n"
            f"  netpulse ping google.com              Live ping monitor\n"
            f"  netpulse ping --vibe google.com       Ping with background beat\n"
            f"  netpulse ping -i 0.2 -t 50 1.1.1.1    Custom interval/threshold\n"
            f"  netpulse trace cloudflare.com          Visual traceroute\n"
            f"  netpulse compare google.com 1.1.1.1    Compare hosts\n"
            f"  netpulse quick -c 50 8.8.8.8           Quick 50-ping test\n"
        )
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Ping subcommand
    ping_parser = subparsers.add_parser("ping", help="Real-time ping monitor with live graph")
    ping_parser.add_argument("host", help="Host to ping")
    ping_parser.add_argument("-i", "--interval", type=float, default=0.5,
                            help="Ping interval in seconds (default: 0.5)")
    ping_parser.add_argument("-t", "--threshold", type=float, default=100.0,
                            help="Latency threshold in ms for color coding (default: 100)")
    ping_parser.add_argument("-6", "--ipv6", action="store_true",
                            help="Use IPv6")
    ping_parser.add_argument("--vibe", action="store_true",
                            help="Play a background trap beat while pinging (0 to 100 real quick)")

    # Traceroute subcommand
    trace_parser = subparsers.add_parser("trace", help="Visual traceroute",
                                         aliases=["traceroute", "tr"])
    trace_parser.add_argument("host", help="Destination host")
    trace_parser.add_argument("-m", "--max-hops", type=int, default=30,
                             help="Maximum hops (default: 30)")

    # Compare subcommand
    compare_parser = subparsers.add_parser("compare", help="Multi-host comparison",
                                           aliases=["cmp"])
    compare_parser.add_argument("hosts", nargs="+", help="Hosts to compare (2-5)")
    compare_parser.add_argument("-c", "--count", type=int, default=20,
                               help="Pings per host (default: 20)")
    compare_parser.add_argument("-i", "--interval", type=float, default=0.3,
                               help="Interval between pings (default: 0.3)")

    # Quick subcommand
    quick_parser = subparsers.add_parser("quick", help="Quick non-interactive ping",
                                         aliases=["q"])
    quick_parser.add_argument("host", help="Host to ping")
    quick_parser.add_argument("-c", "--count", type=int, default=20,
                             help="Number of pings (default: 20)")
    quick_parser.add_argument("-i", "--interval", type=float, default=0.3,
                             help="Interval in seconds (default: 0.3)")

    return parser


# ─── Main ────────────────────────────────────────────────────────────────────

async def async_main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # Default: show help with banner
        print(BANNER)
        parser.print_help()
        print()
        return

    if args.command == "ping":
        monitor = PingMonitor(
            host=args.host,
            interval=args.interval,
            threshold=args.threshold,
            ipv6=args.ipv6,
            vibe=args.vibe,
        )
        await monitor.run()

    elif args.command in ("trace", "traceroute", "tr"):
        viz = TracerouteVisualizer(host=args.host, max_hops=args.max_hops)
        await viz.run()

    elif args.command in ("compare", "cmp"):
        if len(args.hosts) > 5:
            print(f"{Theme.WARNING}⚠ Limiting to 5 hosts for readability.{Color.RESET}")
            args.hosts = args.hosts[:5]
        cmp = MultiPingCompare(hosts=args.hosts, count=args.count, interval=args.interval)
        await cmp.run()

    elif args.command in ("quick", "q"):
        qp = QuickPing(host=args.host, count=args.count, interval=args.interval)
        await qp.run()


def main():
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda *_: None)

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        Term.show_cursor()
        print(f"\n{Theme.MUTED}Interrupted.{Color.RESET}")
    finally:
        Term.show_cursor()


if __name__ == "__main__":
    main()
