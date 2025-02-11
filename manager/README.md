# The management and support service of Verbal

Responsible for refreshing staging and production containers, and for checkpointing.

To run in a local virtual env:

```
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

./venv/bin/python server.py
```

TODO: only allow connections from docker and not from outside.
