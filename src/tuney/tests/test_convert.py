"""Audio conversion: the plan the user is shown, and the command beets runs."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tuney import config, library
from tuney.agents import activity, tools


class FakeItem:
    """Enough of a beets Item for the planner: an id, a format and a path."""

    def __init__(self, item_id, fmt="FLAC", path=None, album_id=None):
        self.id = item_id
        self.format = fmt
        self.path = os.fsencode(path) if path else b""
        self.album_id = album_id


def plan_for(items, fmt, **kwargs):
    with mock.patch.object(library, "search", return_value=items), \
         mock.patch.object(library, "all_items", return_value=items):
        return library.convert_plan("artist:x", fmt, **kwargs)


class IdsQueryTest(unittest.TestCase):
    def test_ids_are_ored_not_anded(self):
        self.assertEqual(library.ids_query([1, 2, 3]), "id:1 , id:2 , id:3")

    def test_a_single_id_needs_no_separator(self):
        self.assertEqual(library.ids_query([7]), "id:7")

    def test_an_empty_set_is_an_empty_query(self):
        self.assertEqual(library.ids_query([]), "")


class ConvertCommandTest(unittest.TestCase):
    def test_yes_is_always_passed(self):
        argv = library._convert_command("artist:x", "mp3", "/dest")
        self.assertIn("-y", argv)

    def test_export_does_not_keep_new(self):
        argv = library._convert_command("artist:x", "mp3", "/dest")
        self.assertNotIn("--keep-new", argv)

    def test_replace_keeps_new(self):
        argv = library._convert_command("artist:x", "mp3", "/dest", replace=True)
        self.assertIn("--keep-new", argv)

    def test_the_destination_is_always_given(self):
        argv = library._convert_command("artist:x", "mp3", "/dest", replace=True)
        self.assertEqual(argv[argv.index("-d") + 1], "/dest")

    def test_the_query_is_split_into_separate_arguments(self):
        argv = library._convert_command("artist:x year:2000", "mp3", "/dest")
        self.assertEqual(argv[-2:], ["artist:x", "year:2000"])

    def test_regex_flags_are_repaired_like_every_other_query(self):
        argv = library._convert_command("artist::^(?i)foo", "mp3", "/dest")
        self.assertIn("artist::(?i)^foo", argv)


class QueryArgvTest(unittest.TestCase):
    """The query the plan counts and the query beets converts must match."""

    def test_a_quoted_value_stays_one_term(self):
        self.assertEqual(library.query_argv('album:"Who Coppin"'),
                         ["album:Who Coppin"])

    def test_single_quotes_work_the_same_way(self):
        self.assertEqual(library.query_argv("album:'Who Coppin'"),
                         ["album:Who Coppin"])

    def test_the_argv_matches_what_the_planner_would_search(self):
        import shlex

        for query in ('album:"Who Coppin"', "artist:'Larry June' year:2026",
                      "album:Who Coppin", ""):
            self.assertEqual(library.query_argv(query), shlex.split(query),
                             query)

    def test_the_convert_argv_carries_the_quoted_album_intact(self):
        argv = library._convert_command('album:"Who Coppin"', "aac", "/out")
        self.assertEqual(argv[-1], "album:Who Coppin")

    def test_an_id_set_keeps_its_or_separators(self):
        argv = library.query_argv(library.ids_query([1, 2]))
        self.assertEqual(argv, ["id:1", ",", "id:2"])

    def test_an_unbalanced_quote_does_not_raise(self):
        self.assertEqual(library.query_argv("album:'unbalanced"),
                         ["album:'unbalanced"])


class QualityTierTest(unittest.TestCase):
    """Above all, raising quality must not turn a file that would have been
    copied into one that gets re-encoded."""

    def test_every_format_has_both_tiers(self):
        for fmt in library.CONVERT_FORMATS:
            for tier in library.CONVERT_QUALITIES:
                self.assertIn((fmt, tier), library.CONVERT_ENCODERS,
                              f"{fmt}/{tier} has no encoder command")

    def test_every_command_names_the_source_and_destination(self):
        for key, command in library.CONVERT_ENCODERS.items():
            self.assertIn("$source", command, key)
            self.assertIn("$dest", command, key)

    def test_lossy_best_is_a_higher_bitrate_than_normal(self):
        for fmt in ("mp3", "aac", "opus", "ogg"):
            self.assertNotEqual(library.CONVERT_ENCODERS[(fmt, "normal")],
                                library.CONVERT_ENCODERS[(fmt, "best")], fmt)

    def test_alac_offers_no_choice_because_it_has_none(self):
        self.assertFalse(library.quality_is_meaningful("alac"))

    def test_flac_tiers_differ_but_only_in_compression(self):
        self.assertTrue(library.quality_is_meaningful("flac"))
        self.assertTrue(library.is_lossless("flac"))

    def test_lossless_formats_are_described_as_identical_audio(self):
        for fmt in ("flac", "alac"):
            for tier in library.CONVERT_QUALITIES:
                self.assertIn("identical audio",
                              library.quality_summary(fmt, tier), (fmt, tier))

    def test_lossy_summaries_quote_a_bitrate(self):
        self.assertIn("320 kbps", library.quality_summary("mp3", "best"))
        self.assertIn("kbps", library.quality_summary("mp3", "normal"))

    def test_the_format_flag_stays_the_bare_format_name(self):
        """Passing `mp3_best` to -f would make beets compare it against a
        file's "MP3" and re-encode a track it should have copied."""
        with library._convert_config("mp3", "best") as config_path:
            argv = library._convert_command("artist:x", "mp3", "/dest",
                                            config_path=config_path)
        self.assertEqual(argv[argv.index("-f") + 1], "mp3")

    def test_the_chosen_tier_reaches_the_config_beets_reads(self):
        import yaml

        with library._convert_config("mp3", "best") as config_path:
            with open(config_path, encoding="utf-8") as handle:
                written = yaml.safe_load(handle)
            command = written["convert"]["formats"]["mp3"]["command"]
        self.assertIn(library.CONVERT_ENCODERS[("mp3", "best")], command)

    def test_the_container_extension_is_declared_for_m4a_formats(self):
        # Without it beets names the file `.aac`/`.alac`, which nothing plays.
        import yaml

        for fmt in ("aac", "alac"):
            with library._convert_config(fmt, "normal") as config_path:
                with open(config_path, encoding="utf-8") as handle:
                    written = yaml.safe_load(handle)
            self.assertEqual(written["convert"]["formats"][fmt]["extension"],
                             "m4a")

    def test_the_temp_config_is_cleaned_up(self):
        with library._convert_config("mp3", "best") as config_path:
            self.assertTrue(os.path.exists(config_path))
        self.assertFalse(os.path.exists(config_path))


