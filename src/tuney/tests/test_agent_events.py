"""The tool-call events that let the UI say what the agent is doing."""

import unittest

from langchain_core.messages import AIMessage, ToolMessage

from tuney.agents import activity
from tuney.agents.Agent import _tool_events
from tuney.tui.Panes.ChatPane import _tool_label


def _call(name, args, id="c1"):
    return {"name": name, "args": args, "id": id, "type": "tool_call"}


class ToolEventTest(unittest.TestCase):
    """_tool_events against the `updates` payloads langgraph emits."""

    def test_model_node_yields_one_event_per_requested_call(self):
        update = {"model": {"messages": [AIMessage(content="", tool_calls=[
            _call("collection_search", {"task": "list BabyTron albums"}),
            _call("wishlist", {"task": "add Case Dismissed"}, id="c2"),
        ])]}}
        self.assertEqual(list(_tool_events(update)), [
            ("tool", {"name": "collection_search",
                      "args": {"task": "list BabyTron albums"}}),
            ("tool", {"name": "wishlist",
                      "args": {"task": "add Case Dismissed"}}),
        ])

    def test_tool_node_yields_a_completion(self):
        update = {"tools": {"messages": [
            ToolMessage(content="...", name="search_collection",
                        tool_call_id="c1")]}}
        self.assertEqual(list(_tool_events(update)),
                         [("tool_done", {"name": "search_collection",
                                         "args": {}})])

    def test_plain_answer_yields_nothing(self):
        update = {"model": {"messages": [AIMessage(content="here you go")]}}
        self.assertEqual(list(_tool_events(update)), [])

    def test_unexpected_shapes_are_ignored_not_raised(self):
        # Runs inside the stream loop: an unfamiliar node update must not kill
        # the whole run.
        for junk in ({}, {"x": None}, {"x": {}}, {"x": {"messages": []}},
                     {"x": {"messages": None}}, {"x": "surprise"}):
            with self.subTest(junk=junk):
                self.assertEqual(list(_tool_events(junk)), [])


class ToolLabelTest(unittest.TestCase):
    """_tool_label — what the status line actually says."""

    def test_supervisor_tools_get_a_human_label_without_the_brief(self):
        label = _tool_label({"name": "collection_search",
                             "args": {"task": "list every album by X"}})
        self.assertEqual(label, "Searching your collection")

    def test_unknown_tool_falls_back_to_its_name(self):
        self.assertEqual(_tool_label({"name": "list_wishlist", "args": {}}),
                         "list wishlist")

    def test_shows_the_most_specific_argument(self):
        self.assertEqual(
            _tool_label({"name": "search_collection",
                         "args": {"query": "artist:babytron"}}),
            "search collection · artist:babytron")
        self.assertEqual(
            _tool_label({"name": "collection_has",
                         "args": {"artist": "BabyTron", "album": "Megatron"}}),
            "collection has · Megatron")

    def test_long_arguments_are_truncated_to_one_line(self):
        label = _tool_label({"name": "search_collection",
                             "args": {"query": "x" * 200}})
        self.assertLessEqual(len(label), 90)
        self.assertTrue(label.endswith("…"))

    def test_newlines_in_an_argument_do_not_break_the_line(self):
        label = _tool_label({"name": "search_collection",
                             "args": {"query": "artist:x\n\nyear:2024"}})
        self.assertEqual(label, "search collection · artist:x year:2024")

    def test_missing_name_still_renders(self):
        self.assertEqual(_tool_label({}), "working")


class ActivityToolTest(unittest.TestCase):
    """activity.set_tool — the moving part of the subagent banner."""

    def tearDown(self):
        activity._active.clear()

    def test_tracks_the_specialists_current_tool(self):
        token = activity.start("Search", "find every BabyTron album")
        self.assertEqual(activity.snapshot()[0]["tool"], "")

        activity.set_tool(token, "distinct_values")
        self.assertEqual(activity.snapshot()[0]["tool"], "distinct_values")

        activity.set_tool(token, "")     # result came back
        self.assertEqual(activity.snapshot()[0]["tool"], "")

        activity.finish(token)
        self.assertEqual(activity.snapshot(), [])

    def test_setting_a_tool_on_a_finished_run_is_harmless(self):
        # The specialist's last tool_done can land after `finish` in a
        # cancelled run; it must not resurrect the entry.
        token = activity.start("Search", "task")
        activity.finish(token)
        activity.set_tool(token, "search_collection")
        self.assertEqual(activity.snapshot(), [])
