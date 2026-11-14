# Lean Plan

An offline Python journal for weight and daily macros. The interface is English and always dark.

This repository contains the source code. Personal journals, backups, screenshots, compiled executables and the bundled Python runtime are excluded.

## Run from source

Use Python 3.11 or newer. On Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "pywebview>=6.2,<7"
.\.venv\Scripts\python.exe app.py
```

The desktop shell uses Microsoft Edge WebView2. To run in a browser without desktop dependencies, use `python app.py --browser`.

For an existing portable build, double-click **Lean Plan.exe** or **Start Lean Plan.cmd**. Keep its `app.py`, `leanplan`, `static` and `.runtime` folders together. Launcher and runtime build scripts are in `tools/`.

## Use

- The optional two-step setup collects an adult profile, starting weight/weight goal and optional **Body composition**. Switch between fixed **FFM (kg)** and **Body fat (%)** in setup or Settings. Known composition uses Cunningham 1991; clearing the selected input restores Mifflin–St Jeor, which requires weight, height, adult age and an explicitly selected sex coefficient. Existing saved profiles are preserved. MET defaults to **2.25** and is adjusted separately in Settings.
- Edit weight directly in **Latest weight** on Overview. The next section separates calculated calories/TEF from protein, carbs and fat inputs. Activity contains training time, calculated training energy, steps and walking energy. A full-width weight chart sits below these sections.
- Settings also apply automatically. There are no save buttons or calorie targets.
- **Daily journal** is a list of days, newest first, with eight days per page and no scrolling. Click a date to view or edit its Measurements or Activity. Missing days remain empty and can be filled later.
- **Archive period** closes completed days through yesterday. Name the archive (for example, Cut or Maintain); today's entries stay in the current period. Current totals, averages and charts use only that current period. The last known weight carries over for BMR without becoming a new measurement or weight-average sample.
- Select a saved period above the journal list to review its days and totals. Archives are read-only snapshots: future profile/MET changes do not recalculate them. CSV exports from an archive include only that selected period; the JSON export includes all periods.
- Entering or editing a previous day permanently marks it **Late entry**, including in CSV/JSON archives. Late records use the same formulas and enter statistics once enough data is available.
- Delete an individual active date from its detail view, or clear all history with confirmation. Clearing removes current entries and archives, keeps the profile and starts a fresh journal today. A local safety backup is created before clearing or archiving.
- **Insights** contains full-width weight and calorie charts, a seven-day rolling mean and an optional weight goal. The chart section has the same coordinates and dimensions as the weight chart on Overview.

## Window and layout

The interface uses one **1200 × 780** logical canvas. All pages share the same header and content origin, content bounds, panel radii and control sizes. There are no page scroll areas or breakpoint-dependent rearrangements.

On Windows the preferred client size is **1200 × 780 DIPs**: about a quarter of a 2560 × 1440 screen at 100% scaling, including the native frame. The window grows with Windows' per-monitor DPI, rather than filling the available monitor. It is reduced uniformly only if needed to fit the work area, including native borders, taskbar and margins. The native window cannot be resized or maximized; full screen, title-bar maximize gestures and browser zoom are disabled. Moving to a display with a different work area or DPI recalculates its bounds. This follows Microsoft's [DIP sizing](https://learn.microsoft.com/en-us/windows/win32/learnwin32/dpi-and-device-independent-pixels) and [Per-Monitor V2 guidance](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows).

## Calculations

| Value | Formula |
| --- | --- |
| Calories | `protein × 4 + fat × 9 + carbs × 4` |
| TEF | `protein × 4 × 0.25 + carbs × 4 × 0.075 + fat × 9 × 0.02` |
| BMR with fat-free mass | `370 + 21.6 × fat-free mass in kg` (Cunningham 1991) |
| Fat-free mass from body fat | `body weight × (1 − body fat percentage / 100)` |
| BMR without fat-free mass | `10 × kg + 6.25 × cm − 5 × age + sex constant` (Mifflin–St Jeor; male +5, female −161) |
| Training | `minutes × (MET − 1) × 3.5 × kg ÷ 200` |
| Expenditure | BMR + the available training, walking and TEF components |
| Balance | Expenditure − calories; positive is deficit, negative is surplus |

These are estimates of resting energy, TEF and activity energy. **Walking energy** means active walking kcal only; steps are a separate count and never add duplicate energy. Unlogged activity is not estimated, and there is no hidden activity multiplier. Today's balance combines a full day's resting estimate with the intake and activity entered so far. Settings → Formulas explains the coefficients. Independent control examples and calculation checks are in `tests/test_calculation_audit.py` and `tools/check_calculations.py`.

**Body composition** has two modes. **FFM (kg)** keeps the entered fat-free mass fixed as body weight changes. It means total body mass excluding fat, not muscle mass. **Body fat (%)** keeps the entered percentage fixed and derives FFM from each day's latest known body weight; e.g. 80 kg at 10% means 72 kg FFM, and 90 kg at 10% means 81 kg FFM. That mode needs a known body weight; an absent weight is not treated as zero or replaced with a future measurement. Neither mode estimates changing body fat by itself.

The modes retain their own inputs. If the destination mode has never been filled (or has been cleared), the switch fills an equivalent starting value from the other mode and the current known weight when possible. Previously entered values are preserved. Only the selected mode affects calculations; clearing its input restores Mifflin–St Jeor even when the other mode has a stored value. A small readout shows the equivalent FFM or percentage. Values autosave immediately, including mode changes.

The FFM equation does not require height, age or sex; direct FFM also works without total weight. Training still requires total body weight. Direct FFM must be positive and cannot exceed a known body weight; body fat is at least 0 and below 100 percent. The BMR caption identifies the selected formula. The coefficients come from [Cunningham's 1991 publication](https://pubmed.ncbi.nlm.nih.gov/1957828/). More accurate body-composition data can help, but changing equations does not guarantee a more accurate personal estimate. Like other profile changes, composition changes recalculate the active period; archived periods keep their original settings and results.

Calories and TEF sum the macros entered so far, even when only protein, carbs or fat is present. Blank macro fields stay unknown in storage and add no contribution; explicit zero values are recorded as zero. When all three macros are empty, intake and TEF remain unknown, with no calorie sample or energy balance. Missing readouts display a small **No data** without units; input fields remain empty. Missing activity contributes no invented energy. Completely skipped days affect neither totals nor averages.

Without a new weight, calculations use the latest measurement on an earlier date. Carried weight is shown as an input placeholder and is not stored as a new measurement or added to the weight average. Weight charts plot only explicitly recorded weights, end at the last actual measurement and label only measurement dates. With many measurements, some date labels are spaced out to keep them readable; every point still has its date in the tooltip. Equal weights recorded on different dates remain separate measurements. Filling an old weight recalculates subsequent days using the last measurement known on each date. MET is edited only in Settings; changing it recalculates today's training and sets the default for new records. Earlier days retain their own intensity. Notes are no longer shown in the interface; legacy notes remain in stored archives.

## Autosave and storage

The screen calculates optimistic updates immediately. Local writes are coalesced and processed sequentially; responses cannot overwrite newer input. Updates send only changed fields. Interrupted writes retain their drafts and retry automatically. **Saved on device** indicates when the queue is empty. The desktop window waits for pending changes before closing.

Live and server calculations round to three decimal places with the same symmetric rule. Summaries and exports use a consistent database snapshot. JSON recalculates active calorie totals from their macros rather than trusting old cached calorie values. Archived snapshots remain unchanged. Weekly change is the difference of the two seven-day measurement averages and needs at least one actual weight in each window.

Records are in **`data/leanplan.sqlite3`**. Safety snapshots are stored in **`data/backups/`** before the first change each day, deletions, and schema upgrades. Old records survive upgrades; missing macro values are not fabricated.

Export CSV or all data as JSON from Settings. CSV includes late-entry provenance. JSON version 4 includes current entries, their carryover weight, journal boundaries and full frozen archives. Archiving and resetting the active journal happen in one SQLite transaction. To move the journal, close the application and copy its `data` folder. Keep an additional copy elsewhere for protection against disk loss.

The application has no cloud service, accounts, online fonts or analytics. Its interface is served only on loopback. Cloud authentication/sync can be added separately later.

## Development

Python 3.11+ runs the server and model with the standard library. `pywebview` provides the optional desktop shell; Playwright is used only for development checks.

```powershell
python -m unittest discover -s tests -v
$env:PYTHONPATH = (Get-Location).Path
python tools/check_ui.py
python tools/check_calculations.py
python tools/check_layout.py --matrix
.\.runtime\python.exe tools/check_desktop.py
```

UI checks use disposable data and an injected calendar. They cover instant recalculation, autosave order, interrupted writes, empty fields, late entries, skipped days, journal pagination, archive boundaries, read-only snapshots, history deletion and exports. Layout checks export review screenshots, compare exact page coordinates and check overflow across viewport/DPI configurations. The native desktop check verifies work-area bounds, DPI-aware preferred sizing, blocked maximize/fullscreen commands and flushing pending edits on immediate close.

**Start Lean Plan.cmd** opens the same GUI launcher as **Lean Plan.exe**, without keeping a console window attached to the app. Logs are in `data/app.log`. To run in a console for diagnostics: `.\.runtime\python.exe app.py`. To use the browser: `.\.runtime\python.exe app.py --browser`.

The Windows shell logs WebView2 process failures and automatically reloads a failed renderer or recreates a failed browser control. Recovery uses the saved local journal and retains the window geometry. Repeated failures show a native message instead of an empty window; the app can still close if its renderer is unavailable. `tools/check_startup.py` checks the actual CMD/EXE launch, rendered pixels and recovery from intentionally terminated WebView2 processes using isolated test data.