class CoverArtTest(unittest.TestCase):
    """`-vn` strips the source's picture and beets' own embed step only covers
    art already downloaded to disk, so the wrapper has to be on every
    command."""

    def test_every_encoder_runs_through_the_art_preserving_wrapper(self):
        for fmt in library.CONVERT_FORMATS:
            for tier in library.CONVERT_QUALITIES:
                command = library._encoder_command(fmt, tier)
                self.assertIn("-m tuney.convert_encoder", command, (fmt, tier))
                self.assertIn(library.CONVERT_ENCODERS[(fmt, tier)], command)

    def test_the_wrapper_is_told_the_source_and_the_destination(self):
        argv = library._encoder_command("mp3", "normal").split()
        marker = argv.index("tuney.convert_encoder")
        self.assertEqual(argv[marker + 1:marker + 3], ["$source", "$dest"])

    def test_an_unknown_tier_has_no_command_at_all(self):
        # Rather than a wrapper around an empty ffmpeg invocation.
        self.assertIsNone(library._encoder_command("mp3", "louder"))

    def test_a_failed_encode_is_reported_before_art_is_attempted(self):
        from tuney import convert_encoder

        with mock.patch.object(convert_encoder.subprocess, "run",
                               return_value=mock.Mock(returncode=1)), \
             mock.patch.object(convert_encoder, "copy_art") as copy_art:
            status = convert_encoder.main(["src.flac", "out.mp3", "ffmpeg"])

        self.assertEqual(status, 1)
        copy_art.assert_not_called()

    def test_unreadable_art_does_not_fail_a_good_conversion(self):
        from tuney import convert_encoder

        convert_encoder.copy_art("/nonexistent/src.flac", "/nonexistent/out.mp3")


