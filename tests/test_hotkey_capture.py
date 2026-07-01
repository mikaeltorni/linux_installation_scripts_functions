#!/usr/bin/env python3
"""Unit tests for the shared hotkey_capture engine (pure logic only).

The evdev capture driver is a thin best-effort I/O layer and is not exercised
here; every state-machine, conversion and conflict rule the goal specifies is.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hotkey_capture import (  # noqa: E402
    HotkeyBinding,
    add_modifier_to_accelerator,
    describe_conflicts,
    display_accelerator,
    find_conflicts,
    normalize_modifier,
    normalize_accelerator,
    to_gnome_accelerator,
    token_for_evdev_key,
)


class HotkeyBindingTests(unittest.TestCase):
    def test_modifiers_accumulate_in_canonical_order(self):
        b = HotkeyBinding()
        # Press out of canonical order: Shift then Super then Control.
        self.assertEqual(b.add_modifier("Shift"), "added")
        self.assertEqual(b.add_modifier("Super"), "added")
        self.assertEqual(b.add_modifier("Control"), "added")
        # Canonical order is Control, Alt, Super, Shift.
        self.assertEqual(b.modifiers, ["Control", "Super", "Shift"])

    def test_duplicate_modifier_ignored(self):
        b = HotkeyBinding()
        self.assertEqual(b.add_modifier("Super"), "added")
        self.assertEqual(b.add_modifier("Super"), "duplicate")
        self.assertEqual(b.modifiers, ["Super"])

    def test_only_one_key_replaces(self):
        b = HotkeyBinding()
        self.assertEqual(b.set_key("s"), "added")
        self.assertEqual(b.set_key("z"), "replaced")
        self.assertEqual(b.key, "z")

    def test_back_removes_most_recent_input(self):
        b = HotkeyBinding()
        b.add_modifier("Super")
        b.add_modifier("Shift")
        b.set_key("s")
        self.assertEqual(b.back(), ("key", "s"))
        self.assertIsNone(b.key)
        self.assertEqual(b.back(), ("mod", "Shift"))
        self.assertEqual(b.modifiers, ["Super"])
        self.assertEqual(b.back(), ("mod", "Super"))
        self.assertTrue(b.is_empty())
        self.assertIsNone(b.back())

    def test_display_plus_format(self):
        b = HotkeyBinding()
        b.add_modifier("Super")
        b.add_modifier("Shift")
        b.set_key("s")
        self.assertEqual(b.display(), "Super+Shift+S")
        self.assertEqual(HotkeyBinding().display(), "(none)")

    def test_control_displays_as_ctrl(self):
        b = HotkeyBinding()
        b.add_modifier("Control")
        b.set_key("t")
        self.assertEqual(b.display(), "Ctrl+T")

    def test_to_accelerator(self):
        b = HotkeyBinding()
        b.add_modifier("Shift")
        b.add_modifier("Super")
        b.set_key("s")
        self.assertEqual(b.to_accelerator(), "<Super><Shift>s")

    def test_to_accelerator_requires_key(self):
        b = HotkeyBinding()
        b.add_modifier("Super")
        with self.assertRaises(ValueError):
            b.to_accelerator()

    def test_is_complete(self):
        b = HotkeyBinding()
        self.assertFalse(b.is_complete())
        b.add_modifier("Super")
        self.assertFalse(b.is_complete())
        b.set_key("z")
        self.assertTrue(b.is_complete())


class MouseModeTests(unittest.TestCase):
    def test_mouse_trigger_to_trigger(self):
        b = HotkeyBinding(mouse_mode=True)
        b.add_modifier("Control")
        b.set_key("MouseBack")
        self.assertEqual(b.to_trigger(), (["Control"], "BTN_BACK"))

    def test_mouse_trigger_has_no_accelerator(self):
        b = HotkeyBinding(mouse_mode=True)
        b.add_modifier("Control")
        b.set_key("MouseForward")
        with self.assertRaises(ValueError):
            b.to_accelerator()

    def test_keyboard_fb_stand_in_for_mouse_buttons(self):
        # In mouse mode the keyboard F/B stand in for Forward/Back buttons.
        self.assertEqual(token_for_evdev_key("KEY_F", mouse_mode=True), ("key", "MouseForward"))
        self.assertEqual(token_for_evdev_key("KEY_B", mouse_mode=True), ("key", "MouseBack"))
        self.assertEqual(token_for_evdev_key("BTN_BACK", mouse_mode=True), ("key", "MouseBack"))
        self.assertEqual(token_for_evdev_key("BTN_FORWARD", mouse_mode=True), ("key", "MouseForward"))

    def test_fb_are_normal_letters_without_mouse_mode(self):
        self.assertEqual(token_for_evdev_key("KEY_F"), ("key", "f"))
        self.assertEqual(token_for_evdev_key("KEY_B"), ("key", "b"))


class TokenMappingTests(unittest.TestCase):
    def test_modifier_names(self):
        self.assertEqual(token_for_evdev_key("KEY_LEFTCTRL"), ("mod", "Control"))
        self.assertEqual(token_for_evdev_key("KEY_RIGHTMETA"), ("mod", "Super"))
        self.assertEqual(token_for_evdev_key("KEY_LEFTSHIFT"), ("mod", "Shift"))
        self.assertEqual(token_for_evdev_key("KEY_RIGHTALT"), ("mod", "Alt"))

    def test_letter_key(self):
        self.assertEqual(token_for_evdev_key("KEY_Z"), ("key", "z"))

    def test_named_key(self):
        self.assertEqual(token_for_evdev_key("KEY_SYSRQ"), ("key", "Print"))
        self.assertEqual(token_for_evdev_key("KEY_SPACE"), ("key", "space"))

    def test_unbindable_key(self):
        self.assertIsNone(token_for_evdev_key("KEY_UNKNOWN"))


class AcceleratorConversionTests(unittest.TestCase):
    def test_friendly_to_gtk(self):
        self.assertEqual(to_gnome_accelerator("super+shift+s"), "<Super><Shift>s")
        self.assertEqual(to_gnome_accelerator("control+t"), "<Control>t")
        self.assertEqual(to_gnome_accelerator("alt+super+w"), "<Alt><Super>w")

    def test_invalid_specs(self):
        for bad in ("", "control+", "alt++t", "+t"):
            with self.assertRaises(ValueError):
                to_gnome_accelerator(bad)

    def test_normalize_order_and_case_insensitive(self):
        self.assertEqual(
            normalize_accelerator("<Super><Alt>e"),
            normalize_accelerator("alt+super+E"),
        )

    def test_display_uses_friendly_multiple_modifier_format(self):
        self.assertEqual(display_accelerator("<Control><Super>w"), "Ctrl+Super+W")

    def test_modifier_field_accepts_exactly_one_modifier(self):
        self.assertEqual(normalize_modifier("shift"), "Shift")
        self.assertEqual(normalize_modifier("ctrl"), "Control")
        with self.assertRaises(ValueError):
            normalize_modifier("super+shift")

    def test_move_modifier_cannot_duplicate_switch_modifier(self):
        self.assertEqual(
            add_modifier_to_accelerator("<Super>w", "Shift"),
            "<Super><Shift>w",
        )
        with self.assertRaises(ValueError):
            add_modifier_to_accelerator("<Super>w", "Super")


class ConflictTests(unittest.TestCase):
    def test_find_conflicts_matches_regardless_of_order(self):
        candidates = [
            ("org.gnome.shell.keybindings show-screenshot-ui", "<Shift><Super>s"),
            ("org.gnome.desktop.wm.keybindings switch-to-workspace-1", "<Super>z"),
        ]
        hits = find_conflicts("super+shift+s", candidates)
        self.assertEqual(hits, [("org.gnome.shell.keybindings show-screenshot-ui", "<Shift><Super>s")])

    def test_no_conflict(self):
        candidates = [("x", "<Super>z")]
        self.assertEqual(find_conflicts("<Super>y", candidates), [])

    def test_describe_conflicts(self):
        lines = describe_conflicts([("some.schema key", "<Super>z")])
        self.assertEqual(len(lines), 1)
        self.assertIn("some.schema key", lines[0])
        self.assertIn("<Super>z", lines[0])
        self.assertIn("unbound", lines[0])


if __name__ == "__main__":
    unittest.main()
