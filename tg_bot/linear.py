"""Linear API wrappers."""

import json
import urllib.request

from tg_bot.config import LINEAR_KEY, LIN_DONE, LIN_PROJECT, LIN_TEAM, PROXY


def _lin(query):
    try:
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=json.dumps({"query": query}).encode(),
            headers={"Authorization": LINEAR_KEY, "Content-Type": "application/json"},
        )
        handlers = []
        if PROXY:
            handlers.append(
                urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
            )
        opener = urllib.request.build_opener(*handlers)
        with opener.open(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def get_tickets():
    r = _lin(
        '{ issues(filter: { project: { id: { eq: "%s" } } }, first: 50)'
        " { nodes { id identifier title state { name } priority } } }" % LIN_PROJECT
    )
    return sorted(
        r.get("data", {}).get("issues", {}).get("nodes", []),
        key=lambda x: x["identifier"],
    )


def move_to_done(ticket_num):
    r = _lin(
        '{ issues(filter: { team: { key: { eq: "%s" } },'
        " number: { eq: %d } }) { nodes { id } } }" % (LIN_TEAM, ticket_num)
    )
    nodes = r.get("data", {}).get("issues", {}).get("nodes", [])
    if not nodes:
        return
    iid = nodes[0]["id"]
    mutation = json.dumps({
        "query": (
            "mutation($id: String!, $input: IssueUpdateInput!) "
            "{ issueUpdate(id: $id, input: $input) "
            "{ issue { identifier state { name } } } }"
        ),
        "variables": {"id": iid, "input": {"stateId": LIN_DONE}},
    }).encode()
    try:
        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=mutation,
            headers={"Authorization": LINEAR_KEY, "Content-Type": "application/json"},
        )
        handlers = []
        if PROXY:
            handlers.append(
                urllib.request.ProxyHandler({"https": PROXY, "http": PROXY})
            )
        opener = urllib.request.build_opener(*handlers)
        opener.open(req, timeout=15)
    except Exception:
        pass
