#!/bin/bash

# Entrypoint for running a Celery worker

# Activate python virtual environment
source /venv/bin/activate

# Run health-checker application, which reports back on the health of this container.
# And in parallel run the celery workers, with the beat scheduler embedded (-B: fine for one worker;
health-checker --listener 0.0.0.0:5001 --log-level error --script-timeout 10 --script "celery -A src.eddie_antartica.tasks inspect ping"  \
& celery -A src.eddie_antartica.tasks worker -B -s tmp/celerybeat-schedule -P threads --loglevel=INFO
