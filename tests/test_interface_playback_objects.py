import unittest

from testing.python.interface_playback import InterfacePlayback


def identity(value):
  return value


class Box:
  pass


class InterfacePlaybackObjectTests(unittest.TestCase):
  def test_custom_object_attributes_record_and_replay(self):
    recorder = InterfacePlayback()
    box = Box()
    box.mode = "old"

    def real():
      box.mode = "new"

    recorder.record(identity, real, box, "advance")

    replay_box = Box()
    replay_box.mode = "old"
    InterfacePlayback(recorder._recording).replay(
      replay_box,
      "advance",
    )
    self.assertEqual(replay_box.mode, "new")

  def test_filter_can_ignore_custom_object_attribute(self):
    recorder = InterfacePlayback()
    box = Box()
    box.mode = "same"
    box.noise = 1

    def real():
      box.noise = 2

    def keep_mode(interaction):
      interaction["call"]["obj"].pop("noise")
      interaction["before"]["obj"].pop("noise")
      interaction["after"]["obj"].pop("noise")
      return interaction

    recorder.record(keep_mode, real, box, "touch")

    candidate = Box()
    candidate.mode = "same"
    candidate.noise = 99

    def changed_noise():
      candidate.noise = 100

    InterfacePlayback(recorder._recording).test(
      changed_noise,
      candidate,
      "touch",
    )


if __name__ == "__main__":
  unittest.main()
