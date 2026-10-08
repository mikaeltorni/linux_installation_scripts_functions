//! Public checks for the repeatable-fields command.

use std::process::{Command, Stdio};
use std::io::Write;

fn run(script: &str) -> (i32, String, String) {
    let mut child = Command::new(env!("CARGO_BIN_EXE_repeatable-fields"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("run repeatable-fields");
    child.stdin.take().unwrap().write_all(script.as_bytes()).unwrap();
    let output = child.wait_with_output().unwrap();
    (
        output.status.code().unwrap_or(1),
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
    )
}

#[test]
fn canonical_edits_match_the_python_row_contract_twice() {
    let script = r#"{"commands":[["add",{"source":"first"}],["set",1,"env","USE_FIRST"],["toggle",1,"startup"],["set-group",1,3],["set",2,"source","missing"],["toggle",0,"startup"]]}"#;
    let expected = "{\"results\": [1, true, true, true, false, false], \"items\": [{\"source\": \"first\", \"env\": \"USE_FIRST\", \"startup\": true, \"group\": 3}]}\n";
    let mut runs = Vec::new();
    for _ in 0..2 {
        let (code, out, err) = run(script);
        assert_eq!(code, 0, "{err}");
        runs.push(out);
    }
    assert_eq!(runs[0], expected);
    assert_eq!(runs[0], runs[1]);
}

#[test]
fn negative_group_is_rejected_without_a_result() {
    let script = r#"{"commands":[["add",{"source":"first"}],["set-group",1,-1]]}"#;
    let (code, out, err) = run(script);
    assert_eq!(code, 1);
    assert_eq!(out, "");
    assert!(err.contains("group must be zero or greater"), "{err}");
}
