import json
from pathlib import Path
import tempfile
import unittest

from testing.python.interface_playback import (
  Free,
  InterfaceGrammarError,
  InterfaceMismatch,
  InterfacePlayback,
  Unchanged,
)


def identity(value):
  return value


class Box:
  pass


class InterfacePlaybackTests(unittest.TestCase):
  def test_free_function_record_save_load_test_and_replay(self):
    recorder = InterfacePlayback()
    values = [1]

    def real():
      values.append(2)
      return "ok"

    self.assertEqual(
      recorder.record(identity, real, Free, "extend", values),
      "ok",
    )
    self.assertEqual(values, [1, 2])

    with tempfile.TemporaryDirectory() as temp:
      path = Path(temp) / "recording.json"
      recorder.save(path)
      data = json.loads(path.read_text(encoding="utf-8"))
      self.assertEqual(len(data), 1)
      self.assertEqual(data[0]["call"]["obj"], {"$free": True})

      target = [1]
      replay = InterfacePlayback(path)
      self.assertEqual(replay.replay(Free, "extend", target), "ok")
      self.assertEqual(target, [1, 2])

      target = [1]
      verifier = InterfacePlayback(path)

      def same():
        target.append(2)
        return "ok"

      self.assertEqual(
        verifier.test(same, Free, "extend", target),
        "ok",
      )

  def test_member_receiver_and_keyword_mutations_round_trip(self):
    recorder = InterfacePlayback()
    receiver = {"mode": "old"}
    option = ["a"]

    def real():
      receiver["mode"] = "new"
      option.append("b")
      return receiver

    result = recorder.record(
      identity,
      real,
      receiver,
      "advance",
      option=option,
    )
    self.assertIs(result, receiver)

    receiver2 = {"mode": "old"}
    option2 = ["a"]
    replay = InterfacePlayback(recorder._recording)
    result2 = replay.replay(
      receiver2,
      "advance",
      option=option2,
    )
    self.assertIs(result2, receiver2)
    self.assertEqual(receiver2, {"mode": "new"})
    self.assertEqual(option2, ["a", "b"])

  def test_test_stops_at_first_consequential_mismatch(self):
    recording = [{
      "call": {"fn_name": "f", "obj": {"$free": True}},
      "before": {"args": [1], "kwargs": {}},
      "after": {"args": [1], "kwargs": {}},
      "result": {"return": 2},
    }]
    playback = InterfacePlayback(recording)

    with self.assertRaisesRegex(
      InterfaceMismatch,
      r"result\.return: expected 2, actual 3",
    ):
      playback.test(lambda: 3, Free, "f", 1)

    with self.assertRaisesRegex(
      InterfaceMismatch,
      r"result\.return: expected 2, actual 3",
    ):
      playback.test(lambda: 3, Free, "f", 1)

  def test_expected_exception_is_verified_and_reraised(self):
    recorder = InterfacePlayback()

    def fail():
      raise ValueError("bad")

    with self.assertRaisesRegex(ValueError, "bad"):
      recorder.record(identity, fail, Free, "fail")

    playback = InterfacePlayback(recorder._recording)
    with self.assertRaisesRegex(ValueError, "bad"):
      playback.test(fail, Free, "fail")

    replay = InterfacePlayback(recorder._recording)
    with self.assertRaisesRegex(ValueError, "bad"):
      replay.replay(Free, "fail")

  def test_logical_aliasing_and_equal_distinct_objects(self):
    recorder = InterfacePlayback()
    left = []
    right = []

    recorder.record(
      identity,
      lambda: left,
      Free,
      "choose",
      left,
      left,
      right,
    )

    replay = InterfacePlayback(recorder._recording)
    same = []
    distinct = []
    self.assertIs(
      replay.replay(Free, "choose", same, same, distinct),
      same,
    )

    invalid = InterfacePlayback(recorder._recording)
    with self.assertRaisesRegex(
      InterfaceMismatch,
      "expected logical object",
    ):
      invalid.replay(Free, "choose", [], [], [])

  def test_unchanged_scalar_and_selective_object_state(self):
    box = Box()
    box.mode = "same"
    box.other = "old"
    recording = [{
      "call": {
        "fn_name": "touch",
        "obj": {"$new": "box_1", "$type": f"{__name__}.Box"},
      },
      "before": {
        "obj": {
          "$ref": "box_1",
          "mode": "same",
          "other": "old",
        },
        "args": [],
        "kwargs": {},
      },
      "after": {
        "obj": {"$unchanged": {"keys": ["mode"]}},
        "args": [],
        "kwargs": {},
      },
      "result": {"return": None},
    }]

    playback = InterfacePlayback(recording)

    def real():
      box.other = "changed"

    playback.test(real, box, "touch")
    self.assertEqual(box.mode, "same")
    self.assertEqual(box.other, "changed")

  def test_python_sentinels_normalize_for_in_memory_load(self):
    recording = [{
      "call": {"fn_name": "f", "obj": Free},
      "before": {"args": [], "kwargs": {}},
      "after": {"args": [], "kwargs": {}},
      "result": {"return": None},
    }]
    playback = InterfacePlayback(recording)
    self.assertIsNone(playback.replay(Free, "f"))

    unchanged = Unchanged(keys=["mode"])
    self.assertEqual(unchanged.keys, ("mode",))

  def test_rejects_unknown_reserved_metadata_and_nonfinite_float(self):
    base = {
      "call": {"fn_name": "f", "obj": {"$free": True}},
      "before": {"args": [], "kwargs": {}},
      "after": {"args": [], "kwargs": {}},
      "result": {"return": None},
    }
    bad = json.loads(json.dumps(base))
    bad["result"]["return"] = {"$wat": True}
    with self.assertRaisesRegex(InterfaceGrammarError, "unknown reserved"):
      InterfacePlayback([bad])

    bad = json.loads(json.dumps(base))
    bad["result"]["return"] = float("nan")
    with self.assertRaisesRegex(InterfaceGrammarError, "non-finite"):
      InterfacePlayback([bad])

  def test_member_receiver_introduced_before_same_object_argument(self):
    recorder = InterfacePlayback()
    receiver = []

    recorder.record(
      identity,
      lambda: None,
      receiver,
      "same",
      receiver,
    )

    interaction = recorder._recording[0]
    self.assertEqual(interaction["call"]["obj"]["$new"], "list_1")
    self.assertEqual(
      interaction["before"]["args"][0],
      {"$ref": "list_1"},
    )

  def test_forward_reference_is_rejected_during_load(self):
    recording = [{
      "call": {"fn_name": "f", "obj": {"$free": True}},
      "before": {
        "args": [{"$ref": "later"}],
        "kwargs": {},
      },
      "after": {
        "args": [{"$new": "later", "$type": "builtins.list", "items": []}],
        "kwargs": {},
      },
      "result": {"return": None},
    }]
    with self.assertRaisesRegex(
      InterfaceGrammarError,
      "forward or unknown logical object reference",
    ):
      InterfacePlayback(recording)

  def test_nested_unchanged_is_preserved_during_replay(self):
    recording = [{
      "call": {"fn_name": "f", "obj": {"$free": True}},
      "before": {
        "args": [{
          "$new": "dict_1",
          "$type": "builtins.dict",
          "items": {"keep": 1, "change": 2},
        }],
        "kwargs": {},
      },
      "after": {
        "args": [{
          "$ref": "dict_1",
          "items": {
            "keep": {"$unchanged": True},
            "change": 3,
          },
        }],
        "kwargs": {},
      },
      "result": {"return": None},
    }]
    target = {"keep": 1, "change": 2}
    InterfacePlayback(recording).replay(Free, "f", target)
    self.assertEqual(target, {"keep": 1, "change": 3})

  def test_filter_can_remove_irrelevant_change_with_unchanged(self):
    recorder = InterfacePlayback()
    target = {"stable": 1, "noise": 10}

    def real():
      target["noise"] = 11

    def keep_stable(interaction):
      after_spec = interaction["after"]["args"][0]
      after_spec.pop("keys")
      after_items = after_spec["items"]
      after_items["stable"] = Unchanged
      after_items.pop("noise")
      before_spec = interaction["before"]["args"][0]
      before_spec.pop("keys")
      before_spec["items"].pop("noise")
      return interaction

    recorder.record(keep_stable, real, Free, "f", target)

    candidate = {"stable": 1, "noise": 99}

    def changed_noise():
      candidate["noise"] = 100

    InterfacePlayback(recorder._recording).test(
      changed_noise,
      Free,
      "f",
      candidate,
    )

  def test_new_custom_return_object_replays_with_logical_type(self):
    recorder = InterfacePlayback()

    def real():
      return Box()

    result = recorder.record(identity, real, Free, "make")
    self.assertIsInstance(result, Box)

    replayed = InterfacePlayback(recorder._recording).replay(
      Free,
      "make",
    )
    self.assertIsInstance(replayed, Box)

  def test_file_load_rejects_truncated_json(self):
    with tempfile.TemporaryDirectory() as temp:
      path = Path(temp) / "bad.json"
      path.write_text('[{"call":', encoding="utf-8")
      with self.assertRaisesRegex(
        InterfaceGrammarError,
        "malformed or truncated|truncated",
      ):
        InterfacePlayback(path)

  def test_large_file_is_valid_incremental_json_array(self):
    recorder = InterfacePlayback()
    for value in range(1000):
      recorder.record(
        identity,
        lambda value=value: value,
        Free,
        "value",
      )

    with tempfile.TemporaryDirectory() as temp:
      path = Path(temp) / "many.json"
      recorder.save(path)
      playback = InterfacePlayback(path)
      for value in range(1000):
        self.assertEqual(playback.replay(Free, "value"), value)


if __name__ == "__main__":
  unittest.main()