class RememberedQualityTest(unittest.TestCase):
    """The tier a conversion ran at becomes the default for the next one."""

    def setUp(self):
        from tuney.tui.Modals.ConvertModal import ConvertModal

        # Called unbound: the dialog needs a running app to instantiate, and
        # this method never touches `self`.
        self.remember = lambda fmt, tier: ConvertModal._remember_quality(
            None, fmt, tier)

        handle = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        # Never write the real settings file from a test run.
        patch = mock.patch.object(config, "config_file", Path(handle.name))
        patch.start()
        self.addCleanup(patch.stop)

        previous = config._config
        config._config = config.Config()
        self.addCleanup(setattr, config, "_config", previous)

    def test_the_tier_a_conversion_ran_at_becomes_the_default(self):
        self.remember("mp3", str(config.ConvertQuality.BEST))

        self.assertIs(config.get_config().convert_quality,
                      config.ConvertQuality.BEST)
        self.assertIs(config.Config.load().convert_quality,
                      config.ConvertQuality.BEST)

    def test_a_format_with_no_real_choice_leaves_the_default_alone(self):
        # The radio still holds a value for ALAC, but the user never chose it.
        config.get_config().convert_quality = config.ConvertQuality.BEST

        self.remember("alac", str(config.ConvertQuality.NORMAL))

        self.assertIs(config.get_config().convert_quality,
                      config.ConvertQuality.BEST)

    def test_the_base_config_is_preserved_not_replaced(self):
        import yaml

        with library._convert_config("mp3", "best") as config_path:
            with open(config_path, encoding="utf-8") as handle:
                written = yaml.safe_load(handle)
        self.assertIn("plugins", written)
        self.assertIn("convert", written["plugins"])


class ConvertPlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def real_file(self, name, size=1024):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as handle:
            handle.write(b"\0" * size)
        return path

    def test_files_already_in_the_target_format_are_not_re_encoded(self):
        items = [FakeItem(1, "MP3", self.real_file("a.mp3")),
                 FakeItem(2, "FLAC", self.real_file("b.flac"))]
        plan = plan_for(items, "mp3")
        self.assertEqual(plan["transcode"], 1)
        self.assertEqual(plan["skipped"], 1)

    def test_force_re_encodes_even_matching_formats(self):
        items = [FakeItem(1, "MP3", self.real_file("a.mp3"))]
        plan = plan_for(items, "mp3", force=True)
        self.assertEqual(plan["transcode"], 1)
        self.assertEqual(plan["skipped"], 0)

    def test_a_missing_file_is_unreachable_not_convertible(self):
        items = [FakeItem(1, "FLAC", os.path.join(self.tmp.name, "gone.flac"))]
        plan = plan_for(items, "mp3")
        self.assertEqual(plan["transcode"], 0)
        self.assertEqual(plan["unreachable"], 1)
        self.assertEqual(plan["unreachable_by_reason"], {"missing": 1})

    def test_an_unmounted_drive_is_reported_as_unmounted(self):
        items = [FakeItem(1, "FLAC", "/Volumes/NoSuchDrive/song.flac")]
        plan = plan_for(items, "mp3")
        self.assertEqual(plan["unreachable_by_reason"], {"unmounted": 1})

    def test_lossy_to_lossy_is_counted_as_a_quality_loss(self):
        items = [FakeItem(1, "MP3", self.real_file("a.mp3"))]
        self.assertEqual(plan_for(items, "opus")["lossy_reencode"], 1)

    def test_lossless_to_lossy_is_not_a_second_generation_loss(self):
        items = [FakeItem(1, "FLAC", self.real_file("a.flac"))]
        self.assertEqual(plan_for(items, "mp3")["lossy_reencode"], 0)

    def test_lossy_to_lossless_is_not_flagged(self):
        items = [FakeItem(1, "MP3", self.real_file("a.mp3"))]
        self.assertEqual(plan_for(items, "flac")["lossy_reencode"], 0)

    def test_source_size_covers_only_what_is_actually_converted(self):
        items = [FakeItem(1, "FLAC", self.real_file("a.flac", 4096)),
                 FakeItem(2, "MP3", self.real_file("b.mp3", 8192))]
        self.assertEqual(plan_for(items, "mp3")["source_bytes"], 4096)

    def test_an_empty_query_is_marked_as_the_whole_library(self):
        with mock.patch.object(library, "all_items", return_value=[]):
            self.assertTrue(library.convert_plan("", "mp3")["whole_library"])
        with mock.patch.object(library, "search", return_value=[]):
            self.assertFalse(library.convert_plan("artist:x", "mp3")["whole_library"])


