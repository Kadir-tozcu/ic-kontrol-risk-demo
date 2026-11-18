"""Public demo input already uses the generator's canonical column names."""


def normalize_columns(frame, fields):
    return frame.copy()


def field_label(name):
    return name
