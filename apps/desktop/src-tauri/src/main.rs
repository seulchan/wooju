//! Wooju desktop shell.
//!
//! Starts the bundled Python server (a sidecar) on a free local port, shows a
//! loading page, and switches the window to the app once the server answers.
//! Quitting the app stops the server. Server output goes to
//! ~/Library/Logs/Wooju/server.log for troubleshooting.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{create_dir_all, OpenOptions};
use std::io::Write;
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

struct Server(Mutex<Option<CommandChild>>);

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(48731)
}

fn wait_until_listening(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    false
}

fn log_path() -> Option<PathBuf> {
    let home = std::env::var_os("HOME")?;
    let dir = PathBuf::from(home).join("Library/Logs/Wooju");
    create_dir_all(&dir).ok()?;
    Some(dir.join("server.log"))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Wooju")
                .inner_size(1180.0, 800.0)
                .min_inner_size(720.0, 520.0)
                .build()?;

            let port = free_port();
            let port_arg = port.to_string();
            let (mut events, child) = app
                .shell()
                .sidecar("wooju-server")?
                .args(["--port", port_arg.as_str()])
                .spawn()?;
            app.manage(Server(Mutex::new(Some(child))));

            // Keep the server's output: drain it so the pipe never fills, and log it.
            tauri::async_runtime::spawn(async move {
                let mut log = log_path().and_then(|p| {
                    OpenOptions::new().create(true).append(true).open(p).ok()
                });
                while let Some(event) = events.recv().await {
                    let line = match event {
                        CommandEvent::Stdout(b) | CommandEvent::Stderr(b) => b,
                        CommandEvent::Terminated(t) => {
                            format!("server exited: {:?}\n", t.code).into_bytes()
                        }
                        _ => continue,
                    };
                    if let Some(f) = log.as_mut() {
                        let _ = f.write_all(&line);
                    }
                }
            });

            std::thread::spawn(move || {
                if wait_until_listening(port, Duration::from_secs(90)) {
                    if let Ok(url) = format!("http://127.0.0.1:{port}/").parse::<Url>() {
                        let _ = window.navigate(url);
                    }
                } else {
                    let _ = window.eval(
                        "document.getElementById('msg').textContent = \
                         'Wooju를 시작하지 못했어요. 앱을 다시 열어 주세요. \
                         문제가 계속되면 ~/Library/Logs/Wooju/server.log 를 보내 주세요.'",
                    );
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to start Wooju")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Server>() {
                    if let Some(child) = state.0.lock().ok().and_then(|mut c| c.take()) {
                        let _ = child.kill();
                    }
                }
            }
        });
}
