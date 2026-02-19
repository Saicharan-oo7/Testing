# Jetson Nano Modern Wi‑Fi GUI (PyQt5)

A portrait-friendly (1080x1920) modern Wi‑Fi manager for Jetson Nano using `PyQt5` and `nmcli`.

## Features
- Available Wi‑Fi scan with signal/security badges.
- Connect to open or secured networks.
- On-screen keyboard password dialog for touch displays (Caps toggle + letters, numbers, and special characters).
- Wi‑Fi radio on/off toggle.
- Saved networks list.
- Forget selected saved network.
- Connected network status indicator.
- Connection workflow shows a `Connecting...` state and clear error messages (including wrong password).
- Manual refresh + periodic status refresh.
- Light modern color palette for bright environments.
- Equal-sized on-screen keyboard buttons for consistent touch accuracy.
- iPhone-style keyboard layout and behavior with `123`/`ABC`, shift/caps, and symbol pages.
- Professional keyboard typography tuned for readability with Roboto Regular and balanced key text sizing.
- Uniform key spacing with row-offset alignment for a cleaner, phone-style keyboard layout.
- Automatic key width adjustment to prevent overlap and keep perfect row alignment across symbol/letter layouts.

## Requirements
- Ubuntu/Jetson Linux with NetworkManager (`nmcli`) enabled.
- Python 3.8+
- PyQt5
- Roboto font (recommended for mobile-style UI look)

Install PyQt5:
```bash
python3 -m pip install PyQt5
```

Install Roboto font (Ubuntu/Jetson):
```bash
sudo apt install fonts-roboto
```

## Run
```bash
python3 wifi_gui.py
```

## Notes
- The app shells out to `nmcli`, so it should run with permission to manage network connections.
- Hidden SSIDs are shown as `<Hidden Network>`.
