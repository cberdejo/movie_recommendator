def parse_int(v):
    """
    Parse string to int if possible

    Raises
        TypeError if not possible
    """
    if v is None or isinstance(v, int):
        return v
    if isinstance(v, str):
        s = v.strip()
        return int(s)
    raise TypeError(f"tipo no soportado: {type(v).__name__}")