class ConvertToolTest(unittest.TestCase):
    """Every early return here is a conversion that must NOT reach the user's
    files."""

    def _invoke(self, **args):
        return tools.convert_tracks.invoke(args)

    def test_an_unknown_format_is_refused_without_converting(self):
        with mock.patch.object(library, "convert") as convert:
            result = self._invoke(query="artist:x", format="mp4")
        convert.assert_not_called()
        self.assertIn("Unknown format", result)

    def test_a_query_matching_nothing_converts_nothing(self):
        empty = {"matched": 0, "transcode": 0, "skipped": 0, "unreachable": 0,
                 "unreachable_by_reason": {}, "lossy_reencode": 0,
                 "source_bytes": 0, "whole_library": False, "items": []}
        with mock.patch.object(library, "convert_plan", return_value=empty), \
             mock.patch.object(library, "convert") as convert:
            result = self._invoke(query="artist:nobody", format="mp3")
        convert.assert_not_called()
        self.assertIn("No tracks matched", result)

    def test_nothing_to_do_skips_the_subprocess_entirely(self):
        plan = {"matched": 5, "transcode": 0, "skipped": 5, "unreachable": 0,
                "unreachable_by_reason": {}, "lossy_reencode": 0,
                "source_bytes": 0, "whole_library": False, "items": []}
        with mock.patch.object(library, "convert_plan", return_value=plan), \
             mock.patch.object(library, "convert") as convert:
            result = self._invoke(query="artist:x", format="mp3")
        convert.assert_not_called()
        self.assertIn("already mp3", result)

    def _run_with_plan(self, log=None, **kwargs):
        plan = {"matched": 3, "transcode": 3, "skipped": 0, "unreachable": 0,
                "unreachable_by_reason": {}, "lossy_reencode": 0,
                "source_bytes": 1024, "whole_library": False, "items": []}
        # A real beets log: the tool reports what the log says, not the plan.
        if log is None:
            log = "\n".join(f"convert: Finished encoding /music/{n}.flac"
                            for n in range(3))
        with mock.patch.object(library, "convert_plan", return_value=plan), \
             mock.patch.object(library, "convert", return_value=log) as convert:
            result = self._invoke(**kwargs)
        return convert, result

    def test_export_writes_to_the_conversion_folder_and_keeps_the_library(self):
        convert, result = self._run_with_plan(query="artist:x", format="mp3")
        self.assertFalse(convert.call_args.kwargs["replace"])
        self.assertEqual(convert.call_args.args[2],
                         config.get_config().convert_dest_path)
        self.assertIn("unchanged", result)

    def test_replace_archives_the_originals(self):
        convert, result = self._run_with_plan(query="artist:x", format="mp3",
                                              replace=True)
        self.assertTrue(convert.call_args.kwargs["replace"])
        self.assertEqual(convert.call_args.args[2],
                         config.get_config().convert_archive_path)
        self.assertIn("originals were moved", result)

    def test_an_unknown_quality_is_refused_without_converting(self):
        with mock.patch.object(library, "convert") as convert:
            result = self._invoke(query="artist:x", format="mp3",
                                  quality="ultra")
        convert.assert_not_called()
        self.assertIn("Unknown quality", result)

    def test_the_quality_the_model_picked_is_the_one_used(self):
        convert, result = self._run_with_plan(query="artist:x", format="mp3",
                                              quality="best")
        self.assertEqual(convert.call_args.kwargs["quality"], "best")
        self.assertIn("320 kbps", result)

    def test_quality_defaults_to_normal(self):
        convert, _ = self._run_with_plan(query="artist:x", format="mp3")
        self.assertEqual(convert.call_args.kwargs["quality"], "normal")

    def test_a_named_destination_beats_the_configured_folder(self):
        convert, result = self._run_with_plan(query="artist:x", format="mp3",
                                              destination="~/Desktop/phone")
        expected = os.path.expanduser("~/Desktop/phone")
        self.assertEqual(convert.call_args.args[2], expected)
        self.assertIn(expected, result)

    def test_an_empty_destination_still_uses_the_configured_folder(self):
        convert, _ = self._run_with_plan(query="artist:x", format="mp3",
                                         destination="   ")
        self.assertEqual(convert.call_args.args[2],
                         config.get_config().convert_dest_path)

    def test_a_running_conversion_holds_off_the_inactivity_watchdog(self):
        plan = {"matched": 1, "transcode": 1, "skipped": 0, "unreachable": 0,
                "unreachable_by_reason": {}, "lossy_reencode": 0,
                "source_bytes": 1, "whole_library": False, "items": []}
        seen = []
        with mock.patch.object(library, "convert_plan", return_value=plan), \
             mock.patch.object(library, "convert",
                               side_effect=lambda *a, **k: seen.append(activity.busy()) or ""):
            self._invoke(query="artist:x", format="mp3")
        self.assertEqual(seen, [True])
        self.assertFalse(activity.busy())   # and released afterwards


