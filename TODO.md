# List of things to think about.

## How to handle logging of referenced sessions.

**Context** When a prior session is referenced with `/set session <id>` it is logged in the dln under the current session id, which is fixed. Once a session is complete, it cannot be altered or appended. This data/history preservation strategy results in a query challenge if something in this new session needs to be found in the future.

**Options**

- Update queries to search for the "focus_session" key in the `context` entry type.
- Update session_id searches to be `IN (a, b, c)` instead of an equality. Also revise /session commands to be add/drop as opposed to set, which will modify that list
- Create a virtual experiment/meta-analysis style experiment

I'm leaning towards the listed session_id. I do not know how much needs to be changed (what references session_id presently)