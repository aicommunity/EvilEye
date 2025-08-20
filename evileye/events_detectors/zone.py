from enum import Enum


class ZoneForm(Enum):
    Rectangle = 'rect'
    Polygon = 'poly'


class Zone:
    def __init__(self, source: int, coords: tuple, zone_form: str = None, is_active: bool = False, zone_id=None):
        self.id = None
        self.source_id = source
        self.norm_coords = coords
        self.is_active = is_active
        self.zone_form = None
        if zone_form:
            self.zone_form = ZoneForm(zone_form)
        # TODO: add zone name?

    def __eq__(self, other):
        return self.source_id == other.source_id and self.norm_coords == other.norm_coords

    def set_id(self, zone_id):
        if not self.id:
            self.id = zone_id

    def get_coords(self):
        return self.norm_coords

    def set_active(self, active: bool):
        self.is_active = active

    def get_src_id(self):
        return self.source_id

    def get_zone_id(self):
        return self.id

    def get_zone_form(self):
        return self.zone_form
