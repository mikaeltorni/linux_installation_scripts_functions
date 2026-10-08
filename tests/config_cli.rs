//! Public checks for installation-config export, apply, diff, and roundtrip.

use std::fs;
use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_installation-config"))
}

fn write(dir: &std::path::Path, name: &str, text: &str) -> std::path::PathBuf {
    let path = dir.join(name);
    fs::write(&path, text).unwrap();
    path
}

#[test]
fn export_apply_diff_and_roundtrip_match_python() {
    let dir = std::env::temp_dir().join(format!("installation-config-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let state = "scope=standalone\nrepo_name=demo\nrepo:demo:1\ncomp\tdemo\talpha\t1\t0\t0\t0\t0\t0\t2\tSuper+A\ncomp\tdemo\tbeta\t0\t1\t0\t0\t0\t0\t\t\n";
    let state_path = write(&dir, "state.txt", state);
    let export = bin().args(["export", "--state-file", state_path.to_str().unwrap()]).output().unwrap();
    assert_eq!(export.status.code(), Some(0), "{}", String::from_utf8_lossy(&export.stderr));
    let expected = "{\n  \"components\": {\n    \"alpha\": {\n      \"config_value\": \"Super+A\",\n      \"favorite\": 0,\n      \"monitor\": 2,\n      \"on\": 1,\n      \"startup\": 0,\n      \"sticky\": 0,\n      \"uninstall\": 0,\n      \"workspace\": 0\n    },\n    \"beta\": {\n      \"config_value\": \"\",\n      \"favorite\": 0,\n      \"on\": 0,\n      \"startup\": 0,\n      \"sticky\": 0,\n      \"uninstall\": 1,\n      \"workspace\": 0\n    }\n  },\n  \"repo\": \"demo\",\n  \"schema_version\": 1,\n  \"scope\": \"standalone\"\n}\n";
    assert_eq!(String::from_utf8_lossy(&export.stdout), expected);
    let again = bin().args(["export", "--state-file", state_path.to_str().unwrap()]).output().unwrap();
    assert_eq!(again.stdout, export.stdout);
    let applied = dir.join("applied.txt");
    let apply = bin().args(["apply", "--config", &write(&dir, "export.json", expected).to_string_lossy(), "--state-file", applied.to_str().unwrap()]).output().unwrap();
    assert_eq!(apply.status.code(), Some(0), "{}", String::from_utf8_lossy(&apply.stderr));
    assert_eq!(fs::read_to_string(&applied).unwrap(), state);
    let base = write(&dir, "base.json", "{\n  \"components\": {\"alpha\": {\"monitor\": 1, \"on\": 1}},\n  \"repo\": \"demo\",\n  \"schema_version\": 1,\n  \"scope\": \"standalone\"\n}\n");
    let curr = write(&dir, "curr.json", "{\n  \"components\": {\"alpha\": {\"config_value\": \"Super+B\", \"monitor\": 2, \"on\": 0}},\n  \"repo\": \"demo\",\n  \"schema_version\": 1,\n  \"scope\": \"standalone\"\n}\n");
    let diff = bin().args(["diff", "--baseline", base.to_str().unwrap(), "--current", curr.to_str().unwrap()]).output().unwrap();
    assert_eq!(diff.status.code(), Some(0));
    assert_eq!(String::from_utf8_lossy(&diff.stdout), "demo/alpha selected: 1 -> 0\ndemo/alpha monitor: 1 -> 2\ndemo/alpha config_value: '' -> 'Super+B'\n");
    let empty = write(&dir, "empty.json", "{\"components\": {}, \"schema_version\": 1, \"scope\": \"standalone\"}\n");
    let empty_status = bin().args(["is-empty", "--config", empty.to_str().unwrap()]).status().unwrap();
    assert_eq!(empty_status.code(), Some(0));
    let populated = bin().args(["is-empty", "--config", base.to_str().unwrap()]).status().unwrap();
    assert_eq!(populated.code(), Some(1));
    let scope = bin().args(["scope", "--config", empty.to_str().unwrap()]).output().unwrap();
    assert_eq!(String::from_utf8_lossy(&scope.stdout), "standalone\n");
    let ids = bin().args(["component-ids", "--config", base.to_str().unwrap()]).output().unwrap();
    assert_eq!(String::from_utf8_lossy(&ids.stdout).trim(), "alpha");
    let roundtrip = bin().args(["roundtrip", "--state-file", state_path.to_str().unwrap()]).output().unwrap();
    assert_eq!(roundtrip.status.code(), Some(0), "{}", String::from_utf8_lossy(&roundtrip.stderr));
    let _ = fs::remove_dir_all(dir);
}
