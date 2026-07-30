"""eval cases for the collection search specialist

A catalogue of case groups, one per thing being probed. Which groups actually
run is decided in evalCollectionSearchAgent.py, alongside the model list — this
file only defines them.

Every case targets a real track in the dev library; the item ids in the
comments are what the agent should land on.
"""


def _mentions(*needles: str):
    """Arg matcher: any arg value mentions one of these (case-insensitive)."""

    def matcher(output_args: dict, _reference_args: dict) -> bool:
        blob = " ".join(str(v) for v in output_args.values()).lower()
        return any(n.lower() in blob for n in needles)

    return matcher


def _item_id(*ids: int):
    """Arg matcher: the call targets one of these beets ids.

    For the id-taking tools (`locate_file`, `item_information`) — checking the
    id is the whole assertion, since it proves the agent resolved the right
    track before asking about its file.
    """

    def matcher(output_args: dict, _reference_args: dict) -> bool:
        return any(v in ids for v in output_args.values())

    return matcher


# 1. Finding a song by filename.
#
# Every target here is untagged (no artist, no title, no album), so metadata
# search can't find it — the agent has to fall back to `search_by_filename`.
# That fallback is the thing under test; a case passes only if the agent gets
# there rather than reporting the track missing.
FILENAME_CASES = [
    {
        # id 12049 — "KSI - KILIMANJARO (Official Video).mp3". The user types
        # the file name verbatim, so this is the floor: no inference needed.
        "name": "filename-exact",
        "prompt": "Do I have KSI - KILIMANJARO (Official Video).mp3?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_by_filename",
                                  "arguments": '{"fragment": "KILIMANJARO"}'}}
                ],
            }
        ],
        "arg_matchers": {
            "search_by_filename": _mentions("kilimanjaro", "ksi"),
            "search_collection": _mentions("kilimanjaro", "ksi"),
        },
    },
    {
        # id 12027 — "Linkin_Park_-_Good_Goodbye.mp3". The user writes the name
        # the natural way, with spaces; the file uses underscores. A literal
        # "good goodbye" fragment misses, so the agent has to loosen the
        # fragment (or regex around the separator) rather than give up.
        "name": "filename-semantic",
        "prompt": "Where's my Good Goodbye track by Linkin Park?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_by_filename",
                                  "arguments": '{"fragment": "Goodbye"}'}}
                ],
            }
        ],
        "arg_matchers": {
            "search_by_filename": _mentions("goodbye", "linkin"),
            "search_collection": _mentions("goodbye", "linkin"),
        },
    },
    {
        # id 12041 — "G-Eazy - Bone Marrow (Audio) ft. Danny Seth.mp3", misspelt
        # by the user as "marow". G-Eazy has 37 tagged tracks, so metadata
        # search returns plenty of plausible-looking noise without the target —
        # the tempting failure is answering off that noise.
        "name": "filename-typo",
        "prompt": "find bone marow by g eazy",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_by_filename",
                                  "arguments": '{"fragment": "Marrow"}'}}
                ],
            }
        ],
        "arg_matchers": {
            "search_by_filename": _mentions("marrow", "marow", "bone", "eazy"),
            "search_collection": _mentions("marrow", "marow", "bone", "eazy"),
        },
    },
    {
        # id 12081 — "Sik Kid - Broken Wings (Prod. Tido Vegas).mp3". The user
        # names only the artist and never the title, and "Sik Kid" exists
        # nowhere in the library's metadata — only inside that one file name.
        "name": "filename-artist-only",
        "prompt": "I've got one song by Sik Kid somewhere, which one is it?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_by_filename",
                                  "arguments": '{"fragment": "Sik Kid"}'}}
                ],
            }
        ],
        "arg_matchers": {
            "search_by_filename": _mentions("sik kid", "sik"),
            "search_collection": _mentions("sik kid", "sik"),
        },
    },
]