class ConvertOutcomeTest(unittest.TestCase):
    """Reading back what beets actually did: it skips files whose target
    exists and reports failed encodes per file while still exiting 0."""

    def test_finished_lines_are_what_counts_as_encoded(self):
        log = ("convert: Encoding /music/a.flac\n"
               "convert: Encoding /music/b.flac\n"
               "convert: Finished encoding /music/a.flac\n"
               "convert: Finished encoding /music/b.flac")
        done = library.convert_outcome(log)
        self.assertEqual(done["encoded"], 2)
        self.assertEqual(done["wrote"], 2)
        self.assertTrue(done["ok"])

    def test_a_started_encode_is_not_a_finished_one(self):
        # "Encoding" is printed before ffmpeg runs.
        log = ("convert: Encoding /music/a.flac\n"
               "convert: Encoding /music/a.flac failed. Cleaning up...")
        done = library.convert_outcome(log)
        self.assertEqual(done["encoded"], 0)
        self.assertEqual(done["failed"], 1)
        self.assertFalse(done["ok"])

    def test_targets_that_already_existed_are_counted_separately(self):
        log = ("convert: Skipping /music/a.flac (target file exists)\n"
               "convert: Skipping /music/b.flac (target file exists)")
        done = library.convert_outcome(log)
        self.assertEqual(done["existing"], 2)
        self.assertEqual(done["wrote"], 0)

    def test_files_already_in_the_target_format_count_as_written(self):
        done = library.convert_outcome("convert: Copying /music/a.mp3")
        self.assertEqual(done["copied"], 1)
        self.assertEqual(done["wrote"], 1)

    def test_a_nonzero_exit_is_not_ok_even_with_encodes(self):
        done = library.convert_outcome("convert: Finished encoding /music/a.flac",
                                       exit_status=1)
        self.assertEqual(done["encoded"], 1)
        self.assertFalse(done["ok"])


