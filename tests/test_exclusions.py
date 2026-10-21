from vision.exclusions import OutputExclusions


def test_boat_exclusion_preserves_swimmers_and_water_boats():
    exclusion = OutputExclusions({"coordinate_space": "normalized", "rules": [{
        "classes": ["boat"], "polygon": [[0,0],[.5,0],[.5,1],[0,1]],
        "min_box_overlap": .6, "end_frame": 10}]})
    tree = {"class": "boat", "bbox_xyxy_px": [0,0,40,40]}
    swimmer = {"class": "swimmer", "bbox_xyxy_px": [0,0,40,40], "track_id": 9}
    water_boat = {"class": "boat", "bbox_xyxy_px": [60,0,90,40]}
    kept, rejected = exclusion.filter([tree,swimmer,water_boat],100,100,0)
    assert kept == [swimmer,water_boat]
    assert kept[0] is swimmer
    assert rejected == [tree]
    assert exclusion.filter([tree],100,100,11) == ([tree],[])
