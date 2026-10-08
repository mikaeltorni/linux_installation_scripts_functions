//! Public checks for hotkey-capture accelerator commands.

use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_hotkey-capture"))
}

fn run(args: &[&str]) -> (i32, String, String) {
    let output = bin().args(args).output().unwrap();
    (
        output.status.code().unwrap_or(1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    )
}

#[test]
fn accel_display_and_modifier_match_python_twice() {
    let (code, out, err) = run(&["accel", "super+shift+s"]);
    assert_eq!(code, 0, "{err}");
    assert_eq!(out, "<Super><Shift>s\n");
    let (code2, out2, _) = run(&["accel", "super+shift+s"]);
    assert_eq!(code2, 0);
    assert_eq!(out, out2);
    assert_eq!(run(&["accel", "control+t"]).1, "<Control>t\n");
    assert_eq!(run(&["accel", "alt+super+w"]).1, "<Alt><Super>w\n");
    let (bad, stdout, stderr) = run(&["accel", "super+"]);
    assert_eq!(bad, 2);
    assert_eq!(stdout, "");
    assert!(stderr.contains("malformed hotkey 'super+': empty modifier or key"), "{stderr}");
    assert_eq!(run(&["display", "<Control><Super>w"]).1, "Ctrl+Super+W\n");
    assert_eq!(run(&["modifier", "shift"]).1, "Shift\n");
    assert_eq!(run(&["modifier", "ctrl"]).1, "Control\n");
    let (mod_bad, _, mod_err) = run(&["modifier", "super+shift"]);
    assert_eq!(mod_bad, 2);
    assert!(mod_err.contains("enter exactly one modifier"), "{mod_err}");
    assert_eq!(run(&["add-modifier", "<Super>w", "Shift"]).1, "<Super><Shift>w\n");
    let (dup, _, dup_err) = run(&["add-modifier", "<Super>w", "Super"]);
    assert_eq!(dup, 2);
    assert!(dup_err.contains("Super is already part of Super+W"), "{dup_err}");
}

#[test]
fn config_round_trip_preserves_other_lines() {
    let dir = std::env::temp_dir().join(format!("hotkey-capture-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("fields.env");
    fs::write(&path, "OTHER=1\n").unwrap();
    let missing = run(&["config-get", path.to_str().unwrap(), "HOTKEY", "<Super>s"]);
    assert_eq!(missing.0, 0);
    assert_eq!(missing.1, "<Super>s\n");
    let saved = run(&["config-set", path.to_str().unwrap(), "HOTKEY", "<Super>s"]);
    assert_eq!(saved.0, 0, "{}", saved.2);
    assert_eq!(fs::read_to_string(&path).unwrap(), "OTHER=1\nHOTKEY=<Super>s\n");
    assert_eq!(fs::metadata(&path).unwrap().permissions().mode() & 0o777, 0o600);
    let stored = run(&["config-get", path.to_str().unwrap(), "HOTKEY", "<Super>x"]);
    assert_eq!(stored.1, "<Super>s\n");
    let again = run(&["config-set", path.to_str().unwrap(), "HOTKEY", "<Super>s"]);
    assert_eq!(again.0, 0);
    assert_eq!(fs::read_to_string(&path).unwrap(), "OTHER=1\nHOTKEY=<Super>s\n");
    let _ = fs::remove_dir_all(dir);
}
