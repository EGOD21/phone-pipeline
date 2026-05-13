from smb_phone_pipeline.seeds import build_partitions, load_categories


def test_load_custom_categories():
    assert load_categories("plumbers, electricians") == ["plumbers", "electricians"]


def test_build_partitions_for_state_and_pages():
    partitions = build_partitions({"TX"}, ["plumbers"], limit_cities=1, pages=2)
    assert len(partitions) == 2
    assert {partition.state for partition in partitions} == {"TX"}
    assert {partition.page for partition in partitions} == {1, 2}
