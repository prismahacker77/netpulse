# ⚡ NetPulse

**Modern Network Diagnostic Visualizer** — real-time ping monitoring & traceroute with beautiful ASCII/ANSI terminal graphics.

Zero external dependencies. Pure Python 3.10+. Just run it.

```
    ╔╗╔┌─┐┌┬┐╔═╗┬ ┬┬  ┌─┐┌─┐
    ║║║├┤  │ ╠═╝│ ││  └─┐├┤
    ╝╚╝└─┘ ┴ ╩  └─┘┴─┘└─┘└─┘
    ─── Network Diagnostic Visualizer ───
```

---

## ✨ Features

- **Live Summary Dashboard** — clean, stable, report-style view that updates values in-place (no flicker)
- **Visual Traceroute** — hop-by-hop route visualization with latency bars
- **Multi-Host Compare** — side-by-side ping comparison of up to 5 hosts
- **Quick Ping** — fast non-interactive mode with inline sparkline results
- **Latency Sparkline** — color-coded history bar using Unicode block characters (▁▂▃▄▅▆▇█)
- **Rich Statistics** — AVG, MIN, MAX, P95, StdDev, Jitter, Packet Loss
- **Latency Heatmap Colors** — smooth green → yellow → red gradient
- **`--vibe` Mode** — plays a synthesized trap beat in the background while you ping (yes, really)
- **Cross-Platform** — Linux, macOS, Windows
- **Zero Dependencies** — pure Python standard library, no `pip install` needed

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/prismahacker77/netpulse.git
cd netpulse

# Run directly — no install needed
python3 netpulse.py ping google.com

# Or install as a CLI tool
pip install -e .
netpulse ping google.com
```

---

## 📖 Commands

### `ping` — Live Monitor

```bash
netpulse ping google.com                # Live dashboard
netpulse ping -i 0.2 -t 50 1.1.1.1      # 200ms interval, 50ms threshold
netpulse ping -6 ipv6.google.com         # IPv6
netpulse ping --vibe google.com          # With background beat 🎵
```

Press **`q`** to quit. On exit you get a final session summary.

### `trace` — Visual Traceroute

```bash
netpulse trace cloudflare.com
netpulse trace -m 20 google.com          # Max 20 hops
```

### `compare` — Multi-Host Comparison

```bash
netpulse compare google.com 1.1.1.1 8.8.8.8
netpulse compare -c 50 aws.amazon.com azure.microsoft.com cloud.google.com
```

### `quick` — Non-Interactive Ping

```bash
netpulse quick google.com               # 20 pings, inline results
netpulse quick -c 100 1.1.1.1           # 100 pings
```

---

## 🎨 What the Live View Looks Like

The `ping` command displays a stable dashboard. The layout is painted once; only the numbers and sparkline update in-place — no screen redraw, no flicker.

```
  ⠙ Pinging google.com — press q to quit


    ╔╗╔┌─┐┌┬┐╔═╗┬ ┬┬  ┌─┐┌─┐
    ║║║├┤  │ ╠═╝│ ││  └─┐├┤
    ╝╚╝└─┘ ┴ ╩  └─┘┴─┘└─┘└─┘
    ─── Network Diagnostic Visualizer ───

  Live Session  ● HEALTHY
  ──────────────────────────────────────

  Target:   google.com (142.250.217.14)
  Duration: 00:00:34

  Packets:
    Sent:     68
    Received: 68
    Lost:     0 (0.0%)

  Latency:
    Min:    18.42ms
    Avg:    23.15ms
    Max:    41.73ms
    P95:    35.20ms
    StdDev: 4.32ms
    Jitter: 3.88ms

  Latency History:
  ▂▃▂▁▃▅▂▃▁▂▃▂▇▂▃▁▄▃▅▂▃▃▁▂▅▃▂▄▂▃▁▃▂
```

---

## 🎵 `--vibe` Mode

```bash
netpulse ping --vibe google.com
```

Generates a **trap-inspired instrumental beat** from scratch using pure Python synthesis — 808 kicks, snare, hi-hats, bass, and synth stabs. The beat builds across 4 bars at 140 BPM with rising energy, then loops.

All audio is synthesized at runtime into a WAV file using `math` + `struct` + `wave` (stdlib only). Playback is handled by whatever your OS provides:

| Platform | Player |
|----------|--------|
| macOS | `afplay` |
| Linux | `paplay`, `aplay`, or `ffplay` |
| Windows | PowerShell `SoundPlayer` |

The beat runs in a background process and doesn't affect ping performance. It stops and cleans up automatically when you quit.

---

## 📊 Statistics

| Metric | Description |
|--------|-------------|
| **AVG** | Mean round-trip time |
| **MIN** | Lowest observed latency |
| **MAX** | Highest observed latency |
| **P95** | 95th percentile — 95% of pings are below this |
| **StdDev** | Standard deviation — measures consistency |
| **Jitter** | Mean difference between consecutive pings |
| **Loss** | Percentage of timed-out packets |

---

## 🖥️ Requirements

- **Python 3.10+**
- **ANSI-capable terminal** — iTerm2, Hyper, Windows Terminal, GNOME Terminal, etc.
- `ping` in PATH (pre-installed on all major OSes)
- `traceroute` (Linux/macOS) or `tracert` (Windows) for route tracing
- For `--vibe`: any of `afplay`, `paplay`, `aplay`, `ffplay`, or PowerShell (optional — ping works fine without audio)

---

## 🏗️ Architecture

Single-file, zero-dependency Python application:

```
netpulse.py
├── Color / Theme         ANSI truecolor engine with latency gradients
├── Box                   Unicode box-drawing & block elements
├── BrailleGraph          High-res 2×4 dot-matrix graph renderer
├── Sparkline             Compact block-character sparkline
├── HBar                  Horizontal bar chart
├── Panel                 Bordered panels with rounded corners
├── PingParser            Cross-platform ping output parser
├── TracerouteRunner      Cross-platform traceroute parser
├── VibeEngine            WAV synthesizer — 808 kick, snare, hats, bass, synth
├── PingMonitor           Stable live dashboard (paint-once, update-in-place)
├── TracerouteVisualizer  Streaming hop-by-hop route display
├── MultiPingCompare      Concurrent multi-host comparison
└── QuickPing             Fast non-interactive ping
```

---

## 🔧 vs. the Original

This project was inspired by [ping_graph](https://github.com/vitovt/ping_graph) by vitovt. Here's how it compares:

| | ping_graph | **NetPulse** |
|---|---|---|
| Dependencies | matplotlib, numpy | **None** |
| Interface | Matplotlib GUI window | **Terminal dashboard** |
| Rendering | Full window repaint | **In-place value updates (no flicker)** |
| Traceroute | ❌ | ✅ |
| Multi-host compare | ❌ | ✅ |
| Statistics | avg / min / max | **+ P95, Jitter, StdDev** |
| Background music | ❌ | **✅ `--vibe`** |
| Cross-platform | Linux + macOS | **Linux + macOS + Windows** |
| Install | pip + venv + matplotlib | **Just run the .py file** |

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

## 🙏 Credits

Inspired by [ping_graph](https://github.com/vitovt/ping_graph), [gping](https://github.com/orf/gping), and [mtr](https://github.com/traviscross/mtr).
