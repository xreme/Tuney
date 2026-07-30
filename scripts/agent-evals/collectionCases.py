"""eval cases for the collection search specialist"""


def _mentions(*needles: str):
    """Arg matcher: any arg value mentions one of these (case-insensitive)."""

    def matcher(output_args: dict, _reference_args: dict) -> bool:
        blob = " ".join(str(v) for v in output_args.values()).lower()
        return any(n.lower() in blob for n in needles)

    return matcher


CASES = [
    {
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
