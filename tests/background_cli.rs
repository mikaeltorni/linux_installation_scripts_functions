//! Public checks for tmux-background-output record and start.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::process::{Command, Stdio};
use std::io::Write;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_tmux-background-output"))
}

fn record(path: &std::path::Path, payload: &[u8]) -> std::process::Output {
    let mut child = bin().args(["record", "--file", path.to_str().unwrap()]).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    child.stdin.take().unwrap().write_all(payload).unwrap();
    child.wait_with_output().unwrap()
}

fn decompress(path: &std::path::Path) -> Vec<u8> {
    let output = Command::new("gzip").args(["-dc", path.to_str().unwrap()]).output().unwrap();
    assert_eq!(output.status.code(), Some(0), "{}", String::from_utf8_lossy(&output.stderr));
    output.stdout
}

#[test]
fn record_preserves_bytes_and_two_runs_match() {
    let dir = std::env::temp_dir().join(format!("tmux-background-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let payload = b"hello demo\n".iter().copied().chain(0u8..=31).collect::<Vec<_>>();
    let mut archives = Vec::new();
    for index in 0..2 {
        let path = dir.join(format!("record-{index}.gz"));
        let output = record(&path, &payload);
        assert_eq!(output.status.code(), Some(0), "{}", String::from_utf8_lossy(&output.stderr));
        assert_eq!(output.stdout, b"");
        assert_eq!(decompress(&path), payload);
        assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
        archives.push(fs::read(&path).unwrap());
    }
    assert_eq!(archives[0], archives[1]);
    let empty = dir.join("empty.gz");
    let output = record(&empty, b"");
    assert_eq!(output.status.code(), Some(0));
    assert_eq!(fs::read(&empty).unwrap(), hex_bytes("1f8b080000000000040303000000000000000000"));
    let appended = dir.join("append.gz");
    assert_eq!(record(&appended, b"ab").status.code(), Some(0));
    assert_eq!(record(&appended, b"cd").status.code(), Some(0));
    assert_eq!(decompress(&appended), b"abcd");
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn malformed_commands_exit_before_creating_archives() {
    let dir = std::env::temp_dir().join(format!("tmux-background-reject-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let file = dir.join("x.gz");
    let cases = [
        vec![],
        vec!["unknown".to_string()],
        vec!["record".to_string()],
        vec!["record".into(), "--file".into(), file.display().to_string(), "extra".into()],
        vec!["start".into(), "--target".into(), "demo:app".into()],
        vec!["start".into(), "--target".into(), "nosep".into(), "--archive-dir".into(), dir.display().to_string(), "--".into(), "true".into()],
    ];
    for args in cases {
        let output = bin().args(&args).output().unwrap();
        assert_ne!(output.status.code(), Some(0), "{args:?}");
        assert!(fs::read_dir(&dir).unwrap().next().is_none(), "{args:?}");
    }
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn start_archives_markers_and_bounds_history() {
    let dir = std::env::temp_dir().join(format!("tmux-background-start-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let socket = dir.join("tmux.sock");
    let archive = dir.join("archive");
    fs::create_dir_all(&archive).unwrap();
    let _ = Command::new("tmux").args(["-S", socket.to_str().unwrap(), "kill-server"]).output();
    let created = Command::new("tmux").args(["-S", socket.to_str().unwrap(), "new-session", "-d", "-s", "demo", "-n", "app", "printf 'old-marker\\n'; sleep 1000"]).status().unwrap();
    assert!(created.success());
    assert!(Command::new("tmux").args(["-S", socket.to_str().unwrap(), "set-window-option", "-t", "demo:app", "history-limit", "5000"]).status().unwrap().success());
    std::thread::sleep(std::time::Duration::from_millis(200));
    let output = bin().env("TMUX", format!("{},0,0", socket.display())).args(["start", "--target", "demo:app", "--archive-dir", archive.to_str().unwrap(), "--cwd", dir.to_str().unwrap(), "--", "bash", "-c", "printf 'fresh-end\\n'; sleep 1000"]).output().unwrap();
    assert_eq!(output.status.code(), Some(0), "{} {}", String::from_utf8_lossy(&output.stderr), String::from_utf8_lossy(&output.stdout));
    let mut collected = Vec::new();
    for _ in 0..40 {
        collected.clear();
        for entry in fs::read_dir(&archive).unwrap() {
            let path = entry.unwrap().path();
            if path.extension().and_then(|ext| ext.to_str()) == Some("gz") {
                collected.extend(decompress(&path));
            }
        }
        if collected.windows(b"fresh-end".len()).any(|window| window == b"fresh-end") && collected.windows(b"old-marker".len()).any(|window| window == b"old-marker") {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    let text = String::from_utf8_lossy(&collected);
    assert!(text.contains("old-marker"), "{text}");
    assert!(text.contains("fresh-end"), "{text}");
    let limit = Command::new("tmux").args(["-S", socket.to_str().unwrap(), "display-message", "-p", "-t", "demo:app", "#{history_limit}"]).output().unwrap();
    assert_eq!(String::from_utf8_lossy(&limit.stdout).trim(), "2000");
    let _ = Command::new("tmux").args(["-S", socket.to_str().unwrap(), "kill-server"]).output();
    let _ = fs::remove_dir_all(dir);
}

fn hex_bytes(text: &str) -> Vec<u8> {
    (0..text.len()).step_by(2).map(|index| u8::from_str_radix(&text[index..index + 2], 16).unwrap()).collect()
}
