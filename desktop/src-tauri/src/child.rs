//! Child-process orchestration for the two Python sidecars.
//!
//! We deliberately avoid the Tauri ``shell`` plugin's ``sidecar`` API
//! because pyinstaller's ``--onedir`` output is a *directory* (one
//! launcher binary plus a `_internal/` tree) and Tauri's sidecar
//! convention only handles single-file binaries. Instead we ship the
//! whole ``binaries/xiexie-{backend,overlay}/`` directory as a Tauri
//! resource (see ``tauri.conf.json -> bundle.resources``) and spawn the
//! launcher with `std::process::Command`. That gives us full control
//! over the child's working directory, environment, and (critically)
//! the OS PID so we can SIGTERM-then-SIGKILL it on quit.

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

use crate::ChildProcesses;

/// Backend health-check endpoint. Must match
/// ``backend/xiexie/main.py``'s ``GET /health``.
const HEALTH_URL: &str = "http://127.0.0.1:8787/health";

/// Hard ceiling for backend warm-up. faster-whisper preload + Z.AI proxy
/// connection burns ~6–10 s on a cold cache; 30 s is a generous slack.
const HEALTH_TIMEOUT: Duration = Duration::from_secs(30);

/// Polling cadence for the health loop.
const HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);

/// Grace period for a child to honour SIGTERM before we SIGKILL it.
const SHUTDOWN_GRACE: Duration = Duration::from_secs(5);

/// Resolve the directory holding a sidecar launcher binary.
///
/// Inside a packaged ``.app`` this lives at:
///   ``Xiexie.app/Contents/Resources/binaries/<name>/``
///
/// In ``cargo tauri dev`` it lives at:
///   ``desktop/src-tauri/binaries/<name>/``
///
/// Both shapes are returned by ``app.path().resource_dir()`` so we
/// don't have to special-case them.
fn binary_dir(app: &AppHandle, name: &str) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("resource_dir lookup failed: {e}"))?;
    Ok(resource_dir.join("binaries").join(name))
}

/// Spawn the FastAPI backend as ``binaries/xiexie-backend/xiexie-backend``
/// and block until ``GET /health`` returns 200 (or the 30 s timeout
/// elapses, whichever comes first).
pub fn start_backend(app: &AppHandle) -> Result<(), String> {
    let dir = binary_dir(app, "xiexie-backend")?;
    let bin = dir.join("xiexie-backend");
    if !bin.exists() {
        return Err(format!(
            "backend binary missing: {}\n\
             Run `desktop/scripts/build-python-binaries.sh` to produce it.",
            bin.display()
        ));
    }

    eprintln!("[xiexie] launching backend: {}", bin.display());

    let data_dir = app
        .path()
        .app_data_dir()
        .map(|d| d.join("data"))
        .unwrap_or_else(|_| PathBuf::from("./xiexie-data"));
    let _ = std::fs::create_dir_all(&data_dir);

    let child = Command::new(&bin)
        .current_dir(&dir)
        // The backend honours these env vars for sandbox-friendliness.
        // We always force loopback binding so a stray ``0.0.0.0`` from
        // a stale ``.env`` doesn't expose the agent on the LAN.
        .env("XIEXIE_HOST", "127.0.0.1")
        .env("XIEXIE_PORT", "8787")
        .env("XIEXIE_DATA_DIR", data_dir.as_os_str())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| format!("spawn backend: {e}"))?;

    let state = app.state::<ChildProcesses>();
    *state.backend.lock().unwrap() = Some(child);

    wait_for_health()?;
    eprintln!("[xiexie] backend healthy on {HEALTH_URL}");
    Ok(())
}

/// Spawn the PyQt6 overlay daemon — ``binaries/xiexie-overlay/xiexie-overlay``
/// — pointed at the backend's WebSocket endpoint.
///
/// The overlay reconnects on its own if the backend isn't ready yet, so
/// we don't health-check this one.
pub fn start_overlay(app: &AppHandle) -> Result<(), String> {
    let dir = binary_dir(app, "xiexie-overlay")?;
    let bin = dir.join("xiexie-overlay");
    if !bin.exists() {
        return Err(format!(
            "overlay binary missing: {}\n\
             Run `desktop/scripts/build-python-binaries.sh` to produce it.",
            bin.display()
        ));
    }

    eprintln!("[xiexie] launching overlay: {}", bin.display());

    let child = Command::new(&bin)
        .current_dir(&dir)
        .arg("--url")
        .arg("ws://127.0.0.1:8787/ws")
        .arg("--position")
        .arg("top-right")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|e| format!("spawn overlay: {e}"))?;

    let state = app.state::<ChildProcesses>();
    *state.overlay.lock().unwrap() = Some(child);
    Ok(())
}

fn wait_for_health() -> Result<(), String> {
    let deadline = Instant::now() + HEALTH_TIMEOUT;
    let mut last_err: Option<String> = None;
    while Instant::now() < deadline {
        match ureq::get(HEALTH_URL).timeout(Duration::from_secs(2)).call() {
            Ok(resp) if resp.status() == 200 => return Ok(()),
            Ok(resp) => last_err = Some(format!("HTTP {}", resp.status())),
            Err(e) => last_err = Some(format!("{e}")),
        }
        std::thread::sleep(HEALTH_POLL_INTERVAL);
    }
    Err(format!(
        "backend /health never returned 200 within {}s (last error: {})",
        HEALTH_TIMEOUT.as_secs(),
        last_err.unwrap_or_else(|| "n/a".into()),
    ))
}

/// Best-effort graceful shutdown: SIGTERM, wait up to ``SHUTDOWN_GRACE``,
/// then SIGKILL. Logging only — never panics so app-quit always succeeds.
pub fn shutdown(slot: &Mutex<Option<Child>>, label: &str) {
    let mut guard = match slot.lock() {
        Ok(g) => g,
        Err(poisoned) => poisoned.into_inner(),
    };
    let Some(mut child) = guard.take() else {
        return;
    };
    let pid = child.id();
    eprintln!("[xiexie] shutting down {label} (pid {pid})…");

    #[cfg(unix)]
    {
        // SAFETY: ``kill`` is a well-defined POSIX syscall that mutates
        // process state but doesn't touch any Rust invariant. ``pid``
        // came from a Child we still hold, so even if it's already
        // exited the worst case is ESRCH which we ignore.
        unsafe {
            libc::kill(pid as libc::pid_t, libc::SIGTERM);
        }
    }

    let deadline = Instant::now() + SHUTDOWN_GRACE;
    while Instant::now() < deadline {
        match child.try_wait() {
            Ok(Some(status)) => {
                eprintln!("[xiexie] {label} exited cleanly: {status}");
                return;
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(100)),
            Err(e) => {
                eprintln!("[xiexie] try_wait({label}): {e}");
                break;
            }
        }
    }

    eprintln!("[xiexie] {label} ignored SIGTERM, sending SIGKILL");
    let _ = child.kill();
    let _ = child.wait();
}