# Counting songs by an artist.
#
# `count_items` exists so the agent doesn't page through `search_collection`
# and tally by hand, so the trajectory assertion is that it reaches for the
# counting tool. Check the `answer` column for the number itself.
COUNT_CASES = [
    {
        # 175 tracks tagged artist "Drake"; 212 if collab credits count.
        # Either is defensible — what matters is that the agent counts rather
        # than estimates.
        "name": "count-drake",
        "prompt": "How many Drake songs do I have?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "count_items",
                                  "arguments": '{"query": "artist:drake"}'}}
                ],
            }
        ],
        "arg_matchers": {"count_items": _mentions("drake")},
    },
    {
        # 186 tracks tagged artist "Larry June" (244 with collabs). Two words,
        # so the query needs quoting — an unquoted `artist:larry june` splits
        # into two ANDed terms and silently undercounts.
        "name": "count-larry-june",
        "prompt": "How many Larry June songs are in my collection?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "count_items",
                                  "arguments": '{"query": "artist:\\"larry june\\""}'}}
                ],
            }
        ],
        "arg_matchers": {"count_items": _mentions("larry")},
    },
    {
        # Zero Taylor Swift anywhere — artist, title, album or file path. The
        # agent should work through its retry ladder and then say plainly that
        # there are none, without inventing a number.
        "name": "count-absent-artist",
        "prompt": "How many Taylor Swift songs do I have?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "count_items",
                                  "arguments": '{"query": "artist:\\"taylor swift\\""}'}}
                ],
            }
        ],
        "arg_matchers": {
            "count_items": _mentions("taylor", "swift"),
            "search_collection": _mentions("taylor", "swift"),
            "search_by_filename": _mentions("taylor", "swift"),
        },
    },
]

# 3. Locating a track's file on disk.
#
# `locate_file` takes a beets id, so the expected trajectory is always
# search-then-locate: resolve the track, then ask where it lives. These cases
# also test how the agent relays a failure it can't fix — the tool returns
# prose explaining the drive or file problem, and the agent should pass that
# reason on instead of flattening it to "not found".
LOCATION_CASES = [
    {
        # id 12286 — Tee Grizzley "First Day Out", on the internal disk under
        # ~/Downloads, file present. The control: without it, a passing
        # trajectory on the two failure cases below proves nothing.
        "name": "locate-file-present",
        "prompt": "Where is the file for Tee Grizzley's First Day Out?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_collection",
                                  "arguments": '{"query": "artist:\\"tee grizzley\\" title:\\"first day out\\""}'}}
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "locate_file",
                                  "arguments": '{"itemId": 12286}'}}
                ],
            },
        ],
        "arg_matchers": {
            "search_collection": _mentions("grizzley", "first day out"),
            "locate_file": _item_id(12286),
        },
    },
    {
        # id 9792 — Kanye West "Off The Grid", the only copy in the library and
        # it sits on /Volumes/MUSIC, which is not mounted. `locate_file` raises
        # DriveNotMounted and comes back with "reconnect the drive"; a good
        # answer says the drive is offline, not that the file is gone.
        "name": "locate-drive-unmounted",
        "prompt": "Where's the file for Off The Grid by Kanye West?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_collection",
                                  "arguments": '{"query": "artist:kanye title:\\"off the grid\\""}'}}
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "locate_file",
                                  "arguments": '{"itemId": 9792}'}}
                ],
            },
        ],
        "arg_matchers": {
            "search_collection": _mentions("kanye", "off the grid"),
            "locate_file": _item_id(9792),
        },
    },
    {
        # id 12291 — Tee Grizzley "Overlapped". Its drive IS mounted but the
        # file is meant to be absent, so `locate_file` raises FileNotFoundError
        # and reports a stale library entry — a different fix for the user than
        # the unmounted case, which is the distinction being tested.
        #
        # REQUIRES the file to actually be missing. As of writing every local
        # file in the library is present, so stage it before the run and put it
        # back after:
        #   mv "$F" "$F.bak"   # then, after the run:   mv "$F.bak" "$F"
        # where F="/Users/reme/Downloads/My Moment (2017)/Tee Grizzley - My Moment - 07 - Overlapped.flac"
        # Without that, this case degrades into a second copy of
        # locate-file-present: the trajectory still passes, but the `answer`
        # column shows a found file rather than the missing-file report.
        "name": "locate-file-missing",
        "requires": "item 12291's file removed from disk (see comment above)",
        "prompt": "Where is Overlapped by Tee Grizzley stored?",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_collection",
                                  "arguments": '{"query": "artist:\\"tee grizzley\\" title:overlapped"}'}}
                ],
            },
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "locate_file",
                                  "arguments": '{"itemId": 12291}'}}
                ],
            },
        ],
        "arg_matchers": {
            "search_collection": _mentions("grizzley", "overlapped"),
            "locate_file": _item_id(12291),
        },
    },
]

# Odds and ends that don't belong to a numbered category.
METADATA_CASES = [
    {
        # "U Mad Bro" is deliberately ambiguous: Speaker Knockerz has it tagged
        # (id 11777) and there's an untagged "Kevin Flum - U Mad Bro-.mp3"
        # (id 12046). Either is a fair read of the prompt.
        "name": "metadata-you-mad-bro",
        "prompt": "Show me you mad bro's metadata",
        "reference": [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "search_collection",
                                  "arguments": '{"query": "you mad bro"}'}}
                ],
            }
        ],
        "arg_matchers": {
            "search_collection": _mentions("mad", "bro"),
            "item_information": _mentions("mad", "bro"),
        },
    },
]
