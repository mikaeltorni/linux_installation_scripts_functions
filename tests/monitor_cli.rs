//! Public checks for monitor-layout list and count.

use std::fs;
use std::process::Command;

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_monitor-layout"))
}

#[test]
fn simplified_layout_matches_the_python_rows() {
    let dir = std::env::temp_dir().join(format!("monitor-layout-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let base = r#"{"monitors":[{"connector":"DP-0","name":"Left","modes":[{"width":3840,"height":2160,"current":true}]},{"connector":"HDMI-0","name":"Right","modes":[{"width":3840,"height":2160,"current":true}]}],"logical":[{"x":0,"y":0,"scale":1,"transform":0,"primary":false,"connectors":["DP-0"]},{"x":3840,"y":100,"scale":1,"transform":0,"primary":true,"connectors":["HDMI-0"]}]}"#;
    let path = dir.join("state.json");
    fs::write(&path, base).unwrap();
    let expected = "1\tDP-0\tLeft\t0\t0\t0\t3840\t2160\n2\tHDMI-0\tRight\t1\t3840\t100\t3840\t2160\n";
    let mut runs = Vec::new();
    for _ in 0..2 {
        let output = bin().args(["list", "--state", path.to_str().unwrap()]).output().unwrap();
        assert_eq!(output.status.code(), Some(0), "{}", String::from_utf8_lossy(&output.stderr));
        runs.push(String::from_utf8_lossy(&output.stdout).to_string());
    }
    assert_eq!(runs[0], expected);
    assert_eq!(runs[0], runs[1]);
    let rotated = base.replace("\"transform\":0,\"primary\":true", "\"transform\":1,\"primary\":true");
    fs::write(&path, rotated).unwrap();
    let output = bin().args(["list", "--state", path.to_str().unwrap()]).output().unwrap();
    assert_eq!(String::from_utf8_lossy(&output.stdout), "1\tDP-0\tLeft\t0\t0\t0\t3840\t2160\n2\tHDMI-0\tRight\t1\t3840\t100\t2160\t3840\n");
    let scaled = base.replace("\"scale\":1,\"transform\":0,\"primary\":true", "\"scale\":2,\"transform\":0,\"primary\":true");
    fs::write(&path, scaled).unwrap();
    let output = bin().args(["count", "--state", path.to_str().unwrap()]).output().unwrap();
    assert_eq!(output.status.code(), Some(0));
    assert_eq!(String::from_utf8_lossy(&output.stdout).trim(), "2");
    let listed = bin().args(["list", "--state", path.to_str().unwrap()]).output().unwrap();
    assert!(String::from_utf8_lossy(&listed.stdout).contains("1920\t1080"), "{}", String::from_utf8_lossy(&listed.stdout));
    let _ = fs::remove_dir_all(dir);
}

#[test]
fn busctl_variant_names_and_rotation_match_python_geometry() {
    let dir = std::env::temp_dir().join(format!("monitor-layout-busctl-{}", std::process::id()));
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    let document = r#"{"type":"u","data":[1,[[["HDMI-0","SAM","LU","H"],[["mode",3840,2160,60,1,[1],{"is-current":{"type":"b","data":true}}]],{"display-name":{"type":"s","data":"Samsung Electric Company 29\""}}]],[[3840,1380,1,3,false,[["HDMI-0","SAM","LU","H"]],{}]],{}]}"#;
    let path = dir.join("busctl.json");
    fs::write(&path, document).unwrap();
    let output = bin().args(["list", "--busctl", path.to_str().unwrap()]).output().unwrap();
    assert_eq!(output.status.code(), Some(0), "{}", String::from_utf8_lossy(&output.stderr));
    assert_eq!(String::from_utf8_lossy(&output.stdout), "1\tHDMI-0\tSamsung Electric Company 29\"\t0\t3840\t1380\t2160\t3840\n");
    let _ = fs::remove_dir_all(dir);
}
