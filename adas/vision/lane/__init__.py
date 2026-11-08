"""Lane-departure vision stages: preprocess -> detect -> decide.

``departure.DepartureDecider`` (the debounced state machine) is real and
unit-tested; ``preprocess``/``detector``/``model`` are the classical + learned
CV stages that feed it a signed lateral offset.
"""
