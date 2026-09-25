from app.engine.material_flow import AWAITING, FlowRecord, build_sankey, kg_by_material, traced_share

RECORDS = [
    FlowRecord("Asha", "Agg1", "RecA", "metal", 10.0),
    FlowRecord("Asha", "Agg1", None, "metal", 5.0),
    FlowRecord("Bala", "Agg1", "RecA", "pet", 3.0),
    FlowRecord("Bala", "Agg2", None, "pet", 2.0),
]


def edges(sankey):
    names = [n["name"] for n in sankey["nodes"]]
    return {(names[l["source"]], names[l["target"]], l["material"]): l["value"] for l in sankey["links"]}


def test_kg_by_material_sorted_desc():
    assert kg_by_material(RECORDS) == {"metal": 15.0, "pet": 5.0}


def test_traced_share():
    assert traced_share(RECORDS) == {"kg_total": 20.0, "kg_traced": 13.0, "pct_traced": 65.0}
    assert traced_share([])["pct_traced"] == 0.0


def test_sankey_links_aggregate_by_path_and_material():
    s = build_sankey(RECORDS)
    assert edges(s) == {
        ("Asha", "Agg1", "metal"): 15.0,
        ("Bala", "Agg1", "pet"): 3.0,
        ("Bala", "Agg2", "pet"): 2.0,
        ("Agg1", "RecA", "metal"): 10.0,
        ("Agg1", "RecA", "pet"): 3.0,
        ("Agg1", AWAITING, "metal"): 5.0,
        ("Agg2", AWAITING, "pet"): 2.0,
    }


def test_sankey_nodes_ordered_by_stage_and_mass_conserved():
    s = build_sankey(RECORDS)
    assert [n["stage"] for n in s["nodes"]] == ["collector", "collector", "aggregator", "aggregator",
                                                 "recycler", "pending"]
    into_aggs = sum(l["value"] for l in s["links"] if s["nodes"][l["target"]]["stage"] == "aggregator")
    out_of_aggs = sum(l["value"] for l in s["links"] if s["nodes"][l["source"]]["stage"] == "aggregator")
    assert into_aggs == out_of_aggs == 20.0


def test_same_label_in_different_stages_are_distinct_nodes():
    s = build_sankey([FlowRecord("Sanganer", "Sanganer", "Sanganer", "glass", 1.0)])
    assert len(s["nodes"]) == 3


def test_empty():
    assert build_sankey([]) == {"nodes": [], "links": []}


def test_kg_by_material_name_splits_copper_from_metal():
    recs = [FlowRecord("A", "G", None, "metal", 4.0, "Copper"),
            FlowRecord("A", "G", None, "metal", 6.0, "Steel/Al")]
    assert kg_by_material(recs) == {"metal": 10.0}
    assert kg_by_material(recs, by="name") == {"Steel/Al": 6.0, "Copper": 4.0}
