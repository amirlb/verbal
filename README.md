# Verbal - natural language remote computer management interface

Working with SSH on a phone is a terrible experience. Using LLMs can simplify
the operation of remote machines. The Verbal system presents a web UI with
access to a language madel, which is equipped with commands to inspect the
file system, to read, write, edit or delete files, and to run shell commands.
Once a basic system like this is running, any improvement in any direction
the user wants to take can be done with only natural language input.

Everything is properly containerized, with staging/production split, in order
to avoid losing data. There is an outside-facing HTTP server which
authenticates the user with oauth, and shows an iframe which is served by
the inside server which communicates with the language model. There's also
a settings icon for non-language-model actions: view files, view logs, deploy.

The HTTP endpoints are:
* `/` - The landing page, includes an iframe from `/verbal` and link to the
    settings page
* `/settings` - Menu with several buttons, TBD, leave empty for now
* `/verbal` - Redirects to the inner (production) server, which serves an
    interface to the language model
* `/staging` - A version of the language page that includes an iframe from
    `/verbal-staging`, which redirects to the inner staging server
* `/api/deploy` - Copy from the staging directory to production and commit.
* `/api/...` - Implementation of other settings page commands.

The inner service would also interpret commands from the language model and
run them on the system, which means it must run in a separate container. In
addition, actions in both instances edit the same directory (staging).
Deploying code is handled by the outside service. The production copy is
a git repo, and on every deployment a new commit is created.
