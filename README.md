# Verbal - natural language remote computer management interface

Working with SSH on a phone is a terrible experience. Using LLMs can simplify
the operation of remote machines. The Verbal system presents a web UI with
access to a language madel, which is equipped with commands to inspect the
file system, to read, write, edit or delete files, and to run shell commands.
Once a basic system like this is running, any improvement in any direction
the user wants to take can be done with only natural language input.

Everything is properly containerized, with checkpointing implemented outside
the LLM-controlled directories. In the future this will also implement a
separate staging server, and support other features such as fetching logs
and diffing against the last checkpoint.

The implementation includes: nginx to handle SSL, which forwards connections
to oauth2-proxy that authenticates users, which forwards them to the container
with the actual Verbal app. There is also a checkpointing service, which
provides an API that the LLM container can access.
