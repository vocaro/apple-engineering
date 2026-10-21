# Python environments

These mechanisms and lessons apply when the stated capability is present. Original
measurements establish their recorded platform and workload; they do not establish
universal behavior on later operating systems or in a different application.

## Python native-dependency preflight

Locked environments, inspection before native imports, and repair from verified dependency downloads when quarantine would otherwise cause a blocking dialog or misleading import failure.

[studywright scripts/check-python-quarantine.py](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/scripts/check-python-quarantine.py) and [studywright scripts/check-all-python-env.sh](https://github.com/vocaro/studywright/blob/f25d97a147e63c8c9a3bdbebaad2ea1c7e957e8c/scripts/check-all-python-env.sh). Share the method and inspector; environment contents remain per checkout.
