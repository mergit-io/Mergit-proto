"""Measuring whether Mergit did the thing, by asking the services rather than the agent.

The brief this was written for says "show how you know it works", and the honest answer
cannot come from the agent's own report — that is the thing under test. Every check here
reads the outside world back: GitHub for the pull request, Linear for the ticket, Notion
for the page, Slack for the reply.

The number that matters is not the success rate. It is the **silent-failure rate**: runs
the system called COMPLETED that the services say did not happen. A run that fails loudly
costs a retry; a run that fails silently costs trust in every other run.
"""
