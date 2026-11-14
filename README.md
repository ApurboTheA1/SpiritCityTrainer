# Spirit City: Lofi Sessions — Desktop Trainer & Cheat Engine Table

[![Platform](https://img.shields.io/badge/Platform-Windows%20x64-blue)](#requirements)
[![Python](https://img.shields.io/badge/Python-3.10%2B%20(Zero%20Dependencies)-3776AB)](#quick-start)
[![Engine](https://img.shields.io/badge/Unreal%20Engine-5.7.3-lightgrey)](#how-it-works)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

A standalone **Windows desktop trainer** and companion **Cheat Engine 7.x table** for **Spirit City: Lofi Sessions** (`SpiritCity-Win64-Shipping.exe`), **created using AI**. Built using dynamic AOB signature scanning, runtime Unreal Engine 5.7.3 reflection, and Blueprint VM / `ProcessEvent` hooking — zero hardcoded runtime addresses and zero third-party Python dependencies.

> **Note:** This trainer, UE5 reflection engine, and Cheat Engine table were researched, developed, and optimized using AI.

---

## Repository Contents

| File | Description |
| :--- | :--- |
| `spirit_city_trainer.py` | Dark-mode desktop GUI trainer built with Python's standard `tkinter` / `ttk` library. |
| `ue_engine.py` | UE 5.7.3 memory reader/writer, dynamic AOB resolver, reflection inspector, x64 code cave hook, and game-thread `UFunction` caller. |
| `Launch_Trainer.bat` | One-click Windows launcher script. |
| `SpiritCity_LofiSessions.CT` | Cheat Engine 7.x table with dynamic Lua resolver, Auto Assembler `[Master Hook]`, pointer entries, and a built-in Lua EXP Slider window. |
| `requirements.txt` | Notes zero external `pip` dependencies (Python 3.10+ stdlib only). |
| `LICENSE` | MIT License. |

---

## Features

### 1. EXP & Spirit Credits Multipliers
- **EXP Earned Multiplier (`0.0x` – `50.0x` slider + custom values e.g. `100x`):** Intercepts `BP_SessionsPlayerController_C::Add XP` inside `ProcessLocalScriptFunction` so **all** XP sources scale automatically (1-minute active ticks, Pomodoro completion, Daily Login, Daily Todo, Spirit discoveries), while preserving native XP bar animations, level-ups, +500 Credit rewards, Steam achievements, and saving.
- **Spirit Credits Multiplier (`0.0x` – `50.0x` slider + custom values):** Scales credits awarded through `Add Spirit Credits`.
- **Live Hook Telemetry:** Displays intercepted XP call count alongside `Last Raw -> Multiplied XP`.

### 2. Economy, Daily Bonuses & Direct Stat Editors
- **Free Shop / Zero Cost Purchases:** Forces item price checks and debit amounts to `0` across Wardrobe, Room, Garden, Train, Library, and Spirit Skins.
- **Unlimited Daily EXP & Credits Bonus:** Keeps daily login, todo, and pomodoro bonus flags active on every completion.
- **Native Grants & Exact Editors:** Grant XP (native notification & auto level-up), Grant Spirit Credits, Set Exact Total XP, Set Level (with optional level-curve XP sync), Set Spirit Credits, Trigger Level Up, and Force Save Game.

### 3. World, Game Speed, Time of Day & Focus Timer
- **Game Speed (`TimeDilation`) Slider (`0.1x` – `20.0x`).**
- **Time of Day Override:** Toggle real-life clock sync or switch lighting modes (`Morning`, `Day`, `Sunset`, `Night`).
- **Pomodoro / Focus Timer / Stopwatch:** Live segment & timer readout, **Complete Active Timer / Pomodoro Segment in ~1s** (preserving completion logs and rewards), and Stopwatch `TimePassed` editor.
- **Train Controls (*All Aboard!* DLC):** Adjust Train Speed (`0`–`5000`) and Train Shake Multiplier (`0.0`–`5.0`).
- **Audio, UI & Camera:** Toggle audio mute, hide in-game HUD, adjust Camera Parallax Strength, and edit Playtime Today.

### 4. Spirits, Spiritdex & Live Clue Inspector
- **Live Room & Audio Setup Telemetry:** Displays live player room state (`Location`, `Nook / Spot`, `Activity`, `Time of Day`, `Active Soundscapes`, and `Equipped Companion`) updated in real time.
- **Companion Category Filters:** Quick-filter the companion table by room (`All`, `Bedroom`, `Kitchen`, `Train`, `Garden`, `Library`) or status (`Discovered`, `Undiscovered`).
- **Complete Conditions & Clues Inspector for All 76 Companions:** Shows exact in-game requirements extracted directly from engine metadata:
  - Required Room Location (`Bedroom`, `Kitchen`, `Train`, `Garden`, `Library`, or `Any Room`)
  - Required Spot / Nook (`Desk`, `Bed`, `Lounge Rug`, `Window Sill`, `Train Seat`, etc.)
  - Required Time of Day (`Morning`, `Day`, `Sunset`, `Night`)
  - Required Activity (`Reading`, `Writing`, `Drawing`, `Gaming`, `Typing / Coding`, `Knitting`, `Cooking`, etc.)
  - Exact Required Soundscape Audio (`Forest Birds`, `Rain on Window`, `Fireplace / Crackling Fire`, `Gentle Wind`, `Vinyl Record Player`, `Winter Snow`, `Distant Thunder`, `Night Forest`, `BBQ Sizzle`, `Tasty Bubbling`, etc.)
  - Required Equipped Companion (e.g. Bentobunny requires `Dust Bunny`, Cinnaspinner requires `Arachknit`, Syrupii requires `Goopii`)
  - Required Room / Train Background Customization (e.g. `Train_Background_City`, `Train_Background_Sky`, etc.)
  - Native Lure Duration (`Instant`, `2m`, `6m`, `15m`, `25m`, `40m`, `60m`)
- **Live Condition Diffing & Match Status:** Instantly informs you whether your current setup matches the selected companion (`✅ All Room & Audio Conditions MATCH!`), or pinpoints exactly what is missing (`⚠️ Missing Conditions: Turn ON Soundscape: Fireplace, Change Time of Day to Night, Equip Companion: Dust Bunny`).
- **⚡ Auto-Match Time of Day:** Automatically switches in-game lighting and time of day to match the selected companion with a single click.
- **Fast Spirit Luring (`0.05s` – `5.0s` interval):** Automatically evaluates conditions and advances active luring ticks so spirits arrive in seconds once conditions match.
- **✨ Instant Discover Selected Companion:** Instantly unlocks the selected companion and sets friendship to 999.
- **🌟 Unlock & Max ALL 76 Companions:** Unlocks all 76 spirits across all DLCs/rooms with max friendship (999) using 100% byte-accurate GVAS serialization into `%LOCALAPPDATA%\SpiritCity\Saved\SaveGames\SCLS_Spiritdex.sav`.
- **Friendship Editors:** Set custom friendship scores for any companion or max all discovered friendships in one click.

### 5. Unlocks, Steam Achievements & Utilities
- **Unlock All Content Packages (`0..12`)** in memory via `GameInstance.Owned Content Packages`.
- **Sync Steam Achievements** retroactively for your current Level and Discovered Spirits.
- **Toggle Built-in Developer Widgets** (`WBP_CheatMenu`, `WBP_DebugMenu`).
- **One-Click Save Backup:** Copies `%LOCALAPPDATA%\SpiritCity\Saved\SaveGames` to a timestamped backup folder.

---

## Requirements

- **OS:** Windows 10 / 11 (64-bit)
- **Game:** *Spirit City: Lofi Sessions* (Steam / `SpiritCity-Win64-Shipping.exe`, Unreal Engine 5.7.3)
- **Python:** 3.10+ (for the GUI Trainer — includes `tkinter`, requires **no `pip install`**)
- *(Optional)* **Cheat Engine 7.x** if using `SpiritCity_LofiSessions.CT`

---

## Quick Start

### Option A — Standalone GUI Trainer (Recommended)
1. Launch **Spirit City: Lofi Sessions** and wait until your room has loaded.
2. Clone or download this repository.
3. Double-click **`Launch_Trainer.bat`**, or run from a terminal:
   ```bat
   python -B spirit_city_trainer.py
   ```
4. The trainer automatically attaches to `SpiritCity-Win64-Shipping.exe`, resolves engine pointers, installs the safe x64 hook, and populates live stats.
   > **Note:** On closing the trainer window, the hook cleanly restores original instructions before detaching.

### Option B — Cheat Engine Table
1. Launch **Spirit City: Lofi Sessions** and wait until your room has loaded.
2. Open **`SpiritCity_LofiSessions.CT`** in **Cheat Engine 7.x**.
3. Attach to `SpiritCity-Win64-Shipping.exe` (auto-attaches on table open if already running).
4. Enable **`[Master Hook]`** and optionally enable **`[Open EXP Multiplier Slider GUI Window]`**.

---

## How It Works

1. **Dynamic Signature Scanning:** Reads the target process's `.text` section and performs fast byte-anchor AOB scans to locate `GWorld`, `FNamePool`, `GUObjectArray`, and `UObject::ProcessLocalScriptFunction`, resolving `UObject::ProcessEvent` directly from `UWorld`'s vtable (`[76]`).
2. **Runtime UE5 Reflection:** Walks `UClass` / `UStruct` child properties (`FProperty`) and `UFunction` chains using `FNamePool` so actor/widget offsets are discovered dynamically from live metadata.
3. **Blueprint VM Intercept & Game-Thread Dispatch:** Allocates a small RWX code cave within ±2 GB of `ProcessLocalScriptFunction`. Parameter overrides (`Add XP`, `Add Spirit Credits`, `Debit Spirit Credits`, `Check if can buy item`, `StartSpiritLuringTimer`) run inline before Blueprint VM execution, while UI-triggered actions (`Add XP`, `TriggerSave`, `SetVisibility`, etc.) execute safely on the game thread via an interlocked `ProcessEvent` command slot.

---

## Troubleshooting

- **"Failed to open game process" / Access Denied:** Run `Launch_Trainer.bat` (or your terminal) **as Administrator** if the game was launched elevated.
- **"Game world is still loading":** Wait until you load past the title screen into your room, then click **Re-Attach**.
- **"Game-thread UFunction call timed out":** Happens if the game is paused/frozen or fully minimized when invoking a command; bring the game window briefly into focus/unpaused.

---

## Credits & Disclaimer

- **Development:** This trainer and Cheat Engine table were created using AI.
- **Usage:** Intended strictly for personal, offline experimentation in a single-player relaxing/productivity game. Use the built-in **Backup SaveGames Folder Now** button (or copy `%LOCALAPPDATA%\SpiritCity\Saved\SaveGames`) before modifying progression or unlocks.