class ConvertReportingTest(unittest.TestCase):
    """The agent tool must describe the run, not the request."""

    def _report(self, log, transcode=2, **kwargs):
        plan = {"matched": transcode, "transcode": transcode, "skipped": 0,
                "unreachable": 0, "unreachable_by_reason": {},
                "lossy_reencode": 0, "source_bytes": 1, "whole_library": False,
                "items": []}
        with mock.patch.object(library, "convert_plan", return_value=plan), \
             mock.patch.object(library, "convert", return_value=log):
            args = {"query": "artist:x", "format": "mp3", **kwargs}
            return tools.convert_tracks.invoke(args)

    def test_a_rerun_that_wrote_nothing_is_not_reported_as_converted(self):
        result = self._report(
            "convert: Skipping /music/a.flac (target file exists)\n"
            "convert: Skipping /music/b.flac (target file exists)")
        self.assertIn("Nothing was converted", result)
        self.assertNotIn("Converted 2 tracks", result)

    def test_an_all_failed_run_is_reported_as_a_failure(self):
        result = self._report(
            "convert: Encoding /music/a.flac\n"
            "convert: Encoding /music/a.flac failed. Cleaning up...\n"
            "convert: Encoding /music/b.flac failed. Cleaning up...")
        self.assertIn("FAILED", result)
        self.assertIn("0 of 2", result)

    def test_a_partial_run_reports_the_count_that_was_written(self):
        result = self._report(
            "convert: Finished encoding /music/a.flac\n"
            "convert: Skipping /music/b.flac (target file exists)")
        self.assertIn("Converted 1 tracks", result)
        self.assertIn("1 were left alone", result)

    def test_a_silent_log_never_claims_success(self):
        result = self._report("")
        self.assertIn("Do not tell the user the conversion succeeded", result)

    def test_an_invalid_query_is_reported_not_raised(self):
        # A tool result the model can act on, not a crashed turn.
        with mock.patch.object(library, "convert_plan",
                               side_effect=ValueError("bad query")), \
             mock.patch.object(library, "convert") as convert:
            result = tools.convert_tracks.invoke(
                {"query": "artist::(", "format": "mp3"})
        convert.assert_not_called()
        self.assertIn("isn't valid", result)

    def test_an_unusable_destination_is_reported_not_raised(self):
        plan = {"matched": 1, "transcode": 1, "skipped": 0, "unreachable": 0,
                "unreachable_by_reason": {}, "lossy_reencode": 0,
                "source_bytes": 1, "whole_library": False, "items": []}
        with mock.patch.object(library, "convert_plan", return_value=plan), \
             mock.patch.object(library, "convert",
                               side_effect=PermissionError("nope")):
            result = tools.convert_tracks.invoke(
                {"query": "artist:x", "format": "mp3",
                 "destination": "/System/nope"})
        self.assertIn("Nothing was converted", result)
        self.assertIn("could not be used as the destination", result)


class LongTaskTest(unittest.TestCase):
    def test_nesting_keeps_the_flag_up_until_the_last_one_finishes(self):
        with activity.long_task():
            with activity.long_task():
                self.assertTrue(activity.busy())
            self.assertTrue(activity.busy())
        self.assertFalse(activity.busy())

    def test_an_exception_still_clears_the_flag(self):
        with self.assertRaises(ValueError):
            with activity.long_task():
                raise ValueError("boom")
        self.assertFalse(activity.busy())
