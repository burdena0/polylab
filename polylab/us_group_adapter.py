"""Adapt registered multi-station group metadata to the frozen single-city loader."""
from .us_benter import load_groups


def load_station_groups(root, cfg, rows, model):
    groups = []
    for group in cfg['groups']:
        if group.get('station', cfg['station']) != cfg['station']:
            raise ValueError('Registered group station differs from selected station')
        groups.append({key:value for key,value in group.items() if key!='station'})
    # The frozen loader adds station itself and verifies every rule's station.
    # This removes a redundant keyword, without changing rules or model inputs.
    return load_groups(root, {**cfg, 'groups':groups}, rows, model)
